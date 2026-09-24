"""benchmarks.run — the CLI over the benchmark suite.

  python -m benchmarks.run b1|b2|b3 [flags]   # dispatch to benchmarks.headtohead / resilience / levers
  python -m benchmarks.run coherence          # the model-free gate: the anchor (+/-0.02) and B2 (leaf-exact)
  python -m benchmarks.run sensitivity        # the anchor with the report-variation / phantom-crash models off
  python -m benchmarks.run freeze             # regenerate data/reference/anchor.json

The anchor is the model-free truth-table reproduction of the six real bugs A-F and the LL_LENGTH_REQ
suppressor (``run_real`` / ``run_suppressor``): arms baseline, baseline_confirm, tool, ablation and oracle,
with the tool's L3 served from the committed cache. B1 and B3 need the built binaries; the self-test
reproduces them where the binaries exist. Run after ``pip install -e code/`` with PYTHONHASHSEED=0.
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


def run_real(seeds: int = 30, ablate: bool = False, *, params=None, dump_params=None) -> dict:
    """The six Zephyr bugs A-F on the truth-table oracle: baseline, baseline_confirm and tool, plus ablation
    (ddmin only) and oracle (ddmin + exact-id) when ``ablate``. ``params`` / ``dump_params`` override the
    channel and the report-variation model."""
    bugs, ss = list(real.BUGS), list(range(seeds))
    model_params = real.MODEL.params
    real.MODEL.params = dump_params or model_params
    try:
        out = {"suite": "real", "n_seeds": seeds, "bugs": bugs,
               "baseline": idc.agg(real._run(scoring.run_baseline_campaign, real.id_exact, bugs, ss, params=params)),
               "baseline_confirm": idc.agg(real._run(scoring.run_baseline_campaign, real.id_exact, bugs, ss,
                                                     params=params, confirm=1))}
        idc.l3_reset()                                        # attribute the tool arm's L3 provenance
        out["tool"] = idc.agg(real._run(scoring.run_tool_campaign, idc.id_l2l3, bugs, ss, params=params, decorrelate=True))
        out["l3_provenance"] = idc.l3_provenance()
        if ablate:
            out["ablation"] = idc.agg(real._run(scoring.run_tool_campaign, idc.id_l2l3, bugs, ss, params=params,
                                                decorrelate=True, ablate_robust=True))
            out["oracle"] = idc.agg(real._run(scoring.run_tool_campaign, real.id_exact, bugs, ss, params=params,
                                              decorrelate=True, ablate_robust=True))
    finally:
        real.MODEL.params = model_params
    return out


def run_suppressor(seeds: int = 30, ablate: bool = False) -> dict:
    """The real LL_LENGTH_REQ suppressor (non-monotone) on its truth-table oracle; arms as ``run_real``."""
    ss = list(range(seeds))

    def go(mod, identity, **kw):
        rows = []
        for s in ss:
            o = suppressor.LengthReqOracle(identity=identity)
            r = dict(mod(o, [suppressor.LRBUG], random.Random(s), **kw)[0])
            r["reads"] = o.calls
            rows.append(r)
        return idc.agg(rows)

    out = {"suite": "suppressor", "n_seeds": seeds, "true_minimal": [3],
           "baseline": go(scoring.run_baseline_campaign, real.id_exact),
           "baseline_confirm": go(scoring.run_baseline_campaign, real.id_exact, confirm=1)}
    idc.l3_reset()
    out["tool"] = go(scoring.run_tool_campaign, idc.id_l2l3, decorrelate=True)
    out["l3_provenance"] = idc.l3_provenance()
    if ablate:
        out["ablation"] = go(scoring.run_tool_campaign, idc.id_l2l3, decorrelate=True, ablate_robust=True)
    return out


def _metric(m):
    """An arm's genuine rate from an ``idc.agg`` result."""
    return m["genuine"]


_ANCHOR = _REF / "anchor.json"
_GATED = {"real": ("baseline", "baseline_confirm", "tool"), "suppressor": ("baseline", "baseline_confirm", "tool", "ablation")}


def freeze(seeds: int = 30) -> dict:
    """Regenerate data/reference/anchor.json: the real bugs and the suppressor, every gated arm, with the L3
    provenance the gate checks."""
    out = {"real": run_real(seeds), "suppressor": run_suppressor(seeds, ablate=True)}
    _ANCHOR.write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n", encoding="utf-8")
    return out


