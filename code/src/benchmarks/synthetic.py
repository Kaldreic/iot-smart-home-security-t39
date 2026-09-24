"""benchmarks.synthetic — the engine of B2 (``benchmarks.resilience``): the real-anchored synthetic bug
population, the injected identity matchers, the per-(bug, seed) campaign driver and the bootstrap CI.

The device (the oracle, the channel-off truth, the dump composition and the symbol space) lives in
``emulation.synthetic``. Sampling axes: minimal size k in {1..6}, window W in {4..24}, trigger distance
(near/mid/far), suppressors 0/1/2 (non-monotone), crash-report shape and per-bug channel severity. The L3
here is a deterministic site-string rule with no model call; the cached open-model L3 stays in the real
anchor. Requires PYTHONHASHSEED=0 (``base_dump`` hashes bug ids).
"""

from __future__ import annotations

import random

import numpy as np

from emulation.baseline import exact_crash_id
from emulation.dump import DumpModel
from emulation.synthetic import FAULTS, FILES, POOL, LargeOracle, SynthBug, base_dump, sev_channel
from rdd.identity import L2Matcher

# The standard axis-choice lists (the committed population). A regime overrides specific axes; everything
# else stays standard. Sampling is deterministic in (n, seed, regime) given PYTHONHASHSEED=0.
_STD_AXES = {"W": [4, 5, 6, 8, 8, 10, 12, 14, 16, 20, 24], "k": [1, 1, 1, 2, 2, 2, 3, 3, 4, 5, 6],
             "dist": ["near", "near", "mid", "far"], "supp_w": [0.85, 0.11, 0.04],
             "sev": [0.6, 0.8, 1.0, 1.0, 1.3]}
# Stress regimes: each overrides one axis.
REGIMES = {
    "standard":    {},                                        # the committed mix
    "high_card":   {"k": [3, 4, 4, 5, 5, 6, 6]},              # multi-packet minimals k >= 3
    "suppressor":  {"supp_w": [0.30, 0.40, 0.30]},            # about 70% non-monotone bugs
    "far_trigger": {"dist": ["far", "far", "far", "mid"]},    # triggers at the least-recent slots
    "deep_noise":  {"sev": [1.0, 1.3, 1.6, 1.6, 2.0]},        # harsh channel (high false-negative)
    "wide_window": {"W": [12, 14, 16, 16, 20, 24]},           # large candidate space
}


def gen_population(n: int, seed: int = 7, regime=None) -> list[SynthBug]:
    """A heterogeneous population of ``n`` bugs. ``regime`` is a REGIMES name, an axis-override dict, or None for
    the standard mix."""
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


def id_l2l3(bug, l2: L2Matcher, obs) -> bool:                  # RDD: L2 + the deterministic L3 rule
    same, score = l2.is_same(bug.bid, obs)
    if same:
        return True
    if score < 0.05:
        return False
    txt = " ".join(obs.stack) + " " + " ".join(obs.log_lines)
    return (bug.site_fn in txt) or (f"{bug.site_file}:" in txt and ":??" not in txt)


def run(n_bugs: int, n_seeds: int, *, arms, seed: int = 7, regime=None):
    """Run ``arms`` ({label: (campaign fn, 'A'|'B', kwargs)}) over the population; identity arm 'A' is the exact
    matcher, 'B' is L2 + the rule. ``regime`` as in ``gen_population``. Each (bug, seed) seeds its own rng
    stream, so every arm sees the same noise for a given (bug, seed) and no campaign's noise depends on the
    campaigns run before it."""
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
    """95% bootstrap CI for the clustered design: each bug contributes n_seeds correlated rows (a bug whose minimal
    exceeds the baseline's cardinality cap is genuine=0 on every seed), so bugs are resampled with all their
    rows rather than rows i.i.d., which would understate the interval. ``groups`` is one filtered value list
    per bug. The point estimate is the pooled row mean, identical to a flat mean."""
    flat = np.array([v for g in groups for v in g], float)
    if not len(flat):
        return (float("nan"), float("nan"), float("nan"))
    sums = np.array([float(np.sum(g)) for g in groups])
    counts = np.array([len(g) for g in groups], float)
    rng = np.random.default_rng(0)
    ng = len(groups)
    boot = np.empty(b)
    for i in range(b):
        p = rng.integers(0, ng, ng)                              # resample bugs, keeping their rows
        c = counts[p].sum()
        boot[i] = sums[p].sum() / c if c else np.nan
    boot = boot[~np.isnan(boot)]
    return float(flat.mean()), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
