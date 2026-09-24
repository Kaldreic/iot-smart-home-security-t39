"""benchmarks.run — the ONE CLI over the benchmark suite (the 3 headlines + the model-free gate).

  python -m benchmarks.run b1|b2|b3 [flags]   # the 3 HEADLINES (dispatch to benchmarks.headtohead / resilience / levers):
                                              #   b1 = real head-to-head, b2 = synthetic resilience, b3 = lever decomposition
  python -m benchmarks.run coherence          # the MODEL-FREE reproducibility gate: the real anchor (+/-0.02) + B2 (leaf-exact)
                                              #   (B1 + B3 are binary-gated -> the self-test reproduces them where the binaries are built)

Run after `pip install -e code/`. The gate's "real anchor" is the model-free truth-table reproduction of the
6 real bugs (A-F) + the LL_LENGTH_REQ suppressor (``run_real`` / ``run_suppressor`` below); its preserved arms
are exact (the baseline IS AirBugCatcher's minimiser, the tool IS the locked robust pipeline), so ``coherence``
reproduces the committed real genuine rates (gated at +/-0.02; delta 0.000 in practice) and B2 leaf-exactly.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from benchmarks import identity_cache as idc
from benchmarks import scoring

from . import real
from emulation import suppressor

_REF = Path(__file__).resolve().parent / "data" / "reference"


def run_real(seeds: int = 30, ablate: bool = False) -> dict:
    bugs, ss = list(real.BUGS), list(range(seeds))
    baseline = idc.agg(real._run(scoring.run_baseline_campaign, real.id_exact, bugs, ss))   # exact-id arm: no L3
    idc.l3_reset()                                           # attribute the TOOL arm's L3 sourcing (the real anchor)
    tool = idc.agg(real._run(scoring.run_tool_campaign, idc.id_l2l3, bugs, ss, decorrelate=True))
    out = {"suite": "real", "n_seeds": seeds, "bugs": bugs, "baseline": baseline, "tool": tool,
           "l3_provenance": idc.l3_provenance()}              # cached open-model: live_calls==0, reproduces from cache
    if ablate:
        out["ablation"] = idc.agg(real._run(scoring.run_tool_campaign, idc.id_l2l3, bugs, ss,
                                            decorrelate=True, ablate_robust=True))
        # oracle = exact-id + SPRT + ddmin-only. fc lever = the pipeline oracle/gate (fc 0 for oracle/ablation/tool,
        # fc>0 only in the fixed-K baseline); IDENTITY genuine lever = oracle->ablation (exact-id -> L2/L3).
        out["oracle"] = idc.agg(real._run(scoring.run_tool_campaign, real.id_exact, bugs, ss,
                                         decorrelate=True, ablate_robust=True))
    return out


def run_suppressor(seeds: int = 30, ablate: bool = False) -> dict:
    ss = list(range(seeds))

    def go(mod, identity, **kw):
        rows = []
        for s in ss:
            o = suppressor.LengthReqOracle(identity=identity)
            r = dict(mod(o, [suppressor.LRBUG], random.Random(s), **kw)[0])
            r["reads"] = o.calls
            rows.append(r)
        return idc.agg(rows)

    baseline = go(scoring.run_baseline_campaign, real.id_exact)               # exact-id arm: no L3
    idc.l3_reset()                                           # attribute the TOOL arm's L3 sourcing
    out = {"suite": "suppressor", "n_seeds": seeds, "true_minimal": [3], "baseline": baseline,
           "tool": go(scoring.run_tool_campaign, idc.id_l2l3, decorrelate=True),
           "l3_provenance": idc.l3_provenance()}
    if ablate:
        out["ablation"] = go(scoring.run_tool_campaign, idc.id_l2l3, decorrelate=True, ablate_robust=True)
    return out


def _metric(m):
    """The genuine-recovery value from an arm's idc.agg result (a plain float)."""
    return m["genuine"]


