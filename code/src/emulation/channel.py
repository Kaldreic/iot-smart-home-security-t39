"""L1 — the physical wireless replay layer, modelled as a calibrated channel.

In deployment L1 is a fresh over-the-air exchange with the real target (take a
MITM position, re-establish the connection, replay the subset, observe the
device). Offline each rep's outcome is modelled as a stochastic channel so the L2
comparator, the L3 judge and the truncated-SPRT controller can be stress-tested
against realistic noise.

The RF chain is a two-state Gilbert-Elliott Markov chain (GOOD/BAD) with a
geometric BAD burst. Each state has its own miss, phantom and invalid rates:
misses (false negatives) come from the FlakeFlagger rerun corpus, phantoms are
rare, and an invalid (a connection-establishment failure) is discarded, never
counted as a miss. A sticky device-error term ``rho_dev`` (default 0; not swept by the committed benchmarks)
adds ordered-rerun autocorrelation the RF state cannot represent. Two knobs,
``reset`` and ``dev_settle``, de-correlate reps while preserving the marginal
loss rate. Calibration target: an among-valid miss rate of 0.44 (the FlakeFlagger
anchor). All randomness flows through an injected ``random.Random``.
"""

from __future__ import annotations

import enum
import random
from dataclasses import dataclass

from rdd.sprt import Rep


class Outcome(enum.Enum):
    """The three things a single wireless rep can yield."""

    REPRODUCED = "reproduced"          # the device exhibited the target crash
    NOT_REPRODUCED = "not_reproduced"  # the exchange ran, no target crash
    INVALID = "invalid"               # the exchange never happened (pairing/MITM drop)


# the canonical Outcome -> Rep map (full 3-key form, used as-is by causeswap; the other oracles map only
# the two non-reproduced outcomes through it and route REPRODUCED through the identity check by hand).
OUT2REP = {Outcome.REPRODUCED: Rep.YES, Outcome.NOT_REPRODUCED: Rep.NO, Outcome.INVALID: Rep.INVALID}


@dataclass(frozen=True)
class GEChannelParams:
    """Gilbert-Elliott RF, FlakeFlagger flakiness, device persistence and BLE invalids.

    Defaults: stationary P(BAD)=0.2, mean BAD burst 1/p_bg=5 reps; among-valid
    false-negative ~0.44 (the FlakeFlagger anchor), false-positive ~0.03, invalid
    ~0.07; rho_dev=0 (raise it to sweep observable burstiness); dev_settle is a
    boolean policy in {0,1} (a fractional rate is rejected -- it biases the marginal).
    """

    # --- Gilbert-Elliott RF channel (2-state Markov) ---
    p_gb: float = 0.05   # P(GOOD -> BAD)
    p_bg: float = 0.20   # P(BAD  -> GOOD); mean burst length = 1/p_bg = 5
    # --- device flakiness per RF state (FlakeFlagger-calibrated, FN-dominant) ---
    p_fn_good: float = 0.366   # calibrated so the among-valid FN ~ 0.44
    p_fn_bad: float = 0.836    #   (the FlakeFlagger anchor)
    p_fp_good: float = 0.02
    p_fp_bad: float = 0.07
    # --- wireless connection-establishment failure -> invalid trial ---
    p_invalid_good: float = 0.02
    p_invalid_bad: float = 0.27
    # --- device-state persistence: sticky-error autocorrelation (default 0; not swept) ---
    rho_dev: float = 0.0
    # --- de-correlation knobs ---
    reset: float = 0.0       # RF resample rate in [0,1] (cheap spacing; marginal-neutral)
    dev_settle: float = 0.0  # boolean {0,1}: power-cycle every rep, or never (costly)

    def __post_init__(self):
        if float(self.dev_settle) not in (0.0, 1.0):
            raise ValueError(
                "dev_settle must be boolean {0.0, 1.0}: a fractional power-cycle rate "
                "clears the device memory at a state-correlated rate and biases the "
                "among-valid marginal. Model 'power-cycle every rep' "
                "(1) vs 'never' (0); a continuous settle rate is not supported.")

    def stationary_bad(self) -> float:
        """Stationary probability of the BAD (bursty-loss) hidden state."""
        return self.p_gb / (self.p_gb + self.p_bg)


class L1Channel:
    """A stateful Gilbert-Elliott wireless-reproduction channel.

    ``step(truth)`` advances the hidden RF state + device-error memory and emits one
    ``Outcome``. ``truth`` is the ground-truth predicate "this subset reproduces the
    bug". Hidden RF state is exposed as ``.state`` (0=GOOD, 1=BAD) for testing.
    """

    GOOD, BAD = 0, 1

    def __init__(self, params: GEChannelParams, rng: random.Random):
        self.p = params
        self.rng = rng
        # start in the stationary regime so marginals hold from step 1
        self.state = self.BAD if rng.random() < params.stationary_bad() else self.GOOD
        self._prev_wrong: bool | None = None   # sticky-error memory (device persistence)

    def _advance(self) -> None:
        """One RF mixing step. With prob ``reset`` resample from stationary (a fresh,
        spaced connection); else a GE Markov transition. Both preserve the stationary
        law, so the marginal loss rate is invariant to ``reset``."""
        p = self.p
        if p.reset and self.rng.random() < p.reset:
            self.state = self.BAD if self.rng.random() < p.stationary_bad() else self.GOOD
            return
        if self.state == self.GOOD:
            if self.rng.random() < p.p_gb:
                self.state = self.BAD
        else:
            if self.rng.random() < p.p_bg:
                self.state = self.GOOD

    def step(self, truth: bool) -> Outcome:
        p = self.p
        self._advance()
        bad = self.state == self.BAD
        # device power-cycle (boolean): break the sticky-error memory every rep
        if p.dev_settle:
            self._prev_wrong = None
        # 1) connection-establishment failure: independent of bug truth and of the
        #    device-error memory (a failed exchange does not update device state).
        if self.rng.random() < (p.p_invalid_bad if bad else p.p_invalid_good):
            return Outcome.INVALID
        # 2) a valid exchange: sticky-Markov error -> marginal preserved, autocorr rho_dev
        p_err = (p.p_fn_bad if bad else p.p_fn_good) if truth else (p.p_fp_bad if bad else p.p_fp_good)
        rho = p.rho_dev
        if self._prev_wrong is None or rho == 0.0:
            wrong = self.rng.random() < p_err
        else:
            thr = (p_err + rho * (1 - p_err)) if self._prev_wrong else (p_err * (1 - rho))
            wrong = self.rng.random() < thr
        self._prev_wrong = wrong
        if truth:
            return Outcome.NOT_REPRODUCED if wrong else Outcome.REPRODUCED
        return Outcome.REPRODUCED if wrong else Outcome.NOT_REPRODUCED
