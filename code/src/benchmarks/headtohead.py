"""benchmarks.headtohead — B1: the real-target head-to-head, AirBug vs RDD through the full shared pipeline.

The MAIN result. fuzz-campaign -> shared crash-grouping -> per-bug window -> [AirBug | RDD] minimiser -> PoC ->
score, on the real native_sim Zephyr targets. Both arms run over the IDENTICAL campaign, grouping, window,
channel and real device; ONLY the minimiser + its in-loop crash-identity differ, so the comparison isolates
the tool:
  * AirBug arm = the enum minimiser (benchmarks.baseline) + exact-id identity (emulation.baseline.exact_crash_id)
    -> DETERMINISTIC (a bit-reproducible point over a fixed seed set).
  * RDD arm    = the robust pipeline (rdd.minimize) + the live open-model L3 cascade (rdd.LiveL2L3Identity)
    -> reported as a RANGE over N=8 seeds; the live L3 verdicts are FROZEN to the committed cache so CI
    re-verifies a reproducible point.
Both arms drive the SAME real native_sim binary via one captured dump-model per target (built once, shared).

HONEST BOUNDARY (disclosed): the "real device" is the real Zephyr controller compiled to a native_sim ELF and
run via subprocess -- NOT a runtime container (Docker only builds it). The radio/OTA channel is MODELLED
(Gilbert-Elliott). The shared L2 crash-grouping is GENEROUS to the baseline (AirBug's real methodology uses a
weaker exact-id grouping), so RDD's win is conservative. Scored against the channel-off virtual-perfect the
minimiser never sees: genuine <=> the PoC PROVABLY crashes the RIGHT bug.

  python -m benchmarks.headtohead --traces 42 --seeds 8 --model llama3.1:8b   # the live head-to-head (needs Ollama)
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np

from benchmarks import live, scoring
from benchmarks.scenario import _BUGS, CrashDeduper, generate_campaign
from emulation import multibug
from emulation.baseline import exact_crash_id
from emulation.dump import DumpModel
from emulation.live import LiveBinaryOracle
from emulation.suppressor import LRBUG, LengthReqOracle
from rdd.identity import LiveL2L3Identity


def _setup_target(bug, *, model_name, host, judge, dump_params, memo):
    """Capture the real native_sim target ONCE and build the two arms over the SAME dump-model: the RDD oracle
    (live L2/L3 identity) and the AirBug oracle (exact-id identity). Returns (rdd_oracle, rdd_identity, ab_oracle)."""
    rdd_oracle, rdd_identity = live.build_live_campaign(bug, model=model_name, host=host, judge=judge,
                                                        dump_params=dump_params, memo=memo)
    ref_exact = exact_crash_id(rdd_oracle.model.clean_obs(bug))            # the captured clean dump's exact id

    def ab_identity(b, obs, _ref=ref_exact):                              # AirBug's is_same_crash_id (deterministic)
        return exact_crash_id(obs) == _ref
    ab_oracle = LiveBinaryOracle(rdd_oracle.binary, bug, ab_identity, rdd_oracle.model,
                                 crash_rc=rdd_oracle.crash_rc)
    return rdd_oracle, rdd_identity, ab_oracle


def _record(t, predicted, r, calls) -> dict:
    """Score one arm's run on one trace vs the channel-off virtual-perfect (already applied by score_bug):
    genuine <=> credited a PoC that provably crashes the CORRECTLY-deduped target; false_credit = soundness."""
    credited = bool(r.get("true_reproduced"))
    genuine = bool(credited and predicted == t.bug)
    return {"bug": t.bug, "predicted": predicted, "genuine": genuine,
            "false_credit": bool(r.get("false_credit")),
            "size_gap": float(r["size_gap"]) if (genuine and r.get("size_gap") is not None) else float("nan"),
            "reads": calls}


def _miss(t) -> dict:                                                      # dedup returned no family -> nothing minimised
    return {"bug": t.bug, "predicted": None, "genuine": False, "false_credit": False,
            "size_gap": float("nan"), "reads": 0}


def run_headtohead(n_traces: int = 42, *, seed: int = 0, model_name: str = "llama3.1:8b", host=None,
                   judge=None, dump_params=None, deduper=None, memo=None):
    """One campaign seed: synthesise traces, dedup-route each (shared), and run BOTH arms on the routed window
    of the real binary. Returns ({"airbug": rows, "rdd": rows}, confusion, setups)."""
    base_model = DumpModel.from_logs(multibug.LOGS, bugs=_BUGS, params=dump_params) if dump_params \
        else DumpModel.from_logs(multibug.LOGS, bugs=_BUGS)
    references = {b: base_model.clean_obs(b) for b in _BUGS}
    deduper = deduper if deduper is not None else CrashDeduper(references)
    rng = random.Random(seed)
    traces = generate_campaign(n_traces, base_model, rng)

    setups: dict = {}

    def setup_for(bug):
        if bug not in setups:
            setups[bug] = _setup_target(bug, model_name=model_name, host=host, judge=judge,
                                        dump_params=dump_params, memo=memo)
        return setups[bug]

    rows = {"airbug": [], "rdd": []}
    confusion = {b: {p: 0 for p in (*_BUGS, None)} for b in _BUGS}
    for i, t in enumerate(traces):
        predicted = deduper.classify(t.crash_obs)                         # SHARED crash-grouping (the tool sees only the log)
        confusion[t.bug][predicted] += 1
        if predicted is None:
            rows["airbug"].append(_miss(t)); rows["rdd"].append(_miss(t))
            continue
        rdd_oracle, _ri, ab_oracle = setup_for(predicted)
        bug_obj = live._Bug(bug=predicted, window=live._WINDOW[predicted], crash_sig=f"bug-{predicted}")
        trace_seed = seed * 131 + i                                       # SAME channel realisation for both arms (fair)
        rdd_oracle.calls = 0
        rr = dict(scoring.run_tool_campaign(rdd_oracle, [bug_obj], random.Random(trace_seed), decorrelate=True)[0])
        rows["rdd"].append(_record(t, predicted, rr, rdd_oracle.calls))
        ab_oracle.calls = 0
        ar = dict(scoring.run_baseline_campaign(ab_oracle, [bug_obj], random.Random(trace_seed), decorrelate=True)[0])
        rows["airbug"].append(_record(t, predicted, ar, ab_oracle.calls))
    return rows, confusion, setups


def _arm_summary(rows) -> dict:
    n = len(rows) or 1
    routed = [r for r in rows if r["predicted"] == r["bug"]]      # correctly-grouped traces = the minimiser's domain
    nr = len(routed) or 1
    gaps = [r["size_gap"] for r in rows if r["genuine"] and r["size_gap"] == r["size_gap"]]
    return {"genuine": sum(r["genuine"] for r in rows) / n,                    # end-to-end (deployment; gated by shared dedup)
            "genuine_routed": sum(r["genuine"] for r in routed) / nr,          # minimiser-isolated (on correctly-grouped traces)
            "false_credit": sum(r["false_credit"] for r in rows) / n,
            "dedup_accuracy": sum(r["predicted"] == r["bug"] for r in rows) / n,
            "exact_minimal": (sum(g == 0.0 for g in gaps) / len(gaps)) if gaps else float("nan"),
            "mean_size_gap": float(np.mean(gaps)) if gaps else float("nan"),
            "reads": float(np.mean([r["reads"] for r in rows])) if rows else float("nan")}


def _agg_seed(per, key):
    vs = [p[key] for p in per if p[key] == p[key]]
    return {"mean": float(np.mean(vs)), "min": float(min(vs)), "max": float(max(vs)), "n": len(vs)} if vs else None


def _record_direct(r, calls) -> dict:                                     # a non-campaign (direct) bug row
    genuine = bool(r.get("true_reproduced"))
    return {"bug": "LR", "predicted": "LR", "genuine": genuine, "false_credit": bool(r.get("false_credit")),
            "size_gap": float(r["size_gap"]) if (genuine and r.get("size_gap") is not None) else float("nan"),
            "reads": calls}


def run_suppressor_showcase(seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None, judge=None, memo=None) -> dict:
    """The one REAL non-monotone bug (LL_LENGTH_REQ), as a DIRECT head-to-head (no campaign/dedup): crash iff
    the interval=0 trigger is present AND LL_LENGTH_REQ is absent. AirBug's increasing-cardinality enum reaches
    the trigger but, on this non-monotone oracle, FALSE-CREDITS a non-crashing subset under channel noise and is
    less minimal; RDD stays sound (fc 0) + exact. (The dramatic 'bare ddmin SEED-bails to 0' result is the
    DDMIN-ONLY ablation in B3, not this AirBug-vs-RDD arm.) DISCLOSED: this target is TRUTH-TABLE-backed
    (Docker-captured), not a live native_sim subprocess; it emits bug A's real conn-update dump, so RDD's live
    L3 (shared memo) and AirBug's exact-id both judge bug-A dumps. Returns {airbug, rdd, l3_live} (rates over ``seeds``)."""
    ref = multibug.MODEL.clean_obs("A")
    ref_exact = exact_crash_id(ref)

    def ab_id(b, obs):
        return exact_crash_id(obs) == ref_exact

    per = {"airbug": [], "rdd": []}
    l3_live = 0
    for s in range(seeds):
        rdd_identity = LiveL2L3Identity({"A": ref}, model=model_name, host=host, memo=memo, judge=judge)
        ro = LengthReqOracle(identity=rdd_identity)
        rr = dict(scoring.run_tool_campaign(ro, [LRBUG], random.Random(s), decorrelate=True)[0])
        per["rdd"].append(_record_direct(rr, ro.calls))
        l3_live += rdd_identity.stats["l3_live"]
        ao = LengthReqOracle(identity=ab_id)
        ar = dict(scoring.run_baseline_campaign(ao, [LRBUG], random.Random(s), decorrelate=True)[0])
        per["airbug"].append(_record_direct(ar, ao.calls))
    return {"airbug": _arm_summary(per["airbug"]), "rdd": _arm_summary(per["rdd"]), "l3_live": l3_live}


