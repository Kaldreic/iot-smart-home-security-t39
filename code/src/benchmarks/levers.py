"""benchmarks.levers — B3: the real-target lever decomposition.

Four arms on the real host-native Zephyr targets, each on the bug's own window (no grouping front-end):
baseline (AirBugCatcher enumeration + exact-id); oracle (RDD's truncated-SPRT oracle + bare ddmin, exact-id);
ablation (+ the L2/L3 crash identity, bare ddmin); tool (+ the robust minimiser: the shipped RDD). The
``levers`` block reports each arm's false credit on A--F, the oracle -> ablation genuine change on A--F
(identity) and the ablation -> tool genuine change on the real LL_LENGTH_REQ suppressor (minimiser; on the
monotone A--F bugs ddmin suffices). The oracle arm changes the oracle and the minimiser together, so its own
genuine change is not attributed to one lever.

The two L2/L3 arms call the open model live and are reported as ranges over seeds; their verdicts are frozen
to data/llm_cache/levers_l3.json for a reproducible replay. The two exact-id arms call no model. All arms run
decorrelated on the same per-(bug, seed) channel seed and are scored by ``scoring.score_bug`` against the
channel-off truth. The "device" is the host-native ELF run via subprocess; the OTA channel is modelled. The
suppressor target is truth-table backed and emits bug A's real dump.

  python -m benchmarks.levers --seeds 8 --model llama3.1:8b   # live (needs the binaries + Ollama)
  python -m benchmarks.levers --frozen | --coherence | --refreeze
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np

from benchmarks import live, scoring
from benchmarks.scenario import _BUGS
from emulation import multibug
from emulation.baseline import exact_crash_id
from emulation.live import LiveBinaryOracle, _Bug
from emulation.multibug import WINDOW
from emulation.suppressor import LRBUG, LengthReqOracle
from rdd.identity import LiveL2L3Identity

# (label, campaign runner, identity kind 'exact'|'l3', minimiser kwargs). All four arms run decorrelated so
# the channel is the same across arms. decorrelate=True resamples the channel each rep, so the AirBugCatcher arm
# here reads differently from the as-shipped (decorrelate=False) AirBugCatcher arm of B2 and the anchor.
_ARMS = [
    ("baseline", scoring.run_baseline_campaign, "exact", {"decorrelate": True}),
    ("oracle",   scoring.run_tool_campaign,     "exact", {"decorrelate": True, "ablate_robust": True}),
    ("ablation", scoring.run_tool_campaign,     "l3",    {"decorrelate": True, "ablate_robust": True}),
    ("tool",     scoring.run_tool_campaign,     "l3",    {"decorrelate": True}),
]
_METRICS = ("genuine", "false_credit", "exact_minimal", "mean_size_gap", "reads")


def _setup_target(bug, *, model_name, host, judge, memo):
    """Capture the target once and build both oracles over the same dump model: live L2/L3 (ablation, tool) and
    exact-id (baseline, oracle). Returns {'l3': (oracle, identity), 'exact': (oracle, None)}."""
    l3_oracle, l3_identity = live.build_live_campaign(bug, model=model_name, host=host, judge=judge, memo=memo)
    ref_exact = exact_crash_id(l3_oracle.model.clean_obs(bug))            # the captured clean dump's exact id

    def exact_identity(b, obs, _ref=ref_exact):                          # AirBugCatcher's is_same_crash_id
        return exact_crash_id(obs) == _ref
    exact_oracle = LiveBinaryOracle(l3_oracle.binary, bug, exact_identity, l3_oracle.model, crash_rc=l3_oracle.crash_rc)
    return {"l3": (l3_oracle, l3_identity), "exact": (exact_oracle, None)}


def _row(bug, r, calls) -> dict:
    """One arm's scored row for one bug (score_bug has already applied the channel-off rule)."""
    genuine = bool(r.get("true_reproduced"))
    return {"bug": bug, "genuine": genuine, "false_credit": bool(r.get("false_credit")),
            "size_gap": float(r["size_gap"]) if (genuine and r.get("size_gap") is not None) else float("nan"),
            "reads": calls}


def _run_seed(seed, setups) -> dict:
    """The four arms over every real bug on its own window, sharing the per-(bug, seed) channel seed. Returns
    {arm: rows over the bugs}."""
    rows = {lbl: [] for lbl, *_ in _ARMS}
    for i, bug in enumerate(_BUGS):
        oracles = setups[bug]
        bug_obj = _Bug(bug=bug, window=WINDOW[bug], crash_sig=f"bug-{bug}")
        arm_seed = seed * 131 + i                                         # the same channel seed for all four arms (distinct while bugs <= 131)
        for lbl, campaign, kind, kw in _ARMS:
            oracle = oracles[kind][0]
            oracle.calls = 0
            r = dict(campaign(oracle, [bug_obj], random.Random(arm_seed), **kw)[0])
            rows[lbl].append(_row(bug, r, oracle.calls))
    return rows


