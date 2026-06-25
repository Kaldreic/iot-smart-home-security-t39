"""rdd.pipeline — the wired RDD tool: robust delta-debugging under a noisy SPRT reproduction oracle.

The tool wraps the non-monotone-robust minimiser (`minimiser.robust_minimize`) in a two-tier SPRT +
monotone-cache reproduction oracle. It is the deployable reproduction engine; concrete targets are supplied
as oracles by the benchmark suite. The *ddmin-only* behaviour — RDD with the robust seed-finder disabled,
i.e. classical delta-debugging on the same SPRT oracle — is available as an ABLATION (`minimize(...,
ablate_robust=True)`), used in the benchmarks to isolate the contribution of the robust minimiser; it is no
longer a co-equal "arm".

The four design obligations the robust minimiser imposes on its oracle wrapper, satisfied here:

  (1) SPRT-TRUSTED RAW PROBE ORACLE.  `robust_minimize`'s non-monotone-sensitive probes (Phase 0 maximal
      gate, Phase 1 seed-find, Phase 3 verify, Phase 4 final-validation) must run on an UNCACHED oracle
      that is also LOW-false-negative (a lone crashing complement must not be missed on a flaky NO).  So
      `raw_test` is a SEPARATE SPRT with a TIGHTER beta (default min(cfg.beta, 0.01)) and NO cache, while
      alpha stays at cfg.alpha (the credit-bearing false-YES bound that protects the final-validation).

  (2) IN-SEED CACHE -- subsets of the ACCEPTED seed only, with FINAL-VALIDATION as the real guarantee.
      `robust_minimize` consults the cached `test` ONLY in Phase 2 (ddmin INSIDE the seed `find_seed`
      accepted); Phases 0/1/3/4 use `raw_test`.  When the raw verdicts are correct (always, under a
      truthful oracle) the accepted seed is suppressor-free, so the cache only sees a monotone sublattice
      and the full-window NO never reaches it.  Under a FLAKY `raw_test`, a false-YES can make `find_seed`
      accept a non-crashing, suppressor-CONTAINING seed, and the cache then observes suppressor-containing
      queries -- but this is BENIGN: the correctness guarantee is the uncached SPRT-trusted Phase-4
      FINAL-VALIDATION (established at the unit level by the minimiser's split-oracle test + an at-scale
      sweep), NOT the seed-scoping; measured cache-on false-credit ~= cache-off, and false-credit stays 0
      under the contract.  (The pipeline tests assert the load-bearing invariant -- no false credit on a
      poisonable multi-suppressor bug, with the poisoning regime exercised -- not the false "cache never
      sees a suppressor" one.)

  (3) RESAMPLED SUPPRESSOR DIAGNOSTIC.  `undoing_change_verify` re-tests each re-addition on `raw_test`,
      which is the SPRT -- so each suppressor decision is an SPRT-trusted verdict, not a single flaky
      read (a raw_test==test default would fabricate suppressors under noise).

  (4) BURSTY NOISE.  `decorrelate` is threaded through to both SPRTs. As shipped, the RDD tool ALWAYS runs
      decorrelated (dev_settle + reset -- its deployment recipe), which restores the SPRT's i.i.d.-rep
      precondition (sprt.py) under the bursty channel; correlated reps are a disclosed threat the recipe is
      designed to remove, not a regime the benchmark suite sweeps.

Cost: the robust path pays the maximal gate + the seed search + the verify + the final-validation, all on
the (tighter-beta, more reps) probe SPRT -- a disclosed correctness-for-reads premium, paid in full only
on suppressor bugs (the monotone majority pays the gate + final-validation only).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from .cache import MonotoneOracleCache
from .minimizer import robust_minimize
from .sprt import SPRTConfig, TruncatedSPRT, apply_to_cache


@dataclass(frozen=True)
class RDDResult:
    reproduced: bool             # credits the target reproduced (recipe non-empty AND raw-validated)
    subset: frozenset | None     # the converged recipe (None iff empty)
    size: int | None
    calls: int                   # device reads consumed (the overhead currency)
    validated: bool              # Phase-4 RAW final-validation confirmed the recipe reproduces
    cache_hits: int              # tier-1 (in-seed) queries served with 0 device reads
    suppressors: tuple           # confirmed undoing-change suppressors (best-effort diagnostic)
    strategy: str                # "full" | "tear-down:k" | "build-up:k" | "exhausted" | "none"
    capped: bool                 # seed search hit max_seed_calls (budget floor) -- distinct from exhausted


def minimize(oracle, bug, rng: random.Random, *, cfg: SPRTConfig = SPRTConfig(),
             probe_cfg: SPRTConfig | None = None, decorrelate: bool = True, max_remove: int = 2,
             max_build: int = 3, max_seed_calls: int | None = None, verify: bool = True,
             ablate_robust: bool = False) -> RDDResult:
    """Reproduce + minimise one bug: cached two-tier `test` for the in-seed ddmin, SPRT-trusted uncached
    `raw_test` for the non-monotone probes. See the module docstring for the four obligations.

    `ablate_robust=True` disables the robust seed-finder (max_remove=max_build=0, verify off), so the tool
    degrades to classical ddmin on the same SPRT oracle -- the benchmark ablation that isolates the robust
    minimiser's contribution (it bails to [] on a suppressed full window, exactly as bare delta-debugging)."""
    if ablate_robust:
        max_remove = max_build = 0
        verify = False
    probe_cfg = probe_cfg if probe_cfg is not None else replace(cfg, beta=min(cfg.beta, 0.01))
    # SEPARATE deterministic probe rng, seeded WITHOUT perturbing the main stream (snapshot/restore):
    # the non-monotone probes (Phase 0/1/3/4) must not consume from the in-seed ddmin's rng, AND the main
    # rng must stay at its entry position -- so the tool's in-seed ddmin sees the IDENTICAL noise
    # realisation as the ddmin-only ablation, making the ONLY difference the minimiser, not the randomness.
    # (Sharing the rng, or seeding the probe by consuming from the main rng, both perturb the ddmin noise
    # realisation; snapshot/restore removes that artifact so the tool's monotone score == the ablation's.)
    _st = rng.getstate()
    rng_probe = random.Random(rng.getrandbits(63))
    rng.setstate(_st)
    cache = MonotoneOracleCache()                      # per-call; structurally seed-scoped (see docstring)
    sprt_main = TruncatedSPRT(cfg)                      # in-seed ddmin (cached path)
    sprt_probe = TruncatedSPRT(probe_cfg)              # non-monotone probes (uncached, tighter beta)
    calls0 = oracle.calls
    hits = [0]

    def test(subset) -> bool:                          # CACHED two-tier -- Phase-2 ddmin-in-seed ONLY
        s = frozenset(subset)
        ans = cache.query(s)                           # tier 1: monotone closure over the seed sublattice
        if ans is not None:
            hits[0] += 1
            return ans
        v = sprt_main.run(oracle.rep_session(bug, s, rng, decorrelate=decorrelate))   # tier 2: accurate
        apply_to_cache(cache, s, v)                    # trust-gated; only seed-subset observations land here
        return v.decision

    def raw_test(subset) -> bool:                      # UNCACHED SPRT-trusted -- Phase 0/1/3/4 (non-monotone)
        return sprt_probe.run(oracle.rep_session(bug, subset, rng_probe, decorrelate=decorrelate)).decision

    # Mode-2 cause-swap guard: if the oracle exposes a REAL-artifact identity check (identity_truth), wire it
    # into the minimiser's final-validation. Opt-in -- oracles whose raw_test is already target-specific (the
    # synthetic/cached-real benchmark oracles) omit it -> identity_check=None -> behaviour byte-unchanged.
    _idt = getattr(oracle, "identity_truth", None)
    identity_check = (lambda subset: _idt(bug, subset)) if _idt is not None else None
    res = robust_minimize(range(bug.window), test, raw_test=raw_test, identity_check=identity_check,
                          max_remove=max_remove, max_build=max_build, max_seed_calls=max_seed_calls, verify=verify)
    subset = frozenset(res.recipe) if res.recipe else None
    return RDDResult(res.reproduced, subset, (len(res.recipe) or None), oracle.calls - calls0,
                     res.validated, hits[0], tuple(res.suppressors), res.strategy, res.capped)


__all__ = ["minimize", "RDDResult"]
