"""benchmarks.headtohead — B1: AirBugCatcher vs RDD on the real host-native Zephyr targets.

Pipeline: fuzz campaign -> crash grouping -> per-bug window -> [AirBugCatcher | RDD] minimiser -> PoC -> score. Both
arms see the same campaign, L2 crash grouping (AirBugCatcher itself groups by exact id), window, channel
realisation and binary; only the minimiser and its in-loop crash identity differ. The AirBugCatcher arm
(``benchmarks.baseline`` + ``exact_crash_id``) is deterministic; ``airbug_confirm`` is the read-matched
control (one confirming re-run). The RDD arm (``rdd.minimize`` + ``rdd.LiveL2L3Identity``) calls the open
model live, so it is reported as a range over seeds; its L3 verdicts are frozen to
data/llm_cache/headtohead_l3.json so the frozen replay is reproducible. Every arm is scored by
``scoring.score_bug`` against the channel-off truth.

The "device" is the Zephyr controller compiled to a host-native ELF and run via subprocess; the radio/OTA
channel is modelled (Gilbert-Elliott).

  python -m benchmarks.headtohead --traces 42 --seeds 8 --model llama3.1:8b   # live (needs Ollama)
  python -m benchmarks.headtohead --frozen | --coherence | --refreeze          # from the committed memo
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
    """Capture the target once and build both arms over the same dump model: the RDD oracle (live L2/L3
    identity) and the AirBugCatcher oracle (exact-id identity). Returns (rdd_oracle, rdd_identity, ab_oracle)."""
    rdd_oracle, rdd_identity = live.build_live_campaign(bug, model=model_name, host=host, judge=judge,
                                                        dump_params=dump_params, memo=memo)
    ref_exact = exact_crash_id(rdd_oracle.model.clean_obs(bug))            # the captured clean dump's exact id

    def ab_identity(b, obs, _ref=ref_exact):                              # AirBugCatcher's is_same_crash_id
        return exact_crash_id(obs) == _ref
    ab_oracle = LiveBinaryOracle(rdd_oracle.binary, bug, ab_identity, rdd_oracle.model,
                                 crash_rc=rdd_oracle.crash_rc)
    return rdd_oracle, rdd_identity, ab_oracle


def _record(t, predicted, r, calls) -> dict:
    """One arm's scored row for one trace: genuine requires the credited PoC to crash channel-off (already
    checked by score_bug) and the trace to have been grouped to the right bug."""
    credited = bool(r.get("true_reproduced"))
    genuine = bool(credited and predicted == t.bug)
    return {"bug": t.bug, "predicted": predicted, "genuine": genuine,
            "false_credit": bool(r.get("false_credit")),
            "size_gap": float(r["size_gap"]) if (genuine and r.get("size_gap") is not None) else float("nan"),
            "reads": calls}


def _miss(t) -> dict:                                                      # no family predicted: nothing minimised
    return {"bug": t.bug, "predicted": None, "genuine": False, "false_credit": False,
            "size_gap": float("nan"), "reads": 0}


def run_headtohead(n_traces: int = 42, *, seed: int = 0, model_name: str = "llama3.1:8b", host=None,
                   judge=None, dump_params=None, deduper=None, memo=None):
    """One campaign seed: synthesise traces, group each crash, and run every arm on the routed window of the real
    binary. Returns ({"airbug", "airbug_confirm", "rdd"} -> rows, confusion, setups)."""
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

    rows = {"airbug": [], "airbug_confirm": [], "rdd": []}
    confusion = {b: {p: 0 for p in (*_BUGS, None)} for b in _BUGS}
    for i, t in enumerate(traces):
        predicted = deduper.classify(t.crash_obs)                         # crash grouping: the tool sees only the log
        confusion[t.bug][predicted] += 1
        if predicted is None:
            for arm in rows:
                rows[arm].append(_miss(t))
            continue
        rdd_oracle, _ri, ab_oracle = setup_for(predicted)
        bug_obj = live._Bug(bug=predicted, window=live._WINDOW[predicted], crash_sig=f"bug-{predicted}")
        trace_seed = seed * 131 + i                                       # the same channel realisation for every arm (distinct while traces <= 131)
        rdd_oracle.calls = 0
        rr = dict(scoring.run_tool_campaign(rdd_oracle, [bug_obj], random.Random(trace_seed), decorrelate=True)[0])
        rows["rdd"].append(_record(t, predicted, rr, rdd_oracle.calls))
        for arm, confirm in (("airbug", 0), ("airbug_confirm", 1)):       # airbug_confirm: the read-matched control
            ab_oracle.calls = 0
            ar = dict(scoring.run_baseline_campaign(ab_oracle, [bug_obj], random.Random(trace_seed), decorrelate=True,
                                                    confirm=confirm)[0])
            rows[arm].append(_record(t, predicted, ar, ab_oracle.calls))
    return rows, confusion, setups


def _arm_summary(rows) -> dict:
    n = len(rows) or 1
    routed = [r for r in rows if r["predicted"] == r["bug"]]      # correctly-grouped traces
    nr = len(routed) or 1
    gaps = [r["size_gap"] for r in rows if r["genuine"] and r["size_gap"] == r["size_gap"]]
    return {"genuine": sum(r["genuine"] for r in rows) / n,                    # end-to-end, gated by the grouping
            "genuine_routed": sum(r["genuine"] for r in routed) / nr,          # on correctly-grouped traces only
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
    """Every arm on the one real non-monotone bug (LL_LENGTH_REQ), directly, with no campaign or grouping: it
    crashes iff the interval=0 trigger is present and LL_LENGTH_REQ is absent. The target is truth-table
    backed (Docker-captured), not a live subprocess, and emits bug A's real dump, so both identities judge
    bug-A dumps. Returns per-arm rates over ``seeds`` plus the live L3 call count."""
    ref = multibug.MODEL.clean_obs("A")
    ref_exact = exact_crash_id(ref)

    def ab_id(b, obs):
        return exact_crash_id(obs) == ref_exact

    per = {"airbug": [], "airbug_confirm": [], "rdd": []}
    l3_live = 0
    for s in range(seeds):
        rdd_identity = LiveL2L3Identity({"A": ref}, model=model_name, host=host, memo=memo, judge=judge)
        ro = LengthReqOracle(identity=rdd_identity)
        rr = dict(scoring.run_tool_campaign(ro, [LRBUG], random.Random(s), decorrelate=True)[0])
        per["rdd"].append(_record_direct(rr, ro.calls))
        l3_live += rdd_identity.stats["l3_live"]
        for arm, confirm in (("airbug", 0), ("airbug_confirm", 1)):
            ao = LengthReqOracle(identity=ab_id)
            ar = dict(scoring.run_baseline_campaign(ao, [LRBUG], random.Random(s), decorrelate=True, confirm=confirm)[0])
            per[arm].append(_record_direct(ar, ao.calls))
    return {arm: _arm_summary(per[arm]) for arm in per} | {"l3_live": l3_live}


def run(n_traces: int = 42, seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None,
        judge=None, dump_params=None, deduper=None, memo=None) -> dict:
    """Every arm over ``seeds`` campaign seeds, aggregated as mean/min/max per metric. The L3 memo is shared
    across seeds and targets (each distinct dump pair judged once): pass an empty ``memo`` for a live run and
    persist it, or a complete ``memo`` plus a conservative-NO ``judge`` for a replay (``l3_live`` is then 0)."""
    memo = {} if memo is None else memo
    per = {"airbug": [], "airbug_confirm": [], "rdd": []}
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
    out["suppressor"] = {arm: supp[arm] for arm in per}                  # rates over seeds, one bug
    out["l3_live"] += supp["l3_live"]
    return out


_DATA = Path(__file__).resolve().parent / "data"
_CACHE = _DATA / "llm_cache" / "headtohead_l3.json"           # the frozen live-L3 verdicts
_REF = _DATA / "reference" / "headtohead.json"               # the committed B1 reference


def freeze(n_traces: int = 42, seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None, judge=None,
           cache_path: Path = _CACHE, ref_path: Path = _REF) -> dict:
    """Run B1 live (default judge: Ollama), then persist the L3 memo and the reference."""
    memo: dict = {}
    out = run(n_traces, seeds, model_name=model_name, host=host, judge=judge, memo=memo)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(memo, indent=1) + "\n", encoding="utf-8")
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n", encoding="utf-8")
    return out


def frozen(n_traces: int = 42, seeds: int = 8, *, cache_path: Path = _CACHE) -> dict:
    """Replay B1 from the committed memo with no live model: a conservative-NO judge stands in for the model and
    must never fire if the memo is complete (``l3_live`` == 0)."""
    memo = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    return run(n_traces, seeds, judge=lambda *a, **k: {"same": False}, memo=dict(memo))


def refreeze(n_traces: int = 42, seeds: int = 8) -> dict:
    """Write the reference from the frozen replay, for a change to the scorer or the pipeline that leaves the noise
    streams, and hence the committed memo, valid."""
    out = frozen(n_traces, seeds)
    _REF.write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n", encoding="utf-8")
    return out


def coherence(n_traces: int = 42, seeds: int = 8, tol: float = 1e-9) -> bool:
    """True iff the frozen replay reproduces every leaf of the committed reference and makes no live model call.
    The top-level ``l3_live`` is skipped: the reference records the count of the run that wrote it
    (live for ``--freeze``, 0 for ``--refreeze``)."""
    ref = json.loads(_REF.read_text(encoding="utf-8"))
    fresh = scoring.clean_nan(frozen(n_traces, seeds))   # NaN-as-null on both sides
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
                                 description="B1: AirBugCatcher vs RDD on the real host-native targets via the full shared pipeline")
    ap.add_argument("--traces", type=int, default=42)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--host", default=None)
    ap.add_argument("--freeze", action="store_true", help="run against a live judge and rewrite the memo and the reference")
    ap.add_argument("--frozen", action="store_true", help="reproduce from the committed memo (no live model)")
    ap.add_argument("--coherence", action="store_true", help="frozen replay must reproduce the committed reference")
    ap.add_argument("--refreeze", action="store_true", help="write the reference from the frozen replay (no live model)")
    a = ap.parse_args()
    if a.coherence:
        return 0 if coherence(a.traces, a.seeds) else 1
    out = (freeze(a.traces, a.seeds, model_name=a.model, host=a.host) if a.freeze
           else refreeze(a.traces, a.seeds) if a.refreeze
           else frozen(a.traces, a.seeds) if a.frozen
           else run(a.traces, a.seeds, model_name=a.model, host=a.host))
    print(f"=== B1 head-to-head — {a.seeds} seeds x {a.traces} traces; real host-native binary + "
          f"{'frozen L3 cache' if (a.frozen or a.refreeze) else 'live L3 (' + a.model + ')'} ===")
    print(f"  {'metric':16} {'AirBugCatcher':>14} {'+ 1 confirmation':>18} {'RDD (range over seeds)':>26}")
    for m in ("genuine", "genuine_routed", "false_credit", "exact_minimal", "mean_size_gap", "reads"):
        ab, ac, rd = out["airbug"][m], out["airbug_confirm"][m], out["rdd"][m]
        f3 = lambda x: f"{x['mean']:.3f}" if x else "n/a"                   # noqa: E731
        rd_s = f"{rd['mean']:.3f} [{rd['min']:.3f},{rd['max']:.3f}]" if rd else "n/a"
        print(f"  {m:16} {f3(ab):>10} {f3(ac):>20} {rd_s:>26}")
    sp = out["suppressor"]
    print(f"  -- real non-monotone suppressor (LL_LENGTH_REQ, truth-table-backed): "
          f"AirBugCatcher {sp['airbug']['genuine']:.3f}/{sp['airbug']['false_credit']:.3f}   "
          f"+1 confirm {sp['airbug_confirm']['genuine']:.3f}/{sp['airbug_confirm']['false_credit']:.3f}   "
          f"RDD {sp['rdd']['genuine']:.3f}/{sp['rdd']['false_credit']:.3f}  (genuine/false credit)")
    print("  RDD = live open-model L3 (range over seeds; verdicts frozen to the cache for a reproducible CI point);")
    print("  AirBugCatcher = exact-id (bit-reproducible). Scored vs the channel-off virtual-perfect. host-native binary + MODELLED channel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
