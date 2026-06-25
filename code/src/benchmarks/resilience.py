"""benchmarks.resilience — B2: the consolidated synthetic resilience sweep, AirBug vs RDD.

The statistical-power complement to B1's real head-to-head (``benchmarks.headtohead``): a LARGE,
heterogeneous population of REAL-ANCHORED synthetic bugs (the scale MUST be synthetic — only ~6 real
emulable Zephyr controller bugs exist, disclosed) swept across the edge-case STRESS REGIMES that map
WHERE the exact-id baseline breaks and the robust pipeline holds. Replaces the former scale(800x6) +
resilience suites with ONE sweep. A pure HEAD-TO-HEAD: the lever / ablation decomposition is B3 (real target).

TWO AS-SHIPPED ARMS (each tool exactly as deployed — no knob is ablated to flatter or stress it):
  * AirBug (baseline) = the increasing-cardinality enum minimiser + exact-id identity. Fixed-K: it
                        accepts the first positive read without re-sampling (no flaky-FN defence).
  * RDD (tool)        = the robust pipeline (maximal-probe + seed-find + ddmin + truncated-SPRT +
                        L2/L3 identity), run decorrelated — RDD's shipped deployment recipe.

SIX REGIMES (each over-rides ONE sampling axis to isolate a stressor; + an OVERALL pool):
  standard     — the committed heterogeneous mix
  high_card    — multi-packet minimals k>=3 (exact-id strains)
  suppressor   — ~70% NON-MONOTONE bugs (RDD's robust seed-finder recovers; the REAL suppressor is in B1)
  far_trigger  — the trigger sits at the least-recent slots
  deep_noise   — harsh OTA channel (high false-negative)
  wide_window  — large candidate space
(The DRAMATIC suppressor result — bare ddmin SEED-BAILS to 0 while the robust seed-finder recovers — is the
ABLATION, which is B3; in this 2-arm head-to-head the suppressor regime is just AirBug-vs-RDD on non-monotone
bugs. No burst regime: with each tool at its shipped channel setting, varying the channel's rho_dev does not
separate them — RDD (decorrelated) is invariant to it and AirBug's read-once enum is insensitive to within-session
autocorrelation — so a rho_dev sweep would only duplicate `standard`. (The decorrelate KNOB itself does shift the
numbers, so it is held fixed per tool — RDD on, AirBug off, as shipped; see levers.py for the as-control variant.))

DETERMINISTIC, NO LLM, NO BINARIES: the in-loop crash identity is the validated no-LLM L2 + a
deterministic site-string L3 rule (``synthetic.id_l2l3``) — a conservative LOWER BOUND on RDD's real
cached-open-model L3 (which stays in B1's real anchor), tractable at scale and bit-reproducible. So B2
reproduces with NO model and its coherence gate runs in vanilla CI (every published leaf, exact — a
strictly stronger gate than the old genuine-only / tol-0.02 spine check).

METRICS (B1's set), scored vs the channel-off virtual-perfect the minimiser NEVER sees (genuine <=>
the PoC PROVABLY crashes the RIGHT bug), each a 95% bootstrap CI over the per-(bug, seed) rows:
  genuine / false_credit / exact_minimal (of genuine) / mean_size_gap (of genuine) / reads.
  (Cost = device READS, the fair algorithmic cost. B2 is a deterministic sim with no live L3 / real
   device, so the wall-clock usability cost — dominated by live-L3 latency — is a B1 metric, not B2's.)

  python -m benchmarks.resilience --bugs 2500 --seeds 5     # the headline sweep (~3 min)
  python -m benchmarks.resilience --coherence               # fresh run reproduces the committed reference (exact)

Run after `pip install -e code/` with PYTHONHASHSEED=0 (the real-anchored dump composition hashes bug ids).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks import scoring, synthetic

# The two AS-SHIPPED arms: (campaign-runner, identity-arm 'A'=exact-id | 'B'=L2/L3, kwargs). The baseline
# runs with NO decorrelation (not part of its mechanism); RDD runs decorrelated — its shipped recipe. (The
# ddmin-only ablation + the full lever decomposition are B3, on the real target — B2 is a pure head-to-head.)
ARMS = {
    "baseline": (scoring.run_baseline_campaign, "A", {}),
    "tool":     (scoring.run_tool_campaign,     "B", {"decorrelate": True}),
}
METRICS = ("genuine", "false_credit", "exact_minimal", "mean_size_gap", "reads")
# B2 never exercises the open model: the in-loop L3 is the deterministic site-string rule.
L3_PROVENANCE = {"source": "deterministic_rule", "model": None}

_DATA = Path(__file__).resolve().parent / "data"
_REF = _DATA / "reference" / "resilience.json"


def _arm_agg(rows: list[dict], n_seeds: int) -> dict:
    """B1's metric set as 95% bootstrap CIs that resample BUGS, not (bug, seed) rows i.i.d.: the rows nest
    n_seeds correlated seeds within each bug, so an i.i.d. row bootstrap understates the interval (see
    synthetic.ci). exact_minimal and mean_size_gap are conditioned on a genuine reproduction (a non-genuine row
    has no meaningful size). Rows arrive bug-consecutive in chunks of n_seeds (synthetic.run), so each chunk is
    one bug's cluster."""
    bugs = [rows[i:i + n_seeds] for i in range(0, len(rows), n_seeds)]
    genuine = lambda r: r["true_reproduced"]                      # noqa: E731
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
    """The full B2 sweep: the 2 as-shipped arms over every regime + an OVERALL pool (the rows of all
    regimes, so each arm's headline number is the pooled rate). Deterministic (PYTHONHASHSEED=0) ->
    bit-reproducible; the in-loop L3 is the no-LLM deterministic rule, so no model is ever called."""
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
    """Regenerate the committed B2 reference (there is no LLM cache to freeze — the sweep is
    deterministic and model-free; the reference IS the frozen result)."""
    out = run(n_bugs, n_seeds)
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n")
    return out


