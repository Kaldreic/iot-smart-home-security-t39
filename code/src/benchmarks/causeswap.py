"""benchmarks.causeswap — a Mode-2 CAUSE-SWAP demonstration of RDD's identity re-check.

RDD's identity guard (``rdd.minimizer`` ``identity_check``, getattr-probed from ``oracle.identity_truth`` in
``rdd.pipeline``) re-checks, at FINAL-VALIDATION, that the recovered recipe reproduces the TARGET bug's
identity -- not merely SOME crash. This module demonstrates the deployment the guard is FOR (its docstring:
"the final-validation ``raw`` confirms the recipe CRASHES, not that it crashes the TARGET"): a CO-PRESENT
multi-bug binary minimised under a CRASH-ONLY reproduction oracle, where a minimiser targeting bug X reduces
onto a DIFFERENT co-present bug Y, the crash-only ``raw_test`` credits the wrong-bug recipe as X, and the guard
DEMOTES it by parsing the REAL dump of the bug that actually fired. The co-present device (the oracle + its
crash-only in-loop + the guard's full-dump read) lives in ``emulation.causeswap``; this module owns the demo
arms + scoring and INJECTS the guard's real identity cascade (``benchmarks.identity_cache.id_l2l3``).

WHY a SEPARATE demo (and why the guard is a no-op elsewhere): the cached-real benchmark's in-loop oracle is
IDENTITY-AWARE -- ``benchmarks.identity_cache.id_l2l3`` runs INSIDE the reproduction loop, so a wrong-bug recipe is
rejected in-loop and the guard never has anything to demote (verified no-op). The guard's value appears only
when the in-loop reproduction is CRASH-ONLY -- a cheap crash/no-crash signal (exit code / watchdog) replayed
many times under SPRT, with the EXPENSIVE dump-identity check amortised to ONCE at final-validation (the
FrugalGPT cost-gating this project already uses for L3). This demo models exactly that deployment.

REAL vs MODELLED (the honesty boundary):
  * REAL: the A and C crash dumps are the committed Zephyr samples (``emulation.multibug.MODEL``, captured from
    build-multibug), and the GUARD's identity decision is made by the REAL identity cascade
    (``benchmarks.identity_cache.id_l2l3``): A (``ull_conn_update_parameters`` SIGFPE, has a stack) vs C (an ``LL_ASSERT``
    exit, no stack) is settled by L2 -- the dumps are too different for L3 to escalate (the correct FrugalGPT
    behaviour), so this demo exercises the guard's CAUSE-DISCRIMINATION, not L2/L3's robustness to dump VARIATION
    (which is the in-loop / l3_eval's domain). The reduction runs through the REAL pipeline (SPRT + robust minimiser).
  * MODELLED (disclosed): (1) the CO-PRESENCE of A and C in one PDU window -- the real build-multibug binary
    keeps A and C in SEPARATE per-bug harnesses on DISJOINT windows (a real cause-swap is not reachable on
    it without a C-level rebuild; that binary is also gitignored), but real firmware routinely ships co-present
    bugs in one image; (2) the in-loop reproduction is CRASH-ONLY -- it sees only a crash/no-crash BIT (NOT which
    bug), as in exit-code fuzzing; the GUARD, at final-validation, runs the binary ONCE and READS the FULL real
    dump of whatever fired, then ``id_l2l3`` INFERS the identity (cheap crash-only loop + one expensive full-dump
    guard -- the FrugalGPT cost-gating); (3) the OTA channel noise, as elsewhere. The in-loop is NOT identity-aware
    here BY DESIGN -- that is the precondition for the guard to be load-bearing (a verified no-op when it is, as on
    the cached-real benchmark whose in-loop ``id_l2l3`` runs every replay).

THE RESULT (per arm, guard OFF vs ON):
  * swap      (target A, the window's reachable crash is really C -- a co-present mis-target): guard OFF
    FALSE-CREDITS the C-recipe as an A reproduction; guard ON DEMOTES it (false_credit -> 0).
  * genuine_A (target A, reachable A) and genuine_C (target C, reachable C): the guard is a NO-OP -- it never
    reduces a genuine reproduction (demote-only, and the real dump matches the target).

  python -m benchmarks.causeswap [--seeds 30]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

import numpy as np

from benchmarks import identity_cache as idc
from benchmarks import scoring
from emulation.causeswap import _Bug, _CoPresentOracle, _NoGuardOracle, _WINDOW

# the three arms: (label, target bug, the bug actually reachable in the window)
_ARMS = [("swap", "A", "C"),                       # mis-target a co-present C crash as A -> the cause-swap
         ("genuine_A", "A", "A"),                  # correctly target A          -> guard is a no-op
         ("genuine_C", "C", "C")]                  # correctly target C          -> guard is a no-op


def _arm(target: str, reachable: str, seeds: list[int], guard: bool) -> dict:
    Oracle = _CoPresentOracle if guard else _NoGuardOracle
    bug, rows = _Bug(bug=target, crash_sig=f"bug-{target}"), []
    for s in seeds:
        o = Oracle(reachable=reachable, identity=idc.id_l2l3)   # inject the guard's real L2/L3 identity cascade
        rows.append(scoring.run_tool_campaign(o, [bug], random.Random(s), decorrelate=True)[0])
    g = lambda k: float(np.mean([float(bool(r.get(k))) for r in rows]))   # noqa: E731
    return {"genuine": g("true_reproduced"), "false_credit": g("false_credit"), "n": len(rows)}


def run(seeds: int = 30) -> dict:
    ss = list(range(seeds))
    out = {"suite": "causeswap", "n_seeds": seeds, "window": _WINDOW,
           "real": "A/C crash dumps + the GUARD's real identity cascade (L2 settles A-vs-C) + the pipeline (benchmarks.identity_cache + scoring)",
           "modelled": "A+C co-present in one window (real binary: separate per-bug harnesses) + a CRASH-ONLY "
                       "in-loop oracle that sees only a crash BIT (identity only at the guard, which reads the full dump)",
           "arms": {}}
    for label, target, reachable in _ARMS:
        out["arms"][label] = {"target": target, "reachable": reachable,
                              "guard_off": _arm(target, reachable, ss, guard=False),
                              "guard_on": _arm(target, reachable, ss, guard=True)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="benchmarks.causeswap",
                                 description="Mode-2 cause-swap guard demo on a co-present A+C deployment binary")
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--freeze", action="store_true", help="regenerate the committed reference (causeswap.json)")
    a = ap.parse_args()
    out = run(a.seeds)
    if a.freeze:
        ref = Path(__file__).resolve().parent / "data" / "reference" / "causeswap.json"
        ref.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
        print(f"  -> {ref}")
    print(f"=== Mode-2 cause-swap identity-guard demo — {a.seeds} seeds, co-present A+C window ===")
    print("  (REAL: A/C dumps + the guard's L2+L3 identity + the pipeline.  MODELLED: A+C co-present + a")
    print("   CRASH-ONLY in-loop oracle -- identity checked only at the guard, the case the guard is FOR.)")
    print(f"  {'arm':10} {'target->reachable':18} {'guard OFF g/fc':>16} {'guard ON g/fc':>16}")
    for label, m in out["arms"].items():
        off, on = m["guard_off"], m["guard_on"]
        print(f"  {label:10} {m['target']+' -> '+m['reachable']:18} "
              f"{off['genuine']:.3f}/{off['false_credit']:.3f}      "
              f"{on['genuine']:.3f}/{on['false_credit']:.3f}")
    sw = out["arms"]["swap"]
    print(f"  -> the guard DEMOTES the cause-swap: false_credit {sw['guard_off']['false_credit']:.3f} (OFF) "
          f"-> {sw['guard_on']['false_credit']:.3f} (ON); genuine arms unchanged (demote-only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