def run(n_traces: int = 42, seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None,
        judge=None, dump_params=None, deduper=None, memo=None) -> dict:
    """Both arms over ``seeds`` campaign seeds. AirBug is a bit-reproducible point; RDD's live L3 makes its
    aggregate a RANGE (mean + [min,max] over seeds). The L3 verdict memo is SHARED across seeds/targets (each
    distinct dump pair judged once) so the caller can FREEZE it: pass an empty ``memo`` for a live run then
    persist it, or pre-load a complete ``memo`` (with a conservative-NO ``judge``) for a reproducible replay
    -- ``out['l3_live']`` is then 0. Returns per-arm aggregates (mean/min/max over seeds) + the live-call count."""
    memo = {} if memo is None else memo
    per = {"airbug": [], "rdd": []}
    l3_live = 0
    for s in range(seeds):
        rows, _conf, setups = run_headtohead(n_traces, seed=s, model_name=model_name, host=host,
                                             judge=judge, dump_params=dump_params, deduper=deduper, memo=memo)
        l3_live += sum(ri.stats["l3_live"] for (_ro, ri, _ao) in setups.values())
        for arm in per:
            per[arm].append(_arm_summary(rows[arm]))
    metrics = ("genuine", "genuine_routed", "false_credit", "dedup_accuracy", "exact_minimal", "mean_size_gap", "reads")
    out = {"suite": "headtohead", "n_traces": n_traces, "n_seeds": seeds, "l3_live": l3_live}
    for arm in per:
        out[arm] = {m: _agg_seed(per[arm], m) for m in metrics}
    supp = run_suppressor_showcase(seeds, model_name=model_name, host=host, judge=judge, memo=memo)
    out["suppressor"] = {"airbug": supp["airbug"], "rdd": supp["rdd"]}    # the real non-monotone showcase (rates)
    out["l3_live"] += supp["l3_live"]
    return out