def coherence(tol: float = 1e-9) -> bool:
    """The fresh sweep reproduces the committed reference EXACTLY (every leaf), at the reference's own
    (n_bugs, n_seeds). Deterministic + model-free, so this is the vanilla-CI reproducibility gate."""
    ref = json.loads(_REF.read_text())
    fresh = scoring.clean_nan(run(ref["n_bugs"], ref["n_seeds"]))
    diffs = scoring.leaf_diffs(fresh, ref, tol=tol)
    print(f"B2 COHERENCE — fresh {ref['n_bugs']}x{ref['n_seeds']} sweep vs committed resilience.json "
          f"({len(diffs)} leaf diffs over the full reference):")
    for path, fv, rv in diffs[:25]:
        print(f"  [XX] {path}: fresh={fv} ref={rv}")
    print("COHERENT" if not diffs else "INCOHERENT")
    return not diffs


def _print(out: dict) -> None:
    g = lambda cell, key: cell[key][0]                           # the CI mean  # noqa: E731
    cell = lambda c: (f"{g(c, 'genuine'):.3f}/{g(c, 'false_credit'):.3f}/{g(c, 'exact_minimal'):.2f}/"
                      f"{g(c, 'mean_size_gap'):.2f}/{g(c, 'reads'):.1f}")        # noqa: E731
    print(f"=== B2 resilience — {out['n_campaigns_per_arm']} campaigns/arm "
          f"(AirBug vs RDD; {len(out['regimes']) - 1} regimes; {out['n_bugs']}x{out['n_seeds']}) ===")
    print("  each cell = genuine / false_credit / exact_minimal / mean_size_gap / reads")
    print(f"  {'regime':12} {'AirBug':>27} {'RDD':>27}")
    for reg, m in out["regimes"].items():
        print(f"  {reg:12} {cell(m['baseline']):>27} {cell(m['tool']):>27}")
    print("  AirBug = fixed-K enum + exact-id; RDD = the shipped robust pipeline (decorrelated). "
          "Cost = device reads (B2 has no live L3 / real device -> wall-clock is a B1 metric).")
    print(f"  L3-source: {out['l3_provenance']['source']} — no LLM (deterministic site-string rule; the cached "
          "open-model L3 lives only in B1's real anchor). Scored vs the channel-off virtual-perfect.")


def main() -> int:
    ap = argparse.ArgumentParser(prog="benchmarks.resilience",
                                 description="B2: synthetic resilience sweep, AirBug vs RDD (2-arm head-to-head)")
    ap.add_argument("--bugs", type=int, default=2500)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--freeze", action="store_true", help="regenerate the committed reference (resilience.json)")
    ap.add_argument("--coherence", action="store_true", help="fresh run must reproduce the committed reference (exact)")
    ap.add_argument("--out", type=str, default=None, help="also write the result JSON to PATH")
    a = ap.parse_args()
    scoring.require_hashseed0()                              # the synthetic sweep hashes bug ids -> needs seed 0
    if a.coherence:
        return 0 if coherence() else 1
    out = freeze(a.bugs, a.seeds) if a.freeze else run(a.bugs, a.seeds)
    _print(out)
    if a.out:
        Path(a.out).write_text(json.dumps(scoring.clean_nan(out), indent=1) + "\n")
        print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