def coherence(tol: float = 0.02) -> bool:
    """The fresh real + suppressor suite reproduces the COMMITTED reference for the PRESERVED arms: the
    baseline == arm_a (byte-identical to AirBugCatcher's minimiser) and the tool == arm_b_plus (the locked
    robust pipeline), on realbench_robust.json over the 6 real bugs (A-F) + the real suppressor (where the
    ablation must BAIL == arm_b). Gates ``genuine`` (the soundness-bearing quantity; size_gap/reads are
    efficiency metrics, not gated). ALSO gates the cached-real L3-source provenance: the path is LIVE-FREE
    (live_calls==0) and its cache-hit / conservative-NO-rule breakdown reproduces EXACTLY from the frozen
    cache (integer counts, equality-gated). The unified `python -m benchmarks.run coherence` ALSO re-runs
    the B2 synthetic sweep (`benchmarks.resilience --coherence`'s exact model-free gate) -- one command gates both."""
    ref = json.loads((_REF / "realbench_robust.json").read_text(encoding="utf-8"))
    p1, p2 = ref["part1_real_monotone"], ref["part2_real_lengthreq_suppressor"]
    fr, fs = run_real(30), run_suppressor(30, ablate=True)
    checks = [
        ("real  baseline.genuine == arm_a",      _metric(fr["baseline"]), p1["arm_a"]["genuine"]),
        ("real  tool.genuine     == arm_b_plus", _metric(fr["tool"]),     p1["arm_b_plus"]["genuine"]),
        ("supp  baseline.genuine == arm_a",      _metric(fs["baseline"]), p2["arm_a"]["genuine"]),
        ("supp  tool.genuine     == arm_b_plus", _metric(fs["tool"]),     p2["arm_b_plus"]["genuine"]),
        ("supp  ablation BAILS   == arm_b",      _metric(fs["ablation"]), p2["arm_b"]["genuine"]),
    ]
    print(f"COHERENCE — fresh real+suppressor suite vs committed realbench_robust.json (tol +/-{tol:.3f}):")
    ok = True
    for name, fresh, refv in checks:
        d = abs(fresh - refv)
        good = d <= tol
        ok = ok and good
        print(f"  [{'OK' if good else 'XX'}] {name}: fresh={fresh:.3f} ref={refv:.3f} delta={d:.3f}")
    # L3-source provenance: the cached-real paths are LIVE-FREE (live_calls==0, structural) and their
    # cache-hit/rule-NO breakdown reproduces EXACTLY (the committed 164/40 counts detect any L3 cache drift).
    for tag, fp, rp in (("real", fr["l3_provenance"], p1.get("l3_provenance")),
                        ("supp", fs["l3_provenance"], p2.get("l3_provenance"))):
        good = (fp == rp) and (fp.get("live_calls") == 0)
        ok = ok and good
        print(f"  [{'OK' if good else 'XX'}] {tag}  l3_provenance == committed ({fp.get('source')}, "
              f"live_calls={fp.get('live_calls')}, cache_hits={fp.get('cache_hits')}, "
              f"rule_no={fp.get('rule_no_fallback')})" + ("" if good else f"  fresh={fp} ref={rp}"))
    print("COHERENT" if ok else "INCOHERENT")
    return ok


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("b1", "b2", "b3"):               # dispatch to the headline module; flags pass through
        from benchmarks import headtohead, levers, resilience
        mod = {"b1": headtohead, "b2": resilience, "b3": levers}[argv[0]]
        sys.argv = [f"benchmarks.{argv[0]}", *argv[1:]]      # drop the subcommand token: the module parses its own flags
        return mod.main()
    ap = argparse.ArgumentParser(prog="benchmarks.run",
                                 description="b1|b2|b3 = the 3 headlines; coherence = the model-free gate "
                                             "(the real anchor + B2, exact and binary-free)",
                                 epilog="headline subcommands: 'b1', 'b2', 'b3' (e.g. 'python -m benchmarks.run "
                                        "b1 --frozen') dispatch to the headtohead / resilience / levers modules.")
    ap.add_argument("suite", choices=["coherence"])
    ap.parse_args()
    scoring.require_hashseed0()                               # the B2 half of the gate hashes bug ids -> needs seed 0
    from benchmarks import resilience                         # the unified MODEL-FREE gate: real anchor + B2
    ok = coherence()                                         # the real anchor (cached-L3, model-free)
    ok = resilience.coherence() and ok                       # B2 (exact, model-free)
    print("  (B1 + B3 are binary-gated -- the self-test reproduces them where the host-native binaries are built.)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