def _arm_summary(rows) -> dict:
    """The metric set over scored rows: genuine, false_credit, exact_minimal and mean_size_gap (of genuine), reads."""
    n = len(rows) or 1
    gaps = [r["size_gap"] for r in rows if r["genuine"] and r["size_gap"] == r["size_gap"]]
    return {"genuine": sum(r["genuine"] for r in rows) / n,
            "false_credit": sum(r["false_credit"] for r in rows) / n,
            "exact_minimal": (sum(g == 0.0 for g in gaps) / len(gaps)) if gaps else float("nan"),
            "mean_size_gap": float(np.mean(gaps)) if gaps else float("nan"),
            "reads": float(np.mean([r["reads"] for r in rows])) if rows else float("nan")}


def _agg_seed(per, key) -> dict | None:
    vs = [p[key] for p in per if p[key] == p[key]]                        # drop NaN seeds
    return {"mean": float(np.mean(vs)), "min": float(min(vs)), "max": float(max(vs)), "n": len(vs)} if vs else None


def _run_suppressor(seeds, *, model_name, host, judge, memo) -> dict:
    """The four arms on the real non-monotone LL_LENGTH_REQ suppressor (truth-table backed; it emits bug A's
    real dump, so both identities judge bug-A dumps). Rates over ``seeds``."""
    ref = multibug.MODEL.clean_obs("A")
    ref_exact = exact_crash_id(ref)

    def exact_id(b, obs):
        return exact_crash_id(obs) == ref_exact

    per = {lbl: [] for lbl, *_ in _ARMS}
    l3_live = 0
    for s in range(seeds):
        l3_identity = LiveL2L3Identity({"A": ref}, model=model_name, host=host, memo=memo, judge=judge)
        oracles = {"l3": (LengthReqOracle(identity=l3_identity), l3_identity),
                   "exact": (LengthReqOracle(identity=exact_id), None)}
        for lbl, campaign, kind, kw in _ARMS:
            o = oracles[kind][0]
            o.calls = 0
            r = dict(campaign(o, [LRBUG], random.Random(s), **kw)[0])
            per[lbl].append(_row("LR", r, o.calls))
        l3_live += l3_identity.stats["l3_live"]
    return {"arms": {lbl: _arm_summary(per[lbl]) for lbl in per}, "l3_live": l3_live}


def _lever_deltas(out) -> dict:
    """The three lever deltas: per-arm false credit on A--F, the oracle -> ablation genuine change on A--F, and
    the ablation -> tool genuine change on the suppressor."""
    rg = lambda arm: out["real"][arm]["genuine"]["mean"]                  # A--F genuine mean
    rfc = lambda arm: out["real"][arm]["false_credit"]["mean"]
    sg = lambda arm: out["suppressor"][arm]["genuine"]                    # suppressor genuine rate
    return {"oracle_fc_invariance": {lbl: rfc(lbl) for lbl, *_ in _ARMS},
            "identity_genuine_real": rg("ablation") - rg("oracle"),
            "minimiser_genuine_suppressor": sg("tool") - sg("ablation")}


def run(seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None, judge=None, memo=None) -> dict:
    """The full B3 run: the four arms over A--F (ranges over seeds), the suppressor (rates) and the lever deltas.
    The L3 memo is shared across seeds, bugs and parts: pass an empty ``memo`` for a live run, or a complete
    ``memo`` plus a conservative-NO ``judge`` for a replay (``l3_live`` is then 0)."""
    memo = {} if memo is None else memo
    setups = {bug: _setup_target(bug, model_name=model_name, host=host, judge=judge, memo=memo) for bug in _BUGS}
    per = {lbl: [] for lbl, *_ in _ARMS}
    for s in range(seeds):
        rows = _run_seed(s, setups)
        for lbl in per:
            per[lbl].append(_arm_summary(rows[lbl]))
    l3_live = sum(setups[b]["l3"][1].stats["l3_live"] for b in _BUGS)
    out = {"suite": "levers", "n_bugs": len(_BUGS), "n_seeds": seeds, "l3_live": l3_live,
           "real": {lbl: {m: _agg_seed(per[lbl], m) for m in _METRICS} for lbl in per}}
    supp = _run_suppressor(seeds, model_name=model_name, host=host, judge=judge, memo=memo)
    out["suppressor"] = supp["arms"]
    out["l3_live"] += supp["l3_live"]
    out["levers"] = _lever_deltas(out)
    return out


_DATA = Path(__file__).resolve().parent / "data"
_CACHE = _DATA / "llm_cache" / "levers_l3.json"             # the frozen live-L3 verdicts
_REF = _DATA / "reference" / "levers.json"                 # the committed B3 reference


