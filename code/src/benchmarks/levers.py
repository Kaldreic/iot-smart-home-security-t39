"""benchmarks.levers — B3: the real-target lever decomposition, RDD's advantage attributed to its 3 levers.

The third headline (peer to B1 ``benchmarks.headtohead`` + B2 ``benchmarks.resilience``): on the REAL
native_sim Zephyr targets, decompose RDD's reproduction advantage into its three design levers by toggling
ONE at a time — a 4-arm cube run DIRECT-WINDOW (each real bug's own window; NO dedup front-end, so the arms
differ ONLY in the toggled lever):

  baseline  = AirBug          (fixed-K enum minimiser + exact-id)
  oracle    = + the oracle     (RDD's truncated-SPRT oracle + ddmin, still exact-id)        [oracle ON]
  ablation  = + the identity   (L2/L3 crash-identity replaces exact-id; still bare ddmin)   [oracle + identity]
  tool      = + the minimiser  (the robust non-monotone seed-finder; the full shipped RDD)  [all three]

THE 3 LEVERS (honest attribution — each shown where it actually bites):
  * ORACLE/gate = the FALSE-CREDIT lever, shown by INVARIANCE on A--F: false_credit ~ 0 for ALL THREE pipeline
    arms (oracle, ablation, tool) and > 0 ONLY for the fixed-K baseline (no final-validation gate). baseline ->
    the `oracle` arm flips the SPRT oracle AND the minimiser together, so the oracle's genuine EFFECT is
    confounded and NOT claimed as a clean lever (the `oracle` arm's genuine can even sit BELOW baseline; the
    genuine RECOVERY is the identity + minimiser levers below) — only its false-credit role (the SPRT +
    final-validation gate) is attributed here.
  * IDENTITY (genuine) = oracle -> ablation on A--F: the L2/L3 crash-identity recovers reproductions exact-id
    discards (a varied/garbled dump that is the same bug).
  * ROBUST MINIMISER (genuine) = ablation -> tool on the SUPPRESSOR: the non-monotone seed-finder recovers the
    bug bare ddmin SEED-BAILS on (the real LL_LENGTH_REQ suppressor). On the monotone A--F bugs ddmin already
    suffices, so the minimiser lever shows on the suppressor, not on A--F — disclosed.

L3 = "live range + frozen CI gate" (like B1): the two L2/L3 arms (ablation, tool) run their crash-identity LIVE
(the open-model judge) across N=8 seeds -> the authentic genuine RANGE is the headline; the live verdicts are
FROZEN to the committed cache so CI re-verifies a reproducible point (out['l3_live']==0 on a frozen replay). The
two exact-id arms (baseline, oracle) call NO model -> bit-reproducible. All four arms drive the SAME real
native_sim binary per bug (built once, shared) over the SAME per-(bug, seed) channel seed (fair).

METRICS (B1's set), per arm, scored vs the channel-off virtual-perfect the minimiser NEVER sees (genuine <=>
the PoC PROVABLY crashes the RIGHT bug): genuine / false_credit / exact_minimal (of genuine) / mean_size_gap
(of genuine) / reads. The A--F arms are seed-RANGES (mean/min/max over seeds); the suppressor arms are rates
over seeds (one bug). Reported in two parts: ``real`` (A--F) + ``suppressor`` + the 3 ``levers`` deltas.

HONEST BOUNDARY (disclosed, as in B1): the "real device" is the real Zephyr controller compiled to a native_sim
ELF and run via subprocess (NOT a runtime container; Docker only builds it); the radio/OTA channel is MODELLED
(Gilbert-Elliott). Direct-window (vs B1's full fuzz->dedup pipeline) isolates the levers from the grouping
front-end. The suppressor is the real non-monotone LL_LENGTH_REQ target (truth-table-backed, Docker-captured;
it emits bug A's real conn-update dump, so the live L3 + exact-id both judge bug-A dumps).

  python -m benchmarks.levers --seeds 8 --model llama3.1:8b   # the live decomposition (needs the binaries + Ollama)
  python -m benchmarks.levers --coherence                     # frozen replay reproduces the committed reference (exact)
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
from emulation.live import LiveBinaryOracle, _Bug, _WINDOW
from emulation.suppressor import LRBUG, LengthReqOracle
from rdd.identity import LiveL2L3Identity

# the 4-arm cube: (label, campaign-runner, identity-kind 'exact'|'l3', minimiser kwargs). ALL FOUR run
# DECORRELATED so the channel is held CONSTANT across arms (the clean control a decomposition needs; matches B1) --
# the toggled lever is then the only difference. baseline = AirBug enum + exact-id; oracle/ablation/tool = the RDD
# pipeline (truncated-SPRT oracle) with the levers toggled on. NB decorrelate=True resamples the channel each rep, so
# it DOES shift AirBug's numbers (not a no-op) -- it is a deliberate control to equalise the channel across arms here.
# B2's head-to-head runs AirBug as-shipped (decorrelate=False), so the same AirBug arm reads slightly differently
# there (e.g. the real suppressor 0.875 here/B1 vs 0.800 in the cached real anchor): a control difference, not a tool change.
_ARMS = [
    ("baseline", scoring.run_baseline_campaign, "exact", {"decorrelate": True}),
    ("oracle",   scoring.run_tool_campaign,     "exact", {"decorrelate": True, "ablate_robust": True}),
    ("ablation", scoring.run_tool_campaign,     "l3",    {"decorrelate": True, "ablate_robust": True}),
    ("tool",     scoring.run_tool_campaign,     "l3",    {"decorrelate": True}),
]
_METRICS = ("genuine", "false_credit", "exact_minimal", "mean_size_gap", "reads")


def _setup_target(bug, *, model_name, host, judge, memo):
    """Capture the real native_sim target ONCE and build the two oracles over the SAME dump-model: the live
    L2/L3 oracle (ablation + tool) and the exact-id oracle (baseline + oracle arms). Returns {'l3': (o, id), 'exact': (o, None)}."""
    l3_oracle, l3_identity = live.build_live_campaign(bug, model=model_name, host=host, judge=judge, memo=memo)
    ref_exact = exact_crash_id(l3_oracle.model.clean_obs(bug))            # the captured clean dump's exact id

    def exact_identity(b, obs, _ref=ref_exact):                          # AirBug's is_same_crash_id (deterministic)
        return exact_crash_id(obs) == _ref
    exact_oracle = LiveBinaryOracle(l3_oracle.binary, bug, exact_identity, l3_oracle.model, crash_rc=l3_oracle.crash_rc)
    return {"l3": (l3_oracle, l3_identity), "exact": (exact_oracle, None)}


def _row(bug, r, calls) -> dict:
    """Score one arm's run on one bug vs the channel-off virtual-perfect (already applied by score_bug)."""
    genuine = bool(r.get("true_reproduced"))
    return {"bug": bug, "genuine": genuine, "false_credit": bool(r.get("false_credit")),
            "size_gap": float(r["size_gap"]) if (genuine and r.get("size_gap") is not None) else float("nan"),
            "reads": calls}


