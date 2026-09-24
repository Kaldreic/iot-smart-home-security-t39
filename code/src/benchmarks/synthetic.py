"""benchmarks.synthetic — the ENGINE for B2 (``benchmarks.resilience``): the real-anchored synthetic bug
population + the injected identity matchers + the per-(bug, seed) campaign driver + the bootstrap CI.

The statistical-power complement to the real anchor: a LARGE, HETEROGENEOUS population of synthetic bug
instances (the scale must be synthetic — only ~6 real emulable Zephyr controller bugs exist — disclosed),
every one real-anchored. The DEVICE (the oracle, the channel-off truth, the real-anchored dump composition,
the symbol space) lives in ``emulation.synthetic``; this module owns the EVALUATION half: it generates the
heterogeneous bug POPULATION, supplies the two INJECTED identity matchers (the exact-id baseline + the
deterministic no-LLM L2/L3 rule), drives the per-(bug, seed) campaigns, and bootstraps the CIs. The B2
headline (``benchmarks.resilience``) sweeps the REGIMES below and aggregates these rows into B1's metric set.

The sampling axes that map the score comparison across conditions + edge cases: minimality k in {1..6},
window W in {4..24}, trigger DISTANCE (near/mid/far), suppressors 0/1/2 (non-monotone -> the minimiser is
stressed), crash-report shape, per-bug channel severity. L3 here is the validated rule applied
DETERMINISTICALLY (conservative vs the real agents -> the tool's L3 is a lower bound; the real cached-agent
L3 stays in-loop in the real anchor). Run after `pip install -e code/`.
"""

from __future__ import annotations

import random

import numpy as np

from emulation.baseline import exact_crash_id
from emulation.dump import DumpModel
from emulation.synthetic import FAULTS, FILES, POOL, LargeOracle, SynthBug, base_dump, sev_channel
from rdd.identity import L2Matcher

# The STANDARD axis-choice lists (the committed heterogeneous population). A regime overrides specific axes;
# everything else stays standard. The sampling is deterministic in (n, seed, regime) given PYTHONHASHSEED=0
# (a fixed rng-call sequence), so B2's coherence gate reproduces every committed number byte-for-byte.
_STD_AXES = {"W": [4, 5, 6, 8, 8, 10, 12, 14, 16, 20, 24], "k": [1, 1, 1, 2, 2, 2, 3, 3, 4, 5, 6],
             "dist": ["near", "near", "mid", "far"], "supp_w": [0.85, 0.11, 0.04],
             "sev": [0.6, 0.8, 1.0, 1.0, 1.3]}
# Edge-case STRESS regimes — each isolates a stressor the AirBug exact-id baseline / a non-robust ddmin is
# known to struggle with, to map the resiliency gap of AirBug vs RDD.
REGIMES = {
    "standard":    {},                                        # the committed heterogeneous mix
    "high_card":   {"k": [3, 4, 4, 5, 5, 6, 6]},              # multi-packet minimals k>=3 (exact-id strains)
    "suppressor":  {"supp_w": [0.30, 0.40, 0.30]},            # ~70% NON-MONOTONE (ddmin BAILS; the robust regime)
    "far_trigger": {"dist": ["far", "far", "far", "mid"]},    # triggers at the least-recent slots
    "deep_noise":  {"sev": [1.0, 1.3, 1.6, 1.6, 2.0]},        # harsh OTA channel (high false-negative)
    "wide_window": {"W": [12, 14, 16, 16, 20, 24]},           # large candidate space
}


def gen_population(n: int, seed: int = 7, regime=None) -> list[SynthBug]:
    """Heterogeneous synthetic bug population. ``regime`` (a name in REGIMES, or an axis-override dict, or
    None=standard) overrides specific sampling axes to stress an edge case; None reproduces the committed mix."""
    ax = {**_STD_AXES, **(REGIMES[regime] if isinstance(regime, str) else (regime or {}))}
    rng = random.Random(seed)
    bugs = []
    for i in range(n):
        W = rng.choice(ax["W"])
        k = rng.choice(ax["k"])
        k = min(k, W - 1)
        dist = rng.choice(ax["dist"])
        if dist == "near":
            M = frozenset(range(W - k, W))                     # latest trigger == most-recent slot
        elif dist == "far":
            M = frozenset(range(0, k))                         # triggers at the least-recent slots
        else:
            M = frozenset(rng.sample(range(W), k))
        cand = [p for p in range(W) if p not in M]
        nsupp = rng.choices([0, 1, 2], weights=ax["supp_w"])[0]
        supps = tuple(rng.sample(cand, min(nsupp, len(cand)))) if cand else ()
        bugs.append(SynthBug(bid=f"b{i:04d}", window=W, minimal=M, suppressors=supps, distance=dist,
                             shape=rng.choice(["stack", "stack", "deep", "short", "site"]),
                             fault=rng.choice(FAULTS), site_fn=rng.choice(POOL),
                             site_file=rng.choice(FILES), sev=rng.choice(ax["sev"]),
                             k=k, crash_sig=f"bug-{i:04d}"))
    return bugs


