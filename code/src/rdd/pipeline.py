"""``minimize``: robust delta debugging under a noisy SPRT reproduction oracle.

The minimiser in ``rdd.minimizer`` is given two oracles built on ``rdd.sprt``. ``test``, used only by
ddmin inside the seed, consults a fresh ``MonotoneOracleCache`` first and otherwise runs the main SPRT
(``cfg``), recording only trusted verdicts. ``raw_test``, used for the full-window check, the seed
search, suppressor verification and final validation, runs a second uncached SPRT (``probe_cfg``) with
the same ``alpha`` and a tighter ``beta`` (default ``min(cfg.beta, 0.01)``), so that a lone crashing
complement is rarely missed on a flaky NO and each suppressor is an SPRT decision rather than a single
read. A flaky ``raw_test`` can still let a suppressor-containing seed reach the cache; that is harmless,
because credit rests on the uncached final validation rather than on seed scoping. ``decorrelate`` goes
to both SPRTs and is on by default, which the SPRT's independence precondition requires on a bursty
channel. ``ablate_robust=True`` disables the seed finder and verification, leaving classical ddmin on
the same oracle for the benchmark ablation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from .cache import MonotoneOracleCache
from .minimizer import robust_minimize
from .sprt import SPRTConfig, TruncatedSPRT, apply_to_cache


@dataclass(frozen=True)
class RDDResult:
    reproduced: bool             # recipe non-empty and validated on the raw oracle
    subset: frozenset | None     # the converged recipe (None if empty)
    size: int | None
    calls: int                   # device reads consumed
    validated: bool              # final validation confirmed the recipe reproduces
    cache_hits: int              # in-seed queries answered by the cache, at no device reads
    suppressors: tuple           # confirmed undoing-change suppressors (best-effort diagnostic)
    strategy: str                # "full" | "tear-down:k" | "build-up:k" | "exhausted" | "none"
    capped: bool                 # the seed search ran out of max_seed_calls


def minimize(oracle, bug, rng: random.Random, *, cfg: SPRTConfig = SPRTConfig(),
             probe_cfg: SPRTConfig | None = None, decorrelate: bool = True, max_remove: int = 2,
             max_build: int = 3, max_seed_calls: int | None = None, verify: bool = True,
             ablate_robust: bool = False) -> RDDResult:
    """Reproduce and minimise one bug; see the module docstring for the two oracles. With
    ``ablate_robust=True`` the seed finder and verification are off and the tool degrades to classical
    ddmin on the same SPRT oracle, which bails to ``[]`` on a suppressed full window."""
    if ablate_robust:
        max_remove = max_build = 0
        verify = False
    probe_cfg = probe_cfg if probe_cfg is not None else replace(cfg, beta=min(cfg.beta, 0.01))
    # The probe rng is seeded from a snapshot of the main rng, which is then restored, so the in-seed
    # ddmin sees the same noise realisation as the ddmin-only ablation and the minimiser is the only difference.
    _st = rng.getstate()
    rng_probe = random.Random(rng.getrandbits(63))
    rng.setstate(_st)
    cache = MonotoneOracleCache()                      # fresh per call: it only sees this run's seed
    sprt_main = TruncatedSPRT(cfg)                      # in-seed ddmin
    sprt_probe = TruncatedSPRT(probe_cfg)              # non-monotone probes: uncached, tighter beta
    calls0 = oracle.calls
    hits = [0]

    def test(subset) -> bool:                          # cached two-tier oracle, for ddmin inside the seed only
        s = frozenset(subset)
        ans = cache.query(s)                           # tier 1: monotone closure
        if ans is not None:
            hits[0] += 1
            return ans
        v = sprt_main.run(oracle.rep_session(bug, s, rng, decorrelate=decorrelate))   # tier 2: SPRT
        apply_to_cache(cache, s, v)                    # only trusted verdicts are recorded
        return v.decision

    def raw_test(subset) -> bool:                      # uncached SPRT for the non-monotone probes
        return sprt_probe.run(oracle.rep_session(bug, subset, rng_probe, decorrelate=decorrelate)).decision

    # An oracle that exposes identity_truth gets it wired in as the final-validation identity guard;
    # otherwise the guard is off and behaviour is unchanged.
    _idt = getattr(oracle, "identity_truth", None)
    identity_check = (lambda subset: _idt(bug, subset)) if _idt is not None else None
    res = robust_minimize(range(bug.window), test, raw_test=raw_test, identity_check=identity_check,
                          max_remove=max_remove, max_build=max_build, max_seed_calls=max_seed_calls, verify=verify)
    subset = frozenset(res.recipe) if res.recipe else None
    return RDDResult(res.reproduced, subset, (len(res.recipe) or None), oracle.calls - calls0,
                     res.validated, hits[0], tuple(res.suppressors), res.strategy, res.capped)


__all__ = ["minimize", "RDDResult"]
