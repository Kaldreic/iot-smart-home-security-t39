"""Truncated sequential probability ratio test (Wald 1945) over noisy reproduction attempts.

Each rep is a Bernoulli read of "did subset S reproduce the target bug?". ``TruncatedSPRT.run`` draws
reps one at a time until the log-likelihood ratio crosses a boundary and returns a decision with a
trust flag. A false YES sends ddmin into a non-reproducing region, so it is bounded by a tight
``alpha`` and a YES also needs ``min_yes_reps`` valid reps; a false NO only bloats the recipe and gets
a looser ``beta``. At ``n_max`` valid reps the test is truncated and returns NO with ``trust=False``,
so the result is not cached and the subset is re-tested next time. Invalid reps (no exchange took
place) are skipped as missing data; ``invalid_cap`` of them ends the run as ``UNHEALTHY``, also low trust.

Two preconditions underlie the false-YES bound. Reps must be independent: correlated bursts inflate
the realised rate whatever ``min_yes_reps`` is, so the channel layer must de-correlate reps (settle
time, resets). And ``p0`` must be at least the true per-rep YES rate of every subset that has to be
called NO: it is a ceiling on tolerated flakiness, not a nominal false-positive rate. Between ``p0``
and ``p1`` neither error is bounded, as for any SPRT; the remedies, strongest first, are a conservative
``p0`` (paid for in reps and false NOs on genuine reproducers), the ``min_yes_reps`` floor, and the
minimiser's final validation of the converged recipe.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass


class Rep(enum.Enum):
    YES = "yes"          # the rep reproduced the target crash
    NO = "no"            # the exchange ran and did not reproduce
    INVALID = "invalid"  # the exchange never happened


@dataclass(frozen=True)
class SPRTConfig:
    alpha: float = 0.01      # false-YES bound (the severe error)
    beta: float = 0.10       # false-NO bound of decided runs (the mild error; truncation adds forced NOs)
    p0: float = 0.05         # ceiling on the per-valid-rep YES rate of a subset that must be called NO
    p1: float = 0.55         # per-valid-rep YES rate of a reproducing subset
    n_max: int = 16          # truncation point, in valid reps
    invalid_cap: int = 8     # invalid reps before the link is declared unhealthy
    min_yes_reps: int = 3    # a YES needs at least this many valid reps

    def __post_init__(self):
        if not (0 < self.p0 < self.p1 < 1):
            raise ValueError("require 0 < p0 < p1 < 1 (the oracle must be informative)")
        if not (0 < self.alpha < 1 and 0 < self.beta < 1):
            raise ValueError("alpha, beta in (0,1)")
        if self.alpha + self.beta >= 1:                  # else A = log((1-beta)/alpha) <= 0
            raise ValueError("require alpha + beta < 1 (else the SPRT decision boundaries degenerate)")
        if not (1 <= self.min_yes_reps <= self.n_max):
            raise ValueError("require 1 <= min_yes_reps <= n_max (YES must be reachable)")


class Status(enum.Enum):
    DECIDED = "decided"      # a boundary was crossed; trustworthy
    CAPPED = "capped"        # n_max reached; forced NO, low trust
    UNHEALTHY = "unhealthy"  # too many invalid exchanges; forced NO, low trust


@dataclass(frozen=True)
class Verdict:
    decision: bool   # reproduced the target bug?
    trust: bool      # True iff status is DECIDED
    reps: int        # valid reps consumed
    invalid: int     # invalid reps seen
    status: Status


class TruncatedSPRT:
    def __init__(self, cfg: SPRTConfig = SPRTConfig()):
        self.cfg = cfg
        self.A = math.log((1 - cfg.beta) / cfg.alpha)      # accept YES at or above
        self.B = math.log(cfg.beta / (1 - cfg.alpha))      # accept NO at or below
        self.l_yes = math.log(cfg.p1 / cfg.p0)             # LLR step per YES rep (> 0)
        self.l_no = math.log((1 - cfg.p1) / (1 - cfg.p0))  # LLR step per NO rep (< 0)

    def run(self, rep_fn) -> Verdict:
        """Call ``rep_fn() -> Rep`` until a boundary is crossed, ``n_max`` valid reps are used or
        ``invalid_cap`` invalid reps are seen, and return the ``Verdict``."""
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
            # A YES needs sustained evidence: a lucky early burst in the indifference zone must not lock it in.
            if llr >= self.A and valid >= cfg.min_yes_reps:
                return Verdict(True, True, valid, invalid, Status.DECIDED)
            if llr <= self.B:
                return Verdict(False, True, valid, invalid, Status.DECIDED)
        # truncated without a decision: forced NO, low trust
        return Verdict(False, False, valid, invalid, Status.CAPPED)


def apply_to_cache(cache, subset, verdict: Verdict) -> None:
    """Record ``verdict`` in the monotone cache; a capped or unhealthy verdict is passed as untrustworthy
    and therefore not recorded."""
    cache.observe(subset, verdict.decision, trustworthy=verdict.trust)