def coherence(tol: float = 0.02) -> bool:
    """True iff a fresh anchor reproduces the committed anchor.json: genuine and false credit of every gated arm
    within ``tol``, and the tool's L3 provenance equal (live_calls == 0 and the same cache-hit / rule-fallback
    counts, so a drifted cache is detected)."""
    ref = json.loads(_ANCHOR.read_text(encoding="utf-8"))
    fresh = {"real": run_real(30), "suppressor": run_suppressor(30, ablate=True)}
    print(f"COHERENCE — fresh anchor vs committed anchor.json (tol +/-{tol:.3f}):")
    ok = True
    for part, arms in _GATED.items():
        for arm in arms:
            for k in ("genuine", "false_credit"):
                f, r = fresh[part][arm][k], ref[part][arm][k]
                good = abs(f - r) <= tol
                ok = ok and good
                print(f"  [{'OK' if good else 'XX'}] {part:10} {arm:17} {k:12} fresh={f:.3f} ref={r:.3f} delta={abs(f - r):.3f}")
        fp, rp = fresh[part]["l3_provenance"], ref[part]["l3_provenance"]
        good = (fp == rp) and (fp.get("live_calls") == 0)
        ok = ok and good
        print(f"  [{'OK' if good else 'XX'}] {part:10} l3_provenance == committed ({fp.get('source')}, live_calls="
              f"{fp.get('live_calls')}, cache_hits={fp.get('cache_hits')}, rule_no={fp.get('rule_no_fallback')})"
              + ("" if good else f"  fresh={fp} ref={rp}"))
    print("COHERENT" if ok else "INCOHERENT")
    return ok


def sensitivity(seeds: int = 30) -> None:
    """How much of the anchor result is the noise model: genuine / false credit / reads of the baseline, the
    confirmation control and the tool, with the committed noise, with report variation off, with phantom
    crashes off, and with both off."""
    from dataclasses import replace
    from emulation.channel import GEChannelParams
    from emulation.dump import DumpParams
    base = GEChannelParams()
    settings = [("committed noise model", None, None),
                ("report variation off", None, DumpParams(p_truncate=0, p_lose_top=0, p_perturb=0, p_lognoise=0, p_garble=0, addr_jitter=False)),
                ("phantom crashes off", replace(base, p_fp_good=0.0, p_fp_bad=0.0), None),
                ("both off", replace(base, p_fp_good=0.0, p_fp_bad=0.0),
                 DumpParams(p_truncate=0, p_lose_top=0, p_perturb=0, p_lognoise=0, p_garble=0, addr_jitter=False))]
    print(f"NOISE SENSITIVITY — the six real bugs, {seeds} runs each; cell = genuine / false credit / reads")
    print(f"  {'setting':24} {'baseline':>22} {'baseline + 1 confirm':>22} {'RDD':>22}")
    for name, params, dp in settings:
        out = run_real(seeds, params=params, dump_params=dp)
        cell = lambda m: f"{m['genuine']:.3f} / {m['false_credit']:.3f} / {m['reads']:5.1f}"
        print(f"  {name:24} {cell(out['baseline']):>22} {cell(out['baseline_confirm']):>22} {cell(out['tool']):>22}")


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("b1", "b2", "b3"):               # dispatch to the b1/b2/b3 module; flags pass through
        from benchmarks import headtohead, levers, resilience
        mod = {"b1": headtohead, "b2": resilience, "b3": levers}[argv[0]]
        sys.argv = [f"benchmarks.{argv[0]}", *argv[1:]]      # drop the subcommand token: the module parses its own flags
        return mod.main()
    ap = argparse.ArgumentParser(prog="benchmarks.run",
                                 description="b1|b2|b3 = the 3 headlines; coherence = the model-free gate "
                                             "(the real anchor + B2); sensitivity = the anchor under weaker noise; "
                                             "freeze = regenerate anchor.json",
                                 epilog="headline subcommands: 'b1', 'b2', 'b3' (e.g. 'python -m benchmarks.run "
                                        "b1 --frozen') dispatch to the headtohead / resilience / levers modules.")
    ap.add_argument("suite", choices=["coherence", "sensitivity", "freeze"])
    a = ap.parse_args()
    if a.suite == "sensitivity":
        sensitivity()
        return 0
    if a.suite == "freeze":
        freeze()
        print(f"  -> {_ANCHOR}")
        return 0
    scoring.require_hashseed0()                               # coherence runs B2, which hashes bug ids
    from benchmarks import resilience                         # the model-free gate: the anchor + B2
    ok = coherence()
    ok = resilience.coherence() and ok
    print("  (B1 + B3 are binary-gated -- the self-test reproduces them where the host-native binaries are built.)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
