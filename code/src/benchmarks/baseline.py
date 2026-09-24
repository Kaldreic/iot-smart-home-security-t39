"""benchmarks.baseline — a re-implementation of AirBugCatcher's native minimiser (the baseline arm).

Depends only on the oracle protocol (``rdd.oracle``, ``rdd.sprt``); the exact crash-id matcher it is paired
with is ``emulation.baseline.exact_crash_id``. Mechanism, per the esp32_bt config (``max_fuzzed_pkts=3``,
``max_try=3``): candidates are ``itertools.combinations`` over the window in increasing cardinality,
most-recent-first (packets closer to the crash first), capped at three packets; a subset is run at most once
and enumeration stops at the first reproducer, so the result is the smallest subset caught; the ``max_try``
loop breaks on the first non-crash trial and on a repeated crash id, so each candidate gets one effective
reproduction attempt, with no trial-time budget and an exact crash-id match.

Each bug has its own packet window, so cross-bug session reuse is out of scope. Because the first positive
read is accepted, the baseline's false credit under the modelled channel is the phantom-crash rate (a
phantom carries the target's dump); it collapses to 0 when the channel false-positive rate is zeroed.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from rdd.oracle import Bug, Oracle
from rdd.sprt import Rep

# AirBugCatcher's esp32_bt native config.
MAX_FUZZED_PKTS = 3
MAX_TRY = 3


@dataclass(frozen=True)
class BaselineResult:
    reproduced: bool                 # the baseline credits the target crash as reproduced
    subset: frozenset | None         # the smallest reproducer it caught (its minimisation output)
    size: int | None                 # |subset|
    calls: int                       # device reads consumed for this bug


def _run_repro_session(oracle: Oracle, bug: Bug, subset, rng: random.Random, *,
                       max_try: int, decorrelate: bool) -> bool:
    """AirBugCatcher's ``run_exploit``: a fresh session per candidate, up to ``max_try`` trials that stop at the
    first non-crash or the first repeated crash id. Returns whether the target signature was seen. On a
    single-signature oracle this reduces to "the first read is YES"; the loop is kept for fidelity."""
    step = oracle.rep_session(bug, subset, rng, decorrelate=decorrelate)
    crash_ids: list[str] = []
    for _ in range(max_try):
        r = step()                                   # one device read
        if r is not Rep.YES:                         # NO or INVALID: no crash this trial
            break
        cid = bug.crash_sig                          # a reproduced read carries the bug's signature
        if any(cid == c for c in crash_ids):         # repeated crash id: stop
            break
        crash_ids.append(cid)
    return any(cid == bug.crash_sig for cid in crash_ids)   # desired_crash_found


def minimize(oracle: Oracle, bug: Bug, rng: random.Random, *,
             max_card: int = MAX_FUZZED_PKTS, max_try: int = MAX_TRY,
             decorrelate: bool = False, most_recent_first: bool = True, confirm: int = 0) -> BaselineResult:
    """AirBugCatcher's per-bug minimiser: increasing-cardinality ``combinations`` over the window (most-recent-first
    unless ``most_recent_first=False``), exact-subset dedup, stop at the first caught reproducer. ``confirm`` is
    not part of AirBugCatcher: it is the read-matched control, crediting a caught reproducer only after
    ``confirm`` further sessions reproduce it too; otherwise enumeration continues."""
    W = list(range(bug.window))
    if most_recent_first:                            # closest-to-crash first
        W = W[::-1]
    seen: set[frozenset] = set()
    calls0 = oracle.calls
    for k in range(1, max_card + 1):
        for comb in itertools.combinations(W, k):
            S = frozenset(comb)
            if S in seen:                            # exact-subset dedup
                continue
            seen.add(S)
            if _run_repro_session(oracle, bug, S, rng, max_try=max_try, decorrelate=decorrelate) and all(
                    _run_repro_session(oracle, bug, S, rng, max_try=max_try, decorrelate=decorrelate)
                    for _ in range(confirm)):
                return BaselineResult(True, S, k, oracle.calls - calls0)
    return BaselineResult(False, None, None, oracle.calls - calls0)