def _run_seed(seed, setups) -> dict:
    """Run the 4 arms over every real bug on its OWN window (direct-window), all four sharing the per-(bug, seed)
    channel seed. Returns {arm: [rows over the bugs]}."""
    rows = {lbl: [] for lbl, *_ in _ARMS}
    for i, bug in enumerate(_BUGS):
        oracles = setups[bug]
        bug_obj = _Bug(bug=bug, window=_WINDOW[bug], crash_sig=f"bug-{bug}")
        arm_seed = seed * 131 + i                                         # SAME channel realisation start for all 4 arms (fair)
        for lbl, campaign, kind, kw in _ARMS:
            oracle = oracles[kind][0]
            oracle.calls = 0
            r = dict(campaign(oracle, [bug_obj], random.Random(arm_seed), **kw)[0])
            rows[lbl].append(_row(bug, r, oracle.calls))
    return rows


def _arm_summary(rows) -> dict:
    """B1's metric set over a set of scored rows (the 6 bugs of one seed, or the per-seed rows of the suppressor):
    genuine / false_credit / exact_minimal (of genuine) / mean_size_gap (of genuine) / reads."""
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
    """The 4 arms on the real non-monotone LL_LENGTH_REQ suppressor (truth-table-backed; emits bug A's real dump,
    so the live L3 + exact-id both judge bug-A dumps). Rates over ``seeds`` (one bug). This is where the ROBUST
    MINIMISER lever shows: bare ddmin (ablation) SEED-BAILS, the robust seed-finder (tool) recovers."""
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
    """Attribute each lever where it bites: ORACLE = the false-credit INVARIANCE on A--F (baseline > 0, the
    pipeline arms ~ 0); IDENTITY = the oracle -> ablation genuine gain on A--F; ROBUST MINIMISER = the
    ablation -> tool genuine gain on the suppressor (where bare ddmin bails)."""
    rg = lambda arm: out["real"][arm]["genuine"]["mean"]                  # noqa: E731  (A--F genuine mean)
    rfc = lambda arm: out["real"][arm]["false_credit"]["mean"]            # noqa: E731
    sg = lambda arm: out["suppressor"][arm]["genuine"]                    # noqa: E731  (suppressor genuine rate)
    return {"oracle_fc_invariance": {lbl: rfc(lbl) for lbl, *_ in _ARMS},
            "identity_genuine_real": rg("ablation") - rg("oracle"),
            "minimiser_genuine_suppressor": sg("tool") - sg("ablation")}