_DATA = Path(__file__).resolve().parent / "data"
_CACHE = _DATA / "llm_cache" / "headtohead_l3.json"           # the frozen live-L3 verdicts (the reproducibility freeze)
_REF = _DATA / "reference" / "headtohead.json"               # the frozen B1 reference numbers


def freeze(n_traces: int = 42, seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None, judge=None,
           cache_path: Path = _CACHE, ref_path: Path = _REF) -> dict:
    """Run B1 LIVE (default judge = Ollama), capturing every L3 verdict, then PERSIST the memo + the reference.
    The committed memo lets CI replay a reproducible point; the reference is the frozen B1 result."""
    memo: dict = {}
    out = run(n_traces, seeds, model_name=model_name, host=host, judge=judge, memo=memo)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(memo, indent=1) + "\n")
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(json.dumps(out, indent=1) + "\n")
    return out


def frozen(n_traces: int = 42, seeds: int = 8, *, cache_path: Path = _CACHE) -> dict:
    """Reproduce B1 from the committed memo with NO live model: pre-load the complete memo + a conservative-NO
    guard judge (which must never fire if the memo is complete -> out['l3_live'] == 0)."""
    memo = json.loads(Path(cache_path).read_text())
    return run(n_traces, seeds, judge=lambda *a, **k: {"same": False}, memo=dict(memo))