def freeze(seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None, judge=None,
           cache_path: Path = _CACHE, ref_path: Path = _REF) -> dict:
    """Run B3 live (default judge: Ollama), then persist the L3 memo and the reference."""
    memo: dict = {}
    out = run(seeds, model_name=model_name, host=host, judge=judge, memo=memo)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(memo, indent=1) + "\n", encoding="utf-8")
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n", encoding="utf-8")
    return out


def frozen(seeds: int = 8, *, cache_path: Path = _CACHE) -> dict:
    """Replay B3 from the committed memo with no live model: a conservative-NO judge stands in for the model and
    must never fire if the memo is complete (``l3_live`` == 0)."""
    memo = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    return run(seeds, judge=lambda *a, **k: {"same": False}, memo=dict(memo))


def refreeze(seeds: int = 8) -> dict:
    """Write the reference from the frozen replay, for a change to the scorer or the pipeline that leaves the noise
    streams, and hence the committed memo, valid."""
    out = frozen(seeds)
    _REF.write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n", encoding="utf-8")
    return out


def coherence(seeds: int = 8, tol: float = 1e-9) -> bool:
    """True iff the frozen replay reproduces every leaf of the committed reference and makes no live model call.
    The top-level ``l3_live`` is skipped: the reference records the count of the run that wrote it
    (live for ``--freeze``, 0 for ``--refreeze``)."""
    ref = json.loads(_REF.read_text(encoding="utf-8"))
    fresh = scoring.clean_nan(frozen(seeds))
    diffs = scoring.leaf_diffs(fresh, ref, tol=tol, skip_top=("l3_live",))
    ok = fresh["l3_live"] == 0 and not diffs
    print(f"B3 COHERENCE — frozen replay vs committed levers.json "
          f"(l3_live={fresh['l3_live']}, {len(diffs)} leaf diffs over the full reference):")
    for p, fv, rv in diffs[:25]:
        print(f"  [XX] {p}: fresh={fv} ref={rv}")
    print("COHERENT" if ok else "INCOHERENT")
    return ok


def _print(out: dict) -> None:
    g = lambda arm, m: out["real"][arm][m]["mean"] if out["real"][arm][m] else float("nan")
    print(f"=== B3 lever decomposition — {out['n_seeds']} seeds, real host-native binaries ({out['n_bugs']} bugs A--F) + the suppressor ===")
    print(f"  {'arm':9} {'A--F genuine/fc':>22} {'exact/gap':>14}    {'suppressor g/fc':>15}")
    for lbl, *_ in _ARMS:
        s = out["suppressor"][lbl]
        gr = out["real"][lbl]["genuine"]
        gr_s = f"{gr['mean']:.3f} [{gr['min']:.3f},{gr['max']:.3f}]" if gr else "n/a"
        print(f"  {lbl:9} {gr_s:>14}/{g(lbl, 'false_credit'):.3f}   {g(lbl, 'exact_minimal'):.2f}/{g(lbl, 'mean_size_gap'):.2f}    "
              f"{s['genuine']:.3f}/{s['false_credit']:.3f}")
    lv = out["levers"]
    print(f"  LEVERS: oracle = fc INVARIANCE on A--F (baseline {lv['oracle_fc_invariance']['baseline']:.3f} vs "
          f"oracle/ablation/tool {lv['oracle_fc_invariance']['oracle']:.3f}/{lv['oracle_fc_invariance']['ablation']:.3f}/"
          f"{lv['oracle_fc_invariance']['tool']:.3f});")
    print(f"          identity (genuine, A--F) oracle->ablation {lv['identity_genuine_real']:+.3f};  "
          f"robust minimiser (genuine, suppressor) ablation->tool {lv['minimiser_genuine_suppressor']:+.3f}")
    print("  RDD arms (ablation, tool) = live open-model L3 (verdicts frozen to the cache for a reproducible replay);")
    print("  baseline + oracle = exact id, no model. Scored against the channel-off truth; host-native binary, modelled channel.")


def main() -> int:
    ap = argparse.ArgumentParser(prog="benchmarks.levers",
                                 description="B3: the real-target lever decomposition (oracle / identity / robust minimiser)")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--host", default=None)
    ap.add_argument("--freeze", action="store_true", help="run against a live judge and rewrite the memo and the reference")
    ap.add_argument("--frozen", action="store_true", help="reproduce from the committed memo (no live model)")
    ap.add_argument("--coherence", action="store_true", help="frozen replay must reproduce the committed reference")
    ap.add_argument("--refreeze", action="store_true", help="write the reference from the frozen replay (no live model)")
    a = ap.parse_args()
    if a.coherence:
        return 0 if coherence(a.seeds) else 1
    out = (freeze(a.seeds, model_name=a.model, host=a.host) if a.freeze
           else refreeze(a.seeds) if a.refreeze
           else frozen(a.seeds) if a.frozen
           else run(a.seeds, model_name=a.model, host=a.host))
    _print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
