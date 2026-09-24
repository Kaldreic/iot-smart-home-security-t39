"""benchmarks.causeswap — a cause-swap demonstration of RDD's identity guard (Mode 2).

``rdd.minimizer`` re-checks at final validation that the recipe reproduces the target bug, not merely some
crash, through the oracle's optional ``identity_truth`` hook. This module runs the deployment the hook is
for: bugs A and C co-present in one window, minimised under a crash-only in-loop oracle (the loop sees a
crash/no-crash bit, not which bug fired), so a minimiser targeting A can converge onto C's recipe; the guard
reads the full dump of the bug that fired and demotes it.

Real: the A and C dumps (``emulation.multibug.MODEL``) and the guard's decision, made by the L2/L3 cascade
in ``benchmarks.identity_cache.id_l2l3`` (L2 settles A vs C). Modelled: the co-presence (the real binary keeps
A and C in separate harnesses), the crash-only in-loop oracle and the OTA channel; the device is
``emulation.causeswap``. On the cached-real benchmark the in-loop oracle is identity-aware, so the guard has
nothing to demote there. Arms: swap (target A, reachable C), genuine_A, genuine_C; each guard off and on.

  python -m benchmarks.causeswap [--seeds 30] [--freeze]
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

# (label, target bug, the bug that actually fires in the window)
_ARMS = [("swap", "A", "C"),                       # target A, only C fires: the cause-swap
         ("genuine_A", "A", "A"),                  # target A, A fires
         ("genuine_C", "C", "C")]                  # target C, C fires


def _arm(target: str, reachable: str, seeds: list[int], guard: bool) -> dict:
    Oracle = _CoPresentOracle if guard else _NoGuardOracle
    bug, rows = _Bug(bug=target, crash_sig=f"bug-{target}"), []
    for s in seeds:
        o = Oracle(reachable=reachable, identity=idc.id_l2l3)   # the guard's identity cascade
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
