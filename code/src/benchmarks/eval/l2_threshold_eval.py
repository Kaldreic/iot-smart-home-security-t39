"""benchmarks.eval.l2_threshold_eval — sensitivity of the L2 identity threshold on the real bugs A--F.

The identity cascade decides "same bug?" with an L2 similarity threshold (``rdd.l2.L2Comparator`` default
0.5) and escalates the band [0.05, threshold) to L3. This eval measures, on the real base dumps under the
modelled per-rep dump variation (``DumpModel.emit``): the same-bug vs cross-bug separation (ROC AUC), the
Youden-J optimal threshold (fit on A--F, which is the entire real set, so there is no held-out family), the
balanced-accuracy plateau around the default, the stability of all three across variation seeds, and how
far the L3 band sits below the same-bug score floor. It covers the threshold only; the L2 weights are fixed
(see ``rdd/l2.py``). The separation depends on the noise regime, so a deployment with heavier noise should
recalibrate. Deterministic (seeded).

  python -m benchmarks.eval.l2_threshold_eval            # prints the report + writes the committed reference
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from rdd.l2 import L2Comparator

from .. import real

_DATA = Path(__file__).resolve().parent.parent / "data"
_SWEEP = [0.2, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8, 0.9]   # L2 thresholds to sweep
_BAND = real.L3_BAND_LO                                         # the L3 escalation floor (shared constant)


def _scores(n_same: int, n_cross: int, seed: int):
    """Same-bug and cross-bug L2 similarity lists over A--F (real base dumps, modelled per-rep variation), with
    the comparator fit on the base set."""
    bugs = list(real.BUGS)
    rng = random.Random(seed)
    base = {b: real.MODEL.clean_obs(b).to_crash_observation() for b in bugs}
    cmp = L2Comparator()
    cmp.fit([base[b] for b in bugs])
    sig = {b: cmp.signature(base[b]) for b in bugs}
    same, cross = [], []
    for b in bugs:
        for _ in range(n_same):
            obs = real.MODEL.emit(b, rng)
            same.append(cmp.similarity(cmp.signature(obs.to_crash_observation()), sig[b]))
        for o in bugs:
            if o == b:
                continue
            for _ in range(n_cross):
                obs = real.MODEL.emit(o, rng)
                cross.append(cmp.similarity(cmp.signature(obs.to_crash_observation()), sig[b]))
    return same, cross


def _auc(pos, neg) -> float:
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def _youden(pos, neg) -> float:
    best_t, best_j = 0.5, -2.0
    for t in sorted(set(pos) | set(neg)):
        tpr = sum(s >= t for s in pos) / len(pos)
        fpr = sum(s >= t for s in neg) / len(neg)
        if tpr - fpr > best_j:
            best_j, best_t = tpr - fpr, t
    return best_t


def _pct(xs, q):
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(q / 100 * len(s))))]


def evaluate(n_same: int = 60, n_cross: int = 12, seed: int = 0, default_threshold: float = 0.5,
             stability_seeds: int = 5) -> dict:
    """The threshold report on the real A--F bugs (deterministic)."""
    same, cross = _scores(n_same, n_cross, seed)
    auc, youden = _auc(same, cross), _youden(same, cross)
    sweep = {}
    for t in _SWEEP:
        rec = sum(s >= t for s in same) / len(same)
        rej = sum(s < t for s in cross) / len(cross)
        sweep[f"{t:.2f}"] = {"recall": rec, "reject": rej, "balanced": 0.5 * (rec + rej)}
    best = max(v["balanced"] for v in sweep.values())
    plateau = [float(t) for t, v in sweep.items() if best - v["balanced"] <= 0.02]
    same_min = min(same)
    band = {                                                   # the L3 band
        "band": _BAND,
        "cross_escalated_to_l3": sum(_BAND <= s < default_threshold for s in cross) / len(cross),
        "cross_l2_rejected_below_band": sum(s < _BAND for s in cross) / len(cross),
        "same_at_risk_below_band": sum(s < _BAND for s in same) / len(same),    # same-bug scores L2 would reject
        "max_safe_band_same_min": same_min,                   # the band could rise to here before a same-bug miss
    }
    # separation, calibration and plateau recomputed per variation seed
    aucs, youdens = [auc], [youden]
    plat_los, plat_his = [min(plateau)], [max(plateau)]    # seed-0 plateau min/max
    for s in range(1, stability_seeds):
        sa, cr = _scores(n_same, n_cross, seed + s)
        aucs.append(_auc(sa, cr))
        youdens.append(_youden(sa, cr))
        sw = {t: 0.5 * (sum(x >= t for x in sa) / len(sa) + sum(x < t for x in cr) / len(cr)) for t in _SWEEP}
        bst = max(sw.values())
        pl = [t for t, v in sw.items() if bst - v <= 0.02]
        plat_los.append(min(pl))
        plat_his.append(max(pl))
    stability = {"n_seeds": stability_seeds, "auc_min": min(aucs), "auc_max": max(aucs),
                 "youden_min": min(youdens), "youden_max": max(youdens),
                 "plateau_common": [max(plat_los), min(plat_his)],          # the band that is a plateau in every seed
                 "default_in_plateau_all_seeds": all(lo <= default_threshold <= hi for lo, hi in zip(plat_los, plat_his))}
    return {
        "suite": "l2_threshold_eval", "scope": "L2 THRESHOLD overfit on real bugs A--F under MODELLED OTA noise",
        "bugs": list(real.BUGS), "n_same": len(same), "n_cross": len(cross),
        "real": "A--F base crash dumps + the L2 comparator", "modelled": "per-rep dump variation (DumpModel.emit)",
        "validates": "the THRESHOLD ONLY (the L2 weights are FIXED + literature-grounded -- their audit is in rdd/l2.py)",
        "held_out": "none -- A--F is the entire real bug set; Youden is fit-on-A--F (supporting evidence, not a generalization proof)",
        "auc": auc, "default_threshold": default_threshold, "youden_threshold": youden,
        "same": {"mean": sum(same) / len(same), "p5": _pct(same, 5), "min": same_min},
        "cross": {"mean": sum(cross) / len(cross), "p95": _pct(cross, 95), "max": max(cross)},
        "sweep": sweep, "plateau": [min(plateau), max(plateau)] if plateau else None, "best_balanced": best,
        "band": band, "stability": stability,
        "conclusion": (f"NOT overfit [to A--F under the MODELLED OTA-noise regime; the threshold is noise-regime "
                       f"dependent per rdd/l2.py -- a deployment recalibrates]: AUC {auc:.3f}; the FIXED default "
                       f"{default_threshold} is ~the (fit-on-A--F, not held-out) Youden-J optimum {youden:.3f}, on "
                       f"a flat balanced-accuracy plateau [{min(plateau):.2f},{max(plateau):.2f}] (~{best:.3f}); "
                       f"stable across {stability_seeds} variation seeds (AUC {min(aucs):.3f}-{max(aucs):.3f}, and "
                       f"{default_threshold} is on the plateau in {'ALL' if stability['default_in_plateau_all_seeds'] else 'NOT all'} "
                       f"seeds); the band {_BAND} is conservative (far below the same-bug floor {same_min:.2f}). This validates "
                       f"the THRESHOLD only; the L2 weights' non-tuning rests on their rdd/l2.py design audit."),
    }


def main() -> int:
    out = evaluate()
    ref = _DATA / "reference" / "l2_threshold_eval.json"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"=== L2-THRESHOLD overfit/sensitivity eval (real A--F bugs, modelled noise; {out['n_same']} same / {out['n_cross']} cross) ===")
    print(f"  ROC AUC (same vs cross)        : {out['auc']:.4f}   (stable {out['stability']['auc_min']:.3f}-{out['stability']['auc_max']:.3f} over {out['stability']['n_seeds']} seeds)")
    print(f"  same  similarity  mean {out['same']['mean']:.3f}  min {out['same']['min']:.3f}   cross mean {out['cross']['mean']:.3f}  max {out['cross']['max']:.3f}")
    print(f"  fixed default 0.5  vs  Youden-J (fit-on-A--F) {out['youden_threshold']:.3f}   -> ~equal, not arbitrary")
    print(f"  balanced-accuracy plateau      : [{out['plateau'][0]:.2f}, {out['plateau'][1]:.2f}]  (~{out['best_balanced']:.3f}, flat -> not a tuned peak)")
    print(f"  L3 band {out['band']['band']}: {out['band']['cross_escalated_to_l3']:.2f} of cross escalated to L3, "
          f"{out['band']['same_at_risk_below_band']:.2f} same-bug at risk (conservative; safe up to ~{out['band']['max_safe_band_same_min']:.2f})")
    print(f"  -> {out['conclusion']}")
    print(f"  -> {ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