def run(seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None, judge=None, memo=None) -> dict:
    """The full B3 decomposition: the 4-arm cube over A--F (seed-ranges) + the suppressor (rates) + the 3 lever
    deltas. The L3 verdict memo is SHARED across seeds/bugs/parts (each distinct dump pair judged once) so the
    caller can FREEZE it (empty ``memo`` for a live run; a complete ``memo`` + a conservative-NO ``judge`` for a
    reproducible replay -> out['l3_live'] == 0)."""
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
_CACHE = _DATA / "llm_cache" / "levers_l3.json"             # the frozen live-L3 verdicts (the reproducibility freeze)
_REF = _DATA / "reference" / "levers.json"                 # the frozen B3 reference numbers


def freeze(seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None, judge=None,
           cache_path: Path = _CACHE, ref_path: Path = _REF) -> dict:
    """Run B3 LIVE (default judge = Ollama), capturing every L3 verdict, then PERSIST the memo + the reference."""
    memo: dict = {}
    out = run(seeds, model_name=model_name, host=host, judge=judge, memo=memo)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(memo, indent=1) + "\n")
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n")
    return out


def frozen(seeds: int = 8, *, cache_path: Path = _CACHE) -> dict:
    """Reproduce B3 from the committed memo with NO live model: pre-load the complete memo + a conservative-NO
    guard judge (which must never fire if the memo is complete -> out['l3_live'] == 0)."""
    memo = json.loads(Path(cache_path).read_text())
    return run(seeds, judge=lambda *a, **k: {"same": False}, memo=dict(memo))


def coherence(seeds: int = 8, tol: float = 1e-9) -> bool:
    """The FROZEN replay reproduces the committed reference EXACTLY (every leaf) and makes 0 live model calls.
    The top-level ``l3_live`` is skipped — the reference records the live-freeze count, a frozen replay is 0."""
    ref = json.loads(_REF.read_text())
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
    g = lambda arm, m: out["real"][arm][m]["mean"] if out["real"][arm][m] else float("nan")   # noqa: E731
    print(f"=== B3 lever decomposition — {out['n_seeds']} seeds, real native_sim ({out['n_bugs']} bugs A--F) + the suppressor ===")
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
    print("  RDD L2/L3 arms (ablation, tool) = live open-model L3 (range over seeds; frozen to the cache for a reproducible CI point);")
    print("  baseline + oracle = exact-id (bit-reproducible). Scored vs the channel-off virtual-perfect. native_sim + MODELLED channel.")


def main() -> int:
    ap = argparse.ArgumentParser(prog="benchmarks.levers",
                                 description="B3: the real-target lever decomposition (oracle / identity / robust minimiser)")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--host", default=None)
    ap.add_argument("--freeze", action="store_true", help="run LIVE + persist the memo + the reference (regenerate)")
    ap.add_argument("--frozen", action="store_true", help="reproduce from the committed memo (no live model)")
    ap.add_argument("--coherence", action="store_true", help="frozen replay must reproduce the committed reference")
    a = ap.parse_args()
    if a.coherence:
        return 0 if coherence(a.seeds) else 1
    out = (freeze(a.seeds, model_name=a.model, host=a.host) if a.freeze
           else frozen(a.seeds) if a.frozen
           else run(a.seeds, model_name=a.model, host=a.host))
    _print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
