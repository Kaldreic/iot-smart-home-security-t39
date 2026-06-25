"""The truncated-SPRT controller -- turns a noisy per-rep oracle into (decision, trust).

A single wireless rep is a noisy Bernoulli read of "did subset S reproduce the TARGET
bug?" (= L1 produced a crash AND the L2/L3 identity judged it the target). The controller runs reps
SEQUENTIALLY and stops as soon as the evidence is decisive -- Wald's Sequential
Probability Ratio Test [Wald'45], the optimal expected-sample-size test for a target
error pair, applied to a noisy oracle. Four design points the detector needs:

  * ASYMMETRIC error. false-YES (declare "reproduces" when it does not -> ddmin shrinks
    into a non-reproducing cone, SEVERE, ~unrecoverable) is controlled at a TIGHT alpha;
    false-NO (declare "not" when it does -> mild bloat / empty, recoverable) at a looser
    beta. The SPRT boundaries A=log((1-beta)/alpha), B=log(beta/(1-alpha)) encode this:
    it takes MORE evidence to accept YES than to accept NO. (Wald's A,B are APPROXIMATE;
    discrete-LLR overshoot makes the in-model error CONSERVATIVE -- realised below the
    nominal bound -- save for marginal boundary excess as p1->1.) A YES additionally
    requires >= min_yes_reps VALID reps -- the evidence must be SUSTAINED, not a lucky early
    burst (a minimum-evidence floor; see PRECONDITION 2(b)).

  * ALWAYS HALTS. The test is TRUNCATED at n_max VALID reps (the hardware budget). On
    truncation it forces the SAFE decision -- NO (the mild error) -- and flags LOW TRUST,
    so the result is not cached and the caller re-escalates rather than locking in a guess.

  * INVALID reps are missing DATA, not evidence. A failed exchange (pairing/MITM drop)
    carries no information about reproduction, so it is discarded from the SPRT; a cap on
    invalids guards against an unhealthy link/device -> an explicit UNHEALTHY abstain
    (distinct from "did not reproduce").

  * TRUST OUTPUT feeds the tier-1 cache: a DECIDED verdict is trustworthy (cache it); a
    CAPPED or UNHEALTHY verdict is low-trust (``MonotoneOracleCache.observe(.., trustworthy
    =False)`` -> a no-op that re-escalates). See ``apply_to_cache``.

PRECONDITIONS for "false-YES <= alpha" (BOTH load-bearing -- violating either breaks the
SEVERE-error control, and a wrongly-DECIDED YES is trust=True -> cached -> propagated
upward forever by the monotone tier-1 cache, the ~unrecoverable poisoning the two-tier
design exists to prevent). The guarantee is NOT unconditional:

  1. INDEPENDENT reps. The log-likelihood increments assume i.i.d. reps. Bursty
     wireless/device correlation (autocorrelation rho>0) inflates the realised false-YES
     ABOVE alpha -- INDEPENDENTLY of PRECONDITION 2: it breaches even for subsets well
     inside the null. L1 MUST de-correlate reps (space / reset / dev_settle so rho->0) -- a
     HARD precondition the detector relies on (end-to-end, L1 dev_settle pulls the realised
     false-YES back below alpha), not a soft caveat. min_yes_reps does NOT help here (a
     correlated burst clears any reps floor). See L1's reset/dev_settle knobs.

  2. TRUE non-reproduce rate <= p0. The point-null SPRT controls false-YES only on the
     null {true rate <= p0}. p0 is therefore the non-reproduce CEILING -- set it to the
     WORST per-rep YES rate of a subset you must still call NO (clean FP + any tolerable
     flakiness), NOT a nominal FP value. In the INDIFFERENCE ZONE (p0 < true < p1) -- a
     partially-reproducing / flaky subset -- NEITHER error is bounded (standard SPRT) and
     the realised false-YES rises MONOTONICALLY with the true rate. No sequential test
     controls error INSIDE its own indifference zone -- you SHRINK the zone. Defences, in
     order of force:
       (a) PRIMARY -- set p0 conservatively to the worst tolerated rate. This is the lever,
           but NOT free: one config judges EVERY subset, so raising p0 shrinks the p1-p0
           separation and inflates the GENUINE reproducer's false-NO + reps. Set p0 to the
           worst tolerated rate and NO higher -- it pays the mild error to buy down the severe.
       (b) a minimum-evidence FLOOR -- min_yes_reps never commits the irreversible severe
           YES on fewer than that many reps. It trims false-YES just ABOVE p0 but its effect
           DEEP in the zone is modest; a floor, not the fix. Do not lean on it in place of (a).
       (c) the ultimate net -- the converged recipe is FINAL-VALIDATED (Phase 4) by an
           INDEPENDENT re-confirming run before it is committed (escape ~ fY^2). This
           rescues a MODEST p0 underestimate, NOT a gross one -- so (a) must still bracket
           the worst rate; (c) is a backstop, not a substitute.

The false-NO (mild) direction is the deliberately looser side: truncation forces a capped
truly-reproducing subset to a safe NO, which can lift false-NO above beta -- the honest,
chosen direction of the tradeoff. (No min-reps guard on the NO side: a fast NO is cheap
and recoverable.)
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass


class Rep(enum.Enum):
    YES = "yes"          # this rep reproduced the target crash
    NO = "no"            # the exchange ran, did not reproduce
    INVALID = "invalid"  # the exchange never happened (missing data)


@dataclass(frozen=True)
class SPRTConfig:
    alpha: float = 0.01      # false-YES (severe) -- tight
    beta: float = 0.10       # false-NO (mild) -- loose
    p0: float = 0.05         # non-reproduce CEILING: worst per-valid-rep P(YES) of a subset
                             # you must still call NO (FP + tolerable flakiness). The
                             # false-YES guarantee holds on {true rate <= p0} ONLY -- see
                             # PRECONDITION 2. Raise it to widen the protected null.
    p1: float = 0.55         # per-valid-rep P(YES | subset reproduces) ~ 1-FN(among valid)
    n_max: int = 16          # truncation: max VALID reps (hardware budget)
    invalid_cap: int = 8     # max INVALID reps before declaring the link unhealthy
    min_yes_reps: int = 3    # a DECIDED-YES needs >= this many VALID reps (sustained
                             # evidence -- blocks a lucky early burst in the indifference
                             # zone from locking in the SEVERE error). No NO-side analogue.

    def __post_init__(self):
        if not (0 < self.p0 < self.p1 < 1):
            raise ValueError("require 0 < p0 < p1 < 1 (the oracle must be informative)")
        if not (0 < self.alpha < 1 and 0 < self.beta < 1):
            raise ValueError("alpha, beta in (0,1)")
        if self.alpha + self.beta >= 1:                  # else the Wald accept-YES boundary A = log((1-beta)/alpha)
            raise ValueError("require alpha + beta < 1 (else the SPRT decision boundaries degenerate)")
        if not (1 <= self.min_yes_reps <= self.n_max):
            raise ValueError("require 1 <= min_yes_reps <= n_max (YES must be reachable)")


class Status(enum.Enum):
    DECIDED = "decided"      # a boundary was crossed -> trustworthy
    CAPPED = "capped"        # n_max reached -> forced safe-NO, low trust
    UNHEALTHY = "unhealthy"  # too many invalid exchanges -> abstain, low trust


@dataclass(frozen=True)
class Verdict:
    decision: bool   # reproduced the target bug?
    trust: bool      # decided (True) vs capped/unhealthy (False)
    reps: int        # VALID reps consumed
    invalid: int     # INVALID reps seen
    status: Status


class TruncatedSPRT:
    def __init__(self, cfg: SPRTConfig = SPRTConfig()):
        self.cfg = cfg
        self.A = math.log((1 - cfg.beta) / cfg.alpha)      # upper -> accept YES (reproduces)
        self.B = math.log(cfg.beta / (1 - cfg.alpha))      # lower -> accept NO
        self.l_yes = math.log(cfg.p1 / cfg.p0)             # LLR step for a YES rep (>0)
        self.l_no = math.log((1 - cfg.p1) / (1 - cfg.p0))  # LLR step for a NO rep (<0)

    def run(self, rep_fn) -> Verdict:
        """``rep_fn() -> Rep`` performs one wireless rep. Sequential, truncated, always
        halts. Returns a Verdict; INVALID reps are retried up to ``invalid_cap``."""
        cfg = self.cfg
        llr = 0.0
        valid = invalid = 0
        while valid < cfg.n_max:
            o = rep_fn()
            if o is Rep.INVALID:
                invalid += 1
                if invalid >= cfg.invalid_cap:
                    return Verdict(False, False, valid, invalid, Status.UNHEALTHY)
                continue
            valid += 1
            llr += self.l_yes if o is Rep.YES else self.l_no
            # SEVERE side: accept YES only on SUSTAINED evidence (>= min_yes_reps valid
            # reps) -- a lucky 2-rep burst in the indifference zone must not lock it in.
            if llr >= self.A and valid >= cfg.min_yes_reps:
                return Verdict(True, True, valid, invalid, Status.DECIDED)
            if llr <= self.B:                     # MILD side: a fast NO is cheap + safe
                return Verdict(False, True, valid, invalid, Status.DECIDED)
        # truncated without crossing -> force the SAFE (mild) decision NO, low trust
        return Verdict(False, False, valid, invalid, Status.CAPPED)


def apply_to_cache(cache, subset, verdict: Verdict) -> None:
    """Wire the controller into the tier-1 monotone cache: a DECIDED verdict is recorded
    trustworthy; a CAPPED/UNHEALTHY verdict is a no-op (trustworthy=False) that
    re-escalates."""
    cache.observe(subset, verdict.decision, trustworthy=verdict.trust)