_TARGET_EXACT: dict = {}


def id_exact(bug, obs) -> bool:                                # baseline: AirBugCatcher exact id
    return exact_crash_id(obs) == _TARGET_EXACT[bug.bid]


def id_l2l3(bug, l2: L2Matcher, obs) -> bool:                  # RDD: L2 + the deterministic (no-LLM) L3 rule
    same, score = l2.is_same(bug.bid, obs)
    if same:
        return True
    if score < 0.05:
        return False
    txt = " ".join(obs.stack) + " " + " ".join(obs.log_lines)
    return (bug.site_fn in txt) or (f"{bug.site_file}:" in txt and ":??" not in txt)


def run(n_bugs: int, n_seeds: int, *, arms, seed: int = 7, regime=None):
    """Run the given arms over the population. ``arms`` is a {label: (module, 'A'|'B', kwargs)} mapping;
    the identity-arm 'A' uses the exact matcher (baseline), 'B' uses L2+L3 (tool / ablation). ``regime``
    (a REGIMES name) stresses an edge case; None = the committed standard mix."""
    bugs = gen_population(n_bugs, seed, regime)
    model = DumpModel(base={b.bid: base_dump(b) for b in bugs})
    base_obs = {b.bid: model.clean_obs(b.bid) for b in bugs}
    _TARGET_EXACT.clear()
    _TARGET_EXACT.update({b.bid: exact_crash_id(base_obs[b.bid]) for b in bugs})
    l2 = L2Matcher(base_obs)

    def id_b(bug, obs):                                         # arm B identity closes over this population's L2
        return id_l2l3(bug, l2, obs)
    arm_identity = {"A": id_exact, "B": id_b}                   # inject the eval's matcher into the device oracle

    rows = {label: [] for label in arms}
    for b in bugs:
        cp = sev_channel(b.sev)
        ax = {"k": b.k, "W": b.window, "dist": b.distance, "shape": b.shape, "nsupp": len(b.suppressors)}
        for s in range(n_seeds):
            for label, (mod, oarm, kw) in arms.items():
                o = LargeOracle(arm_identity[oarm], model, cp)
                r = dict(mod(o, [b], random.Random(f"{b.bid}:{s}"), **kw)[0])   # own stream per (bug, seed)
                r.update(reads=o.calls, **ax)
                rows[label].append(r)
    return bugs, rows


def ci(groups, b=2000):
    """95% bootstrap CI for the CLUSTERED B2 design: each bug contributes n_seeds correlated seed-rows (a bug
    whose minimal exceeds the baseline's cardinality cap is genuine=0 on EVERY seed), so the bootstrap resamples
    BUGS -- each with ALL its rows -- not rows i.i.d. Resampling rows i.i.d. ignores the within-bug correlation
    and understates the interval. ``groups`` is one already-filtered value-list per bug. The point estimate is the
    pooled row-mean (BIT-IDENTICAL to a flat mean -- the fix widens the interval only, never the point)."""
    flat = np.array([v for g in groups for v in g], float)
    if not len(flat):
        return (float("nan"), float("nan"), float("nan"))
    sums = np.array([float(np.sum(g)) for g in groups])
    counts = np.array([len(g) for g in groups], float)
    rng = np.random.default_rng(0)
    ng = len(groups)
    boot = np.empty(b)
    for i in range(b):
        p = rng.integers(0, ng, ng)                              # resample BUGS (clusters), keep their rows
        c = counts[p].sum()
        boot[i] = sums[p].sum() / c if c else np.nan
    boot = boot[~np.isnan(boot)]
    return float(flat.mean()), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
