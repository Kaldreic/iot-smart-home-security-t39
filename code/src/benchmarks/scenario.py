"""benchmarks.scenario — the FULL real-deployment scenario: RDD as the minimiser module in the production
pipeline  fuzz-campaign -> crash-dedup -> per-bug window -> RDD -> PoC,  over all 6 real bugs.

This module owns the whole eval-side pipeline: the SIMULATED pre-RDD front-end (the fuzzing campaign +
the crash deduper, below), then routing each deduped crash to the real per-bug binary (from
``benchmarks.live``), driving RDD over that bug's fixed window, and scoring the end-to-end run. The fuzzing
campaign is the ONLY simulated stage (no HW radio against native_sim): we synthesise a campaign of packet-log
TRACES (illustrative decoy PDUs + the bugs' real trigger patterns + cross-bug look-alikes) and, for each, a
crash log = a MODELLED-varied instance of that bug's REAL captured dump (the same report-noise model
``benchmarks.live`` uses). The downstream STAGES are real:

  * crash DEDUP   — the tool gets only a crash log and must CLASSIFY it (via the L2/L3 crash-identity) into one
                    of the 6 real families. A,B are both SIGFPE and C,D,E,F all assert (at distinct sites), so
                    dedup must split by crash SITE, not just fault type. The predicted family ROUTES the
                    minimiser to a binary, so a mis-dedup minimises the WRONG target -> a real end-to-end
                    failure (load-bearing dedup).
  * per-bug WINDOW — each bug's FIXED PDU window (trigger-last for A,B; the two load-bearing INDs/REQs for C,D,E,F).
  * RDD MINIMISE  — reduce the window to a PoC by probing the REAL per-bug binary live + a live open-model L3.
  * SCORE         — each PoC must genuinely crash the real binary AND is scored vs the PERFECT true-minimal.

Honest scope: the binary's window layout is fixed, so the trace is a FRONT-END — its PDU sequence is
realism/provenance, while the FUNCTIONAL inputs are the (modelled-varied) crash log -> DEDUP and the binary's
fixed W-window -> MINIMISE (where the minimiser discards the window's real decoys to find the trigger). It is
NOT a larger candidate space — the one gap a HW radio would close. USAGE VALIDATION: no baseline, no coherence
gate (a live model + a live binary are not bit-reproducible). End-to-end genuine varies with the seed (live
model + OTA channel), SUBSTANTIATED at mean 0.872, range [0.825, 0.925] over 8 seeds (``run_multiseed``;
recorded disclosed-live in data/reference/scenario_multiseed.json -- a single seed is not bit-reproducible, so
the RANGE is the claim). The dedup accuracy (mean 0.931) and the 0 false-credit (max 0.000 across all 8 seeds)
are ROBUST; ``test_scenario_multiseed_robust_invariants`` pins those invariants reproducibly in CI (fake judge +
mocked binary).

  python -m benchmarks.scenario --traces 40 --model llama3.1:8b              # one live run (+ confusion matrix)
  python -m benchmarks.scenario --traces 40 --seeds 8 --model llama3.1:8b    # the multi-seed range (needs Ollama)
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field

import numpy as np

from benchmarks import live                                 # the per-bug live-binary oracle + routing
from benchmarks import scoring
from emulation import multibug
from emulation.dump import DumpModel
from rdd.identity import L2Matcher

_BUGS = ("A", "B", "C", "D", "E", "F")

# --- the SIMULATED pre-RDD front-end: fuzzing campaign + crash grouping (no HW radio) ---

# The PDU alphabet a BLE link-layer fuzzer mutates over (names are illustrative of the real control PDUs).
_DECOYS_PEER = ("LE_PING", "LL_VERSION_IND", "LL_FEATURE_REQ", "LL_CHANNEL_MAP_IND")   # transparent for A,B
_DECOY_LOCAL = "LOCAL_LE_PING(drained)"                                                 # the transparent one for C,D,E,F
_TRIGGERS = {"A": ("LL_CONNECTION_UPDATE_IND(interval=0)",),
             "B": ("LL_CIS_REQ(iso_interval=0,conn_event_count=0)",),
             "C": ("LL_CONNECTION_UPDATE_IND #1", "LL_CONNECTION_UPDATE_IND #2"),
             "D": ("LL_PHY_UPDATE_IND #1", "LL_PHY_UPDATE_IND #2"),
             "E": ("LL_LENGTH_REQ #1", "LL_LENGTH_REQ #2"),
             "F": ("LL_CIS_IND #1", "LL_CIS_IND #2")}
# cross-bug LOOK-ALIKES — resemble a trigger but DON'T fire (the noise dedup/minimise must not be fooled by):
_LOOKALIKES = ("LL_CONNECTION_UPDATE_IND(interval=7)",      # a benign conn-update (not interval=0, not a C-pair)
               "LL_CIS_REQ(well-formed)", "LL_PHY_UPDATE_IND(no-op)",
               "LL_LENGTH_REQ(single,benign)",              # one length-req keeps the node -> doesn't fire E
               "LL_CIS_IND(single,benign)")                 # one cis-ind keeps the node -> doesn't fire F


@dataclass
class Trace:
    """One simulated fuzzer artifact: a packet-log + the crash log it produced (the fuzzer's observed crash).
    ``bug`` is the GROUND TRUTH (used only for scoring, never shown to the tool)."""
    bug: str
    pdus: list                     # the full packet sequence (realism/provenance; longer than the window)
    crash_obs: object              # the crash log the fuzzer captured (a varied DumpObs of ``bug``)


def generate_campaign(n_traces: int, model: DumpModel, rng: random.Random) -> list:
    """Synthesise a realistic campaign: ``n_traces`` packet-log traces spread evenly across the real bugs, each
    a noisy session (random decoys + cross-bug look-alikes + the bug's real trigger pattern) ending in that
    bug's crash. The crash log is a VARIED dump (the same report-noise model benchmarks.real/live use)."""
    traces = []
    for i in range(n_traces):
        bug = _BUGS[i % len(_BUGS)]                         # even spread across all real bugs
        decoys = list(_DECOYS_PEER if bug in ("A", "B") else (_DECOY_LOCAL,) * 3)
        n_decoy = rng.randint(2, 6)
        session = [rng.choice(decoys) for _ in range(n_decoy)]
        for _ in range(rng.randint(0, 2)):                 # cross-bug look-alikes sprinkled in (combinations)
            session.insert(rng.randrange(len(session) + 1), rng.choice(_LOOKALIKES))
        session += list(_TRIGGERS[bug])                    # the real trigger pattern, most-recent (windowable)
        crash_obs = model.emit(bug, rng)                   # the fuzzer's crash log (a varied report of ``bug``)
        traces.append(Trace(bug=bug, pdus=session, crash_obs=crash_obs))
    rng.shuffle(traces)
    return traces


class CrashDeduper:
    """Crash deduplication: classify a crash log into one of the known families via the L2 crash-identity
    (fuzzy: stack-LCS + SITE + fault). This is the step that must split A from B (both SIGFPE) and C, D, E, F
    (all four asserts, distinct sites) by crash SITE. Returns the best family, or None (a new family)."""

    def __init__(self, references: dict, threshold: float = 0.5):
        self.l2 = L2Matcher(references, threshold=threshold)
        self.families = list(references)

    def classify(self, crash_obs) -> str | None:
        best, best_s = None, -1.0
        for fam in self.families:
            same, s = self.l2.is_same(fam, crash_obs)
            if same and s > best_s:
                best, best_s = fam, s
        return best


# --- the EVALUATION: route on the prediction, drive RDD over the real binary, score end-to-end ---

@dataclass
class _Scored:
    bug: str
    predicted: str | None
    genuine: bool = False
    false_credit: bool = False
    size_gap: float = field(default=float("nan"))
    reads: int = 0
    binary_runs: int = 0
    l3_live: int = 0


def run_scenario(n_traces: int = 40, *, model_name: str = "llama3.1:8b", host=None, seed: int = 0,
                 judge=None, dump_params=None, deduper=None):
    """The full pipeline over a synthesised campaign. For each trace: DEDUP its crash log -> the predicted
    family ROUTES the minimiser to that bug's REAL binary -> RDD reduces the window (live binary + live L3)
    -> the PoC is scored vs the true minimal. Routing on the PREDICTION (not ground truth) makes dedup
    load-bearing. ``deduper`` overrides the crash deduper (for testing). Returns (rows, confusion, campaigns)."""
    base_model = DumpModel.from_logs(multibug.LOGS, bugs=_BUGS,
                                     params=dump_params) if dump_params else DumpModel.from_logs(
        multibug.LOGS, bugs=_BUGS)
    references = {b: base_model.clean_obs(b) for b in _BUGS}
    deduper = deduper if deduper is not None else CrashDeduper(references)
    rng = random.Random(seed)
    traces = generate_campaign(n_traces, base_model, rng)

    # one live oracle + memoised live-L3 identity per bug (built lazily, shared across traces of that family)
    campaigns: dict = {}

    def campaign_for(bug):
        if bug not in campaigns:
            campaigns[bug] = live.build_live_campaign(bug, model=model_name, host=host, judge=judge,
                                                      dump_params=dump_params)
        return campaigns[bug]

    rows, confusion = [], {b: {p: 0 for p in (*_BUGS, None)} for b in _BUGS}
    for t in traces:
        predicted = deduper.classify(t.crash_obs)          # CRASH DEDUP (the tool sees only the crash log)
        confusion[t.bug][predicted] += 1
        row = _Scored(bug=t.bug, predicted=predicted)
        if predicted is None:
            rows.append(row)                               # unclassified -> the tool has no target to minimise
            continue
        oracle, identity = campaign_for(predicted)         # ROUTE the minimiser to the predicted bug's binary
        l3_before, br_before = identity.stats["l3_live"], oracle.binary_runs   # per-trace deltas (oracle is shared)
        oracle.calls = 0
        bug_obj = live._Bug(bug=predicted, window=live._WINDOW[predicted], crash_sig=f"bug-{predicted}")
        r = dict(scoring.run_tool_campaign(oracle, [bug_obj], random.Random(seed * 131 + len(rows)),
                                           decorrelate=True)[0])
        # run_tool_campaign already scored the recovered PoC against the REAL binary (oracle.truth):
        #   true_reproduced = the PoC PROVABLY crashes ``predicted``;  false_credit = it credited a
        #   NON-crashing PoC (a soundness breach, expect 0);  size_gap = PoC size vs ``predicted``'s minimal.
        credited = bool(r.get("true_reproduced"))
        row.genuine = bool(credited and predicted == t.bug)            # a PoC that reproduces the CORRECT family
        row.false_credit = bool(r.get("false_credit"))                 # soundness (expect 0), independent of dedup
        if row.genuine and r.get("size_gap") is not None:
            row.size_gap = float(r["size_gap"])
        row.reads, row.binary_runs = oracle.calls, oracle.binary_runs - br_before
        row.l3_live = identity.stats["l3_live"] - l3_before
        rows.append(row)
    return rows, confusion, campaigns


def _summary(rows, confusion, campaigns=None, model=None) -> dict:
    n = len(rows)
    dedup_ok = sum(1 for r in rows if r.predicted == r.bug)
    genuine = sum(1 for r in rows if r.genuine)
    fc = sum(1 for r in rows if r.false_credit)
    gaps = [r.size_gap for r in rows if r.genuine and r.size_gap == r.size_gap]
    exact = sum(1 for g in gaps if g == 0.0)
    out = {"n_traces": n,
           "dedup_accuracy": dedup_ok / n if n else float("nan"),
           "end_to_end_genuine": genuine / n if n else float("nan"),
           "false_credit": fc / n if n else float("nan"),
           "exact_minimal_of_genuine": exact / len(gaps) if gaps else float("nan"),
           "mean_size_gap_genuine": float(np.mean(gaps)) if gaps else float("nan")}
    if campaigns is not None:
        # L3-source provenance for the LIVE off-the-shelf path: the open model is called LIVE (memoised per
        # pair), so this end-to-end result is NOT bit-reproducible by design (disclosed) -- the breakdown self-
        # documents the live usage: l3_live model calls, l3_memo cache reuses, l2_decided settled without L3.
        ids = [c[1] for c in campaigns.values()]
        out["l3_provenance"] = {"source": "live_open_model", "model": model,
                                "l3_live": sum(i.stats.get("l3_live", 0) for i in ids),
                                "l3_memo": sum(i.stats.get("l3_memo", 0) for i in ids),
                                "l2_decided": sum(i.stats.get("l2_decided", 0) for i in ids)}
    return out


def run_multiseed(n_traces: int = 40, seeds: int = 8, *, model_name: str = "llama3.1:8b", host=None,
                  judge=None, dump_params=None, deduper=None) -> dict:
    """Run the scenario over ``seeds`` independent seeds and aggregate the per-seed summaries. SUBSTANTIATES
    the end-to-end genuine RANGE (a single live run is not bit-reproducible -- live model + OTA channel), and
    confirms the dedup accuracy + 0 false-credit are ROBUST across seeds. Returns per-seed summaries + a
    mean/min/max aggregate. With the live model+binary this is the disclosed-live end-to-end measurement; with a fake
    judge + mocked binary it is the deterministic CI check (the robust invariants reproduce)."""
    def _agg_seed(key):
        vs = [p[key] for p in per if p[key] == p[key]]           # drop NaN (e.g. exact-min with no genuine PoC)
        return {"mean": float(np.mean(vs)), "min": float(min(vs)), "max": float(max(vs)), "n": len(vs)} if vs else None

    per = []
    for s in range(seeds):
        rows, confusion, campaigns = run_scenario(n_traces, model_name=model_name, host=host, seed=s,
                                                  judge=judge, dump_params=dump_params, deduper=deduper)
        per.append(_summary(rows, confusion, campaigns, model_name))
    return {"suite": "scenario_multiseed", "n_traces": n_traces, "n_seeds": seeds,
            "genuine": _agg_seed("end_to_end_genuine"), "dedup_accuracy": _agg_seed("dedup_accuracy"),
            "false_credit": _agg_seed("false_credit"), "exact_minimal_of_genuine": _agg_seed("exact_minimal_of_genuine"),
            "per_seed": per}


def main() -> int:
    ap = argparse.ArgumentParser(prog="benchmarks.scenario",
                                 description="full real-deployment scenario: fuzz-trace -> dedup -> window -> RDD -> PoC, 6 bugs")
    ap.add_argument("--traces", type=int, default=40)
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--host", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=1, help=">1 runs the multi-seed range (substantiates genuine)")
    a = ap.parse_args()
    if a.seeds > 1:                                            # the multi-seed RANGE (the disclosed-live end-to-end claim)
        m = run_multiseed(a.traces, a.seeds, model_name=a.model, host=a.host)
        print(f"=== SCENARIO multi-seed — {a.seeds} seeds x {a.traces} traces; live binary + L3 ({a.model}) ===")
        for k in ("genuine", "dedup_accuracy", "false_credit", "exact_minimal_of_genuine"):
            v = m[k]
            print(f"  {k:24}: mean {v['mean']:.3f}  range [{v['min']:.3f}, {v['max']:.3f}]  (n={v['n']})")
        print("  LIVE -> not bit-reproducible; the RANGE is the claim. dedup + 0 false-credit are the ROBUST invariants.")
        return 0
    print(f"=== SCENARIO — {a.traces} fuzzer traces across {len(_BUGS)} real bugs; dedup->window->RDD->PoC; live binary + L3 ({a.model}) ===")
    rows, confusion, campaigns = run_scenario(a.traces, model_name=a.model, host=a.host, seed=a.seed)
    s = _summary(rows, confusion, campaigns, a.model)
    print(f"  crash-dedup accuracy : {s['dedup_accuracy']:.3f}   (correctly routed crash -> family)")
    print(f"  end-to-end genuine   : {s['end_to_end_genuine']:.3f}   (a PoC that REALLY crashes the right bug)")
    print(f"  false-credit         : {s['false_credit']:.3f}")
    print(f"  exact-minimal (of genuine PoCs) : {s['exact_minimal_of_genuine']:.3f}   "
          f"mean size-gap {s['mean_size_gap_genuine']:.3f}   (vs the PERFECT true-minimal)")
    lp = s["l3_provenance"]
    print(f"  L3-source ({lp['model']}, LIVE -- not bit-reproducible by design): {lp['l3_live']} live judgments / "
          f"{lp['l3_memo']} memo reuses / {lp['l2_decided']} L2-decided")
    print("  dedup confusion (ground-truth row -> predicted col):")
    for b in _BUGS:
        print(f"    {b}: " + "  ".join(f"{p or '∅'}={confusion[b][p]}" for p in (*_BUGS, None) if confusion[b][p]))
    print("  LIVE = real per-bug binary crash-truth + dump, and the open-model L3 ;  MODELLED = the fuzzer + OTA noise")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
