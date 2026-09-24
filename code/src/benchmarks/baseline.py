"""benchmarks.baseline — a FAITHFUL reimplementation of AirBugCatcher's native minimiser (the baseline arm).

The competing reduction ARM, peer of the RDD tool (rdd.minimizer): the benchmark's head-to-head drives this
against RDD over the same injected oracle. It depends only on the tool's oracle Protocol (rdd.oracle / rdd.sprt),
never on the device — the exact-id crash matcher it conceptually uses (AirBugCatcher's is_same_crash_id) is shared
device infra and lives in emulation.baseline.exact_crash_id.

Mechanism (the esp32_bt config: ``max_fuzzed_pkts=3``, ``max_try=3``):

  * **Candidate generation = brute increasing-cardinality subset enumeration, NOT ddmin.**
    It enumerates ``combinations`` over a bounded backward window in increasing cardinality,
    MOST-RECENT-FIRST -- the "packets closer to the crash fire it" locality heuristic. We honour
    it (``most_recent_first=True``): on this tail-biased-minimal oracle it roughly HALVES the
    FP-driven false-credit rate vs naive index-order, so enumerating index-first would strawman it.
  * **Exact-subset dedup.** A candidate whose hash was already run is skipped, so a subset is
    tried at most once and its (possibly noise-corrupted) verdict is permanent.
  * **Stop on first desired reproduction.** Combined with increasing cardinality, this reports the
    SMALLEST catchable reproducer.
  * **Fixed-K reproduction that is NOT an FN defence.** The ``max_try`` loop breaks on the first
    non-crash trial and on a duplicate crash_id: the trials GATHER DISTINCT CRASH STATES, they do
    not re-sample to beat a flaky false-negative. On a single-signature bug a candidate therefore
    gets ONE effective reproduction attempt -- the baseline overcomes channel FN only by trying
    MANY candidates, never by re-sampling one (the fixed mechanism RDD's adaptive SPRT contrasts with).

This is AirBugCatcher's real control flow with its real crash-id matching. One disclosed, symmetric
simplification: cross-bug *session* reuse is out of scope -- the oracle gives each bug an INDEPENDENT
packet window, so cross-bug accidental triggering cannot occur for either arm. Faithful to this
oracle, the paper's minimal-size law is 1-3, so ``max_fuzzed_pkts=3`` always *contains* the true
minimal -- the baseline's misses are FN-driven, not cardinality-driven.

WHY IT MATTERS. Channel-off, ``combinations`` recovers the exact true 1-minimal for every bug. Under
the calibrated channel the baseline *claims* near-total reproduction but genuinely reproduces far less
and FALSE-CREDITS the rest -- it accepts the first positive read without re-sampling. The false credit
is FP-driven (it collapses to 0 when the channel false-positive rate is zeroed) and burstiness-
invariant (each subset is read at most twice, so the first read decides). This is exactly the
fixed-mechanism weakness RDD's adaptive SPRT is designed to remove.

Driven by ``benchmarks.scoring.run_baseline_campaign`` (the baseline arm of every head-to-head).
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
    calls: int                       # device reads consumed for this bug (the overhead currency)


def _run_repro_session(oracle: Oracle, bug: Bug, subset, rng: random.Random, *,
                       max_try: int, decorrelate: bool) -> bool:
    """Faithful ``run_exploit``: a FRESH OTA session per candidate (within-session reps correlated
    via ``rep_session``); accumulate DISTINCT crash_ids; break on the first non-crash trial or the
    first duplicate. Returns ``desired_crash_found`` (is the target signature among them?).

    On this single-signature oracle a reproduced read always carries ``bug.crash_sig``, so the loop
    collapses to "the first read is YES" -- the faithful consequence of breaking on the first
    non-crash trial (no re-sampling to beat an FN). The full loop is kept for fidelity."""
    step = oracle.rep_session(bug, subset, rng, decorrelate=decorrelate)
    crash_ids: list[str] = []
    for _ in range(max_try):
        r = step()                                   # one device read (counts an oracle call)
        if r is not Rep.YES:                         # NO or INVALID = no crash this trial -> stop
            break
        cid = bug.crash_sig                          # a reproduced read carries the bug's real sig
        if any(cid == c for c in crash_ids):         # repeat crash_id -> stop (gathers STATES only)
            break
        crash_ids.append(cid)
    return any(cid == bug.crash_sig for cid in crash_ids)   # desired_crash_found (is_same_crash_id)


def minimize(oracle: Oracle, bug: Bug, rng: random.Random, *,
             max_card: int = MAX_FUZZED_PKTS, max_try: int = MAX_TRY,
             decorrelate: bool = False, most_recent_first: bool = True, confirm: int = 0) -> BaselineResult:
    """AirBugCatcher's per-bug minimiser: increasing-cardinality ``combinations`` over the window,
    exact-subset dedup, stop at the first caught reproducer (hence smallest size). ``combinations``
    runs over the window MOST-RECENT-FIRST, the locality heuristic that matters (see module
    docstring); ``most_recent_first=False`` is the naive index order, kept only to demonstrate the
    heuristic's effect. ``confirm`` is NOT part of AirBugCatcher: it is the read-matched control used
    in the evaluation -- a caught reproducer is credited only after ``confirm`` further sessions reproduce
    it too, otherwise enumeration continues."""
    W = list(range(bug.window))
    if most_recent_first:                            # closest-to-crash first
        W = W[::-1]
    seen: set[frozenset] = set()
    calls0 = oracle.calls
    for k in range(1, max_card + 1):
        for comb in itertools.combinations(W, k):
            S = frozenset(comb)
            if S in seen:                            # exact-subset dedup (file-hash skip)
                continue
            seen.add(S)
            if _run_repro_session(oracle, bug, S, rng, max_try=max_try, decorrelate=decorrelate) and all(
                    _run_repro_session(oracle, bug, S, rng, max_try=max_try, decorrelate=decorrelate)
                    for _ in range(confirm)):
                return BaselineResult(True, S, k, oracle.calls - calls0)
    return BaselineResult(False, None, None, oracle.calls - calls0)
