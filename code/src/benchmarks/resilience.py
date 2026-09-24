"""benchmarks.resilience — B2: the synthetic resilience sweep, AirBugCatcher vs RDD.

A large population of real-anchored synthetic bugs (only about six real emulable controller bugs exist),
swept across regimes that each override one sampling axis of ``benchmarks.synthetic``: standard, high_card
(minimals k >= 3), suppressor (about 70% non-monotone bugs), far_trigger, deep_noise, wide_window, plus the
pooled OVERALL. No burst regime is swept; ``rho_dev`` stays at its default 0 in every regime.

Arms, each as shipped: baseline (enumeration + exact-id, no decorrelation), baseline_confirm (the
confirmation control: one confirming re-run) and tool (the robust pipeline, decorrelated). The in-loop L3 is
the deterministic site-string rule (``synthetic.id_l2l3``), so the sweep calls no model and is
bit-reproducible; each (bug, seed) has its own noise stream. Every arm is scored by ``scoring.score_bug``
against the channel-off truth; metrics are 95% bootstrap CIs over bugs, cost is device reads.

  python -m benchmarks.resilience --bugs 2500 --seeds 5     # the full sweep (~3 min)
  python -m benchmarks.resilience --coherence               # a fresh run must reproduce the reference

Requires PYTHONHASHSEED=0 (the synthetic dump composition hashes bug ids).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks import scoring, synthetic

# (campaign runner, identity arm 'A' = exact-id | 'B' = L2/L3, kwargs). The baseline runs without decorrelation
# (not part of its mechanism); the tool runs decorrelated, its shipped recipe. The ablation arms are B3.
ARMS = {
    "baseline":         (scoring.run_baseline_campaign, "A", {}),
    "baseline_confirm": (scoring.run_baseline_campaign, "A", {"confirm": 1}),   # the confirmation control
    "tool":             (scoring.run_tool_campaign,     "B", {"decorrelate": True}),
}
METRICS = ("genuine", "false_credit", "exact_minimal", "mean_size_gap", "reads")
# the in-loop L3 is the deterministic site-string rule; no model is called
L3_PROVENANCE = {"source": "deterministic_rule", "model": None}

_DATA = Path(__file__).resolve().parent / "data"
_REF = _DATA / "reference" / "resilience.json"


def _arm_agg(rows: list[dict], n_seeds: int) -> dict:
    """The metric set as 95% bootstrap CIs that resample bugs, not rows: each bug contributes n_seeds correlated
    rows (see ``synthetic.ci``). exact_minimal and mean_size_gap are conditioned on a genuine reproduction.
    Rows arrive bug-consecutive in chunks of n_seeds (``synthetic.run``)."""
    bugs = [rows[i:i + n_seeds] for i in range(0, len(rows), n_seeds)]
    genuine = lambda r: r["true_reproduced"]
    def grp(key, pred=lambda r: True, tf=None):                  # one filtered value-list per bug cluster
        f = tf or (lambda r: r[key])
        return [[f(r) for r in bug if r.get(key) is not None and pred(r)] for bug in bugs]
    return {
        "genuine":       synthetic.ci(grp("true_reproduced")),
        "false_credit":  synthetic.ci(grp("false_credit")),
        "exact_minimal": synthetic.ci(grp("size_gap", genuine, lambda r: 1.0 if r["size_gap"] == 0 else 0.0)),
        "mean_size_gap": synthetic.ci(grp("size_gap", genuine)),
        "reads":         synthetic.ci(grp("reads")),
    }


def run(n_bugs: int = 2500, n_seeds: int = 5) -> dict:
    """The full sweep: every arm over every regime, plus the OVERALL pool of all regimes' rows. Deterministic
    under PYTHONHASHSEED=0; no model is called."""
    regimes, pooled = {}, {lbl: [] for lbl in ARMS}
    for regime in synthetic.REGIMES:
        _bugs, rows = synthetic.run(n_bugs, n_seeds, arms=ARMS, regime=regime)
        regimes[regime] = {lbl: _arm_agg(rows[lbl], n_seeds) for lbl in ARMS}
        for lbl in ARMS:
            pooled[lbl] += rows[lbl]
    regimes["OVERALL"] = {lbl: _arm_agg(pooled[lbl], n_seeds) for lbl in ARMS}
    return {"suite": "resilience", "n_bugs": n_bugs, "n_seeds": n_seeds,
            "n_campaigns_per_arm": n_bugs * n_seeds * len(synthetic.REGIMES),
            "l3_provenance": L3_PROVENANCE, "regimes": regimes}


def freeze(n_bugs: int = 2500, n_seeds: int = 5, *, ref_path: Path = _REF) -> dict:
    """Regenerate the committed reference. There is no model cache to freeze; the reference is the result."""
    out = run(n_bugs, n_seeds)
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n", encoding="utf-8")
    return out


def coherence(tol: float = 1e-9) -> bool:
    """True iff a fresh sweep at the reference's own (n_bugs, n_seeds) reproduces every leaf of the committed
    reference."""
    ref = json.loads(_REF.read_text(encoding="utf-8"))
    fresh = scoring.clean_nan(run(ref["n_bugs"], ref["n_seeds"]))
    diffs = scoring.leaf_diffs(fresh, ref, tol=tol)
    print(f"B2 COHERENCE — fresh {ref['n_bugs']}x{ref['n_seeds']} sweep vs committed resilience.json "
          f"({len(diffs)} leaf diffs over the full reference):")
    for path, fv, rv in diffs[:25]:
        print(f"  [XX] {path}: fresh={fv} ref={rv}")
    print("COHERENT" if not diffs else "INCOHERENT")
    return not diffs


def _print(out: dict) -> None:
    g = lambda cell, key, f: "n/a" if cell[key][0] != cell[key][0] else format(cell[key][0], f)   # the CI mean
    cell = lambda c: (f"{g(c, 'genuine', '.3f')}/{g(c, 'false_credit', '.3f')}/{g(c, 'exact_minimal', '.2f')}/"
                      f"{g(c, 'mean_size_gap', '.2f')}/{g(c, 'reads', '.1f')}")
    print(f"=== B2 resilience — {out['n_campaigns_per_arm']} campaigns/arm "
          f"(AirBugCatcher vs RDD; {len(out['regimes']) - 1} regimes; {out['n_bugs']}x{out['n_seeds']}) ===")
    print("  each cell = genuine / false_credit / exact_minimal / mean_size_gap / reads")
    print(f"  {'regime':12} {'AirBugCatcher':>27} {'+ 1 confirmation':>27} {'RDD':>27}")
    for reg, m in out["regimes"].items():
        print(f"  {reg:12} {cell(m['baseline']):>27} {cell(m['baseline_confirm']):>27} {cell(m['tool']):>27}")
    print("  AirBugCatcher = fixed-K enum + exact-id; RDD = the shipped robust pipeline (decorrelated). "
          "Cost = device reads (B2 has no live L3 / real device -> wall-clock is a B1 metric).")
    print(f"  L3-source: {out['l3_provenance']['source']} — no LLM (deterministic site-string rule; the cached "
          "open-model L3 lives only in B1's real anchor). Scored vs the channel-off virtual-perfect.")


def main() -> int:
    ap = argparse.ArgumentParser(prog="benchmarks.resilience",
                                 description="B2: synthetic resilience sweep (AirBugCatcher, + 1 confirmation, RDD)")
    ap.add_argument("--bugs", type=int, default=2500)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--freeze", action="store_true", help="regenerate the committed reference (resilience.json)")
    ap.add_argument("--coherence", action="store_true", help="fresh run must reproduce the committed reference (exact)")
    ap.add_argument("--out", type=str, default=None, help="also write the result JSON to PATH")
    a = ap.parse_args()
    scoring.require_hashseed0()                              # the sweep hashes bug ids
    if a.coherence:
        return 0 if coherence() else 1
    out = freeze(a.bugs, a.seeds) if a.freeze else run(a.bugs, a.seeds)
    _print(out)
    if a.out:
        Path(a.out).write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n", encoding="utf-8")
        print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
