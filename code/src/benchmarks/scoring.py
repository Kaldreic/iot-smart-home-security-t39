"""benchmarks.scoring — evaluation glue (Module 3, kept out of the tool surface): score a minimiser
result against the channel-off virtual-perfect (genuine vs false-credit + size-gap), and run a whole
campaign for either arm -- the RDD tool or the AirBugCatcher baseline."""

from __future__ import annotations

import os
import random

import rdd
from benchmarks import baseline
from rdd.oracle import Bug, Oracle


def require_hashseed0() -> None:
    """Fail LOUD (with the remedy) if a bit-reproducible run is launched without ``PYTHONHASHSEED=0``.

    The synthetic dump composition hashes bug ids (``emulation.synthetic.base_dump``), and Python randomises
    ``str`` hashing per process unless the seed is pinned — so without ``PYTHONHASHSEED=0`` the bug population,
    and every B2 / coherence number, differs run to run. CI sets it; this turns a LOCAL reproduction run that
    forgets it into a clear actionable error instead of a silently-wrong ``INCOHERENT``. Called from the
    hash-dependent CLI gates (``benchmarks.run`` coherence + ``benchmarks.resilience``); B1/B3 drive the real
    binaries and never hash, so their CLIs don't call it."""
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit(
            "PYTHONHASHSEED=0 is required for a bit-reproducible run — the synthetic dump composition hashes "
            "bug ids (emulation.synthetic.base_dump), so without it the bug population (and every B2 / coherence "
            "number) differs run to run. Re-run with it set, e.g.:\n"
            "  PYTHONHASHSEED=0 python -m benchmarks.run coherence")


def score_bug(oracle: Oracle, bug: Bug, r) -> dict:
    """Score one result against the channel-off ground truth the minimiser never sees. Both arms are held
    to the same rule: a reproduction is *genuine* only if the arm credited its recipe AND the recipe crashes
    the target channel-off; it is a *false credit* if the arm credited a recipe that does not. A recipe the
    tool returned but refused to validate counts for neither."""
    gtm = oracle.ground_truth_minimals(bug)
    opt = min((len(m) for m in gtm), default=None)
    crashes = r.subset is not None and oracle.truth(bug, r.subset)
    return {
        "true_reproduced": bool(r.reproduced and crashes), "false_credit": bool(r.reproduced and not crashes),
        "size_gap": (r.size - opt) if (r.size is not None and opt is not None) else None,
        "calls": r.calls,
    }


def run_tool_campaign(oracle, bugs: list, rng: random.Random, **kw) -> list[dict]:
    """Run the RDD tool over every bug; rows scored by ``score_bug`` (the identical scorer the baseline
    uses, so the head-to-head compares like with like) plus the robust extras."""
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
    """Run the AirBugCatcher baseline over every bug; per-bug scored rows. ``confirm`` > 0 is the
    read-matched control: a caught reproducer must reproduce again that many times before it is credited."""
    return [score_bug(oracle, bug, baseline.minimize(oracle, bug, rng, max_card=max_card, max_try=max_try,
            decorrelate=decorrelate, most_recent_first=most_recent_first, confirm=confirm)) for bug in bugs]


def clean_nan(o):
    """Serialise NaN (an empty-genuine arm mean / bootstrap CI) as JSON null so a written reference is
    RFC-valid JSON and coherence compares null==null after the same cleaning."""
    if isinstance(o, float):
        return None if o != o else o
    if isinstance(o, dict):
        return {k: clean_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_nan(v) for v in o]
    return o


def leaf_diffs(fresh, ref, *, path: str = "", tol: float = 1e-9, skip_top: tuple = ()) -> list:
    """Recursive leaf compare of a fresh (NaN-cleaned) result vs the committed reference — the shared
    coherence gate of every headline (B1/B2/B3). Gates EVERY published number (every arm x metric x
    range/CI bound), not a hand-picked subset; a scalar numeric leaf matches within ``tol``, a NaN-as-null
    leaf must stay null, bools/strings match exactly, and a LIST leaf (B2's ``[mean, lo, hi]`` triples) must
    match element-for-element exactly (no tolerance). ``skip_top`` names TOP-LEVEL keys to ignore — a frozen
    replay's ``l3_live`` is correctly 0 while the reference records the live-freeze count. Returns the list
    of ``(path, fresh, ref)`` mismatches (empty == coherent)."""
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