def coherence(n_traces: int = 42, seeds: int = 8, tol: float = 1e-9) -> bool:
    """The FROZEN replay reproduces the committed reference EXACTLY (every leaf) and makes 0 live model calls.
    The top-level ``l3_live`` is skipped — the reference records the live-freeze count, a frozen replay is 0."""
    ref, fresh = json.loads(_REF.read_text()), frozen(n_traces, seeds)
    diffs = scoring.leaf_diffs(fresh, ref, tol=tol, skip_top=("l3_live",))
    ok = fresh["l3_live"] == 0 and not diffs
    print(f"B1 COHERENCE — frozen replay vs committed headtohead.json "
          f"(l3_live={fresh['l3_live']}, {len(diffs)} leaf diffs over the full reference):")
    for path, fv, rv in diffs[:25]:
        print(f"  [XX] {path}: fresh={fv} ref={rv}")
    print("COHERENT" if ok else "INCOHERENT")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(prog="benchmarks.headtohead",
                                 description="B1: AirBug vs RDD on the real native_sim targets via the full shared pipeline")
    ap.add_argument("--traces", type=int, default=42)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--host", default=None)
    ap.add_argument("--freeze", action="store_true", help="run LIVE + persist the memo + the reference (regenerate)")
    ap.add_argument("--frozen", action="store_true", help="reproduce from the committed memo (no live model)")
    ap.add_argument("--coherence", action="store_true", help="frozen replay must reproduce the committed reference")
    a = ap.parse_args()
    if a.coherence:
        return 0 if coherence(a.traces, a.seeds) else 1
    out = (freeze(a.traces, a.seeds, model_name=a.model, host=a.host) if a.freeze
           else frozen(a.traces, a.seeds) if a.frozen
           else run(a.traces, a.seeds, model_name=a.model, host=a.host))
    print(f"=== B1 head-to-head — {a.seeds} seeds x {a.traces} traces; real native_sim + live L3 ({a.model}) ===")
    print(f"  {'metric':16} {'AirBug (point)':>18} {'RDD (live range)':>26}")
    for m in ("genuine", "genuine_routed", "false_credit", "exact_minimal", "mean_size_gap", "reads"):
        ab, rd = out["airbug"][m], out["rdd"][m]
        ab_s = f"{ab['mean']:.3f}" if ab else "n/a"
        rd_s = f"{rd['mean']:.3f} [{rd['min']:.3f},{rd['max']:.3f}]" if rd else "n/a"
        print(f"  {m:16} {ab_s:>18} {rd_s:>26}")
    sp = out["suppressor"]
    print(f"  -- real non-monotone suppressor (LL_LENGTH_REQ, truth-table-backed): "
          f"AirBug genuine {sp['airbug']['genuine']:.3f} / fc {sp['airbug']['false_credit']:.3f}   "
          f"RDD genuine {sp['rdd']['genuine']:.3f} / fc {sp['rdd']['false_credit']:.3f}")
    print("  RDD = live open-model L3 (range over seeds; verdicts frozen to the cache for a reproducible CI point);")
    print("  AirBug = exact-id (bit-reproducible). Scored vs the channel-off virtual-perfect. native_sim + MODELLED channel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
