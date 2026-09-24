"""benchmarks.scoring — evaluation glue, kept out of the tool surface: score a minimiser result against the
channel-off truth and run a whole campaign for either arm (the RDD tool or the AirBugCatcher baseline)."""

from __future__ import annotations

import os
import random

import rdd
from benchmarks import baseline
from rdd.oracle import Bug, Oracle


def require_hashseed0() -> None:
    """Exit with the remedy if a bit-reproducible run is launched without ``PYTHONHASHSEED=0``.

    The synthetic dump composition hashes bug ids (``emulation.synthetic.base_dump``) and Python randomises
    ``str`` hashing per process, so without the pinned seed the bug population, and every B2 and coherence
    number, differs run to run. Called by the hash-dependent CLIs (``benchmarks.run`` and
    ``benchmarks.resilience``); B1 and B3 drive the real binaries and do not hash."""
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit(
            "PYTHONHASHSEED=0 is required for a bit-reproducible run — the synthetic dump composition hashes "
            "bug ids (emulation.synthetic.base_dump), so without it the bug population (and every B2 / coherence "
            "number) differs run to run. Re-run with it set, e.g.:\n"
            "  PYTHONHASHSEED=0 python -m benchmarks.run coherence")


def score_bug(oracle: Oracle, bug: Bug, r) -> dict:
    """Score one result against the channel-off truth the minimiser never sees. Every arm is held to the same
    rule: genuine if the arm credited its recipe and the recipe crashes the target channel-off; false credit
    if it credited a recipe that does not. A recipe returned but not credited counts for neither."""
    gtm = oracle.ground_truth_minimals(bug)
    opt = min((len(m) for m in gtm), default=None)
    crashes = r.subset is not None and oracle.truth(bug, r.subset)
    return {
        "true_reproduced": bool(r.reproduced and crashes), "false_credit": bool(r.reproduced and not crashes),
        "size_gap": (r.size - opt) if (r.size is not None and opt is not None) else None,
        "calls": r.calls,
    }


def run_tool_campaign(oracle, bugs: list, rng: random.Random, **kw) -> list[dict]:
    """Run the RDD tool over every bug; rows scored by ``score_bug``, plus the tool's cache-hit count."""
    rows = []
    for bug in bugs:
        r = rdd.minimize(oracle, bug, rng, **kw)
        row = score_bug(oracle, bug, r)
        row["cache_hits"] = r.cache_hits
        rows.append(row)
    return rows


def run_baseline_campaign(oracle: Oracle, bugs: list[Bug], rng: random.Random, *,
                          max_card: int = baseline.MAX_FUZZED_PKTS, max_try: int = baseline.MAX_TRY,
                          decorrelate: bool = False, most_recent_first: bool = True, confirm: int = 0) -> list[dict]:
    """Run the AirBugCatcher baseline over every bug; rows scored by ``score_bug``. ``confirm`` > 0 is the
    read-matched control: a caught reproducer must reproduce that many more times before it is credited."""
    return [score_bug(oracle, bug, baseline.minimize(oracle, bug, rng, max_card=max_card, max_try=max_try,
            decorrelate=decorrelate, most_recent_first=most_recent_first, confirm=confirm)) for bug in bugs]


def clean_nan(o):
    """Serialise NaN (an empty-genuine mean or CI bound) as JSON null, so a written reference is valid JSON and
    coherence compares null with null after the same cleaning."""
    if isinstance(o, float):
        return None if o != o else o
    if isinstance(o, dict):
        return {k: clean_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_nan(v) for v in o]
    return o


def leaf_diffs(fresh, ref, *, path: str = "", tol: float = 1e-9, skip_top: tuple = ()) -> list:
    """Recursive leaf comparison of a NaN-cleaned result against the committed reference; the coherence gate of
    B1, B2 and B3. A numeric leaf matches within ``tol``, a null leaf must stay null, bools and strings match
    exactly, and a list leaf (B2's ``[mean, lo, hi]``) must match element for element. ``skip_top`` names
    top-level keys to ignore (a frozen replay's ``l3_live`` is 0 while the reference records the live-freeze
    count). Returns the ``(path, fresh, ref)`` mismatches; empty means coherent."""
    diffs = []
    if isinstance(ref, dict):
        for k in ref:
            if path == "" and k in skip_top:
                continue
            diffs += leaf_diffs((fresh or {}).get(k) if isinstance(fresh, dict) else None, ref[k],
                                path=f"{path}.{k}" if path else k, tol=tol, skip_top=skip_top)
    elif isinstance(ref, bool):
        if fresh is not ref:
            diffs.append((path, fresh, ref))
    elif isinstance(ref, (int, float)):
        if not (isinstance(fresh, (int, float)) and not isinstance(fresh, bool)
                and abs(float(fresh) - float(ref)) <= tol):
            diffs.append((path, fresh, ref))
    elif ref is None:                                            # a NaN-as-null leaf must stay null
        if fresh is not None:
            diffs.append((path, fresh, ref))
    elif fresh != ref:
        diffs.append((path, fresh, ref))
    return diffs
