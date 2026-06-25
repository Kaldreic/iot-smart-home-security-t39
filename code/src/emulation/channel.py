"""L1 -- the physical wireless replay layer, modelled as a calibrated channel.

In deployment L1 is a *fresh over-the-air exchange* with the real target device:
take a MITM position, (re)establish the connection, replay the packet subset,
observe the device. Offline (no hardware) we model the per-rep OUTCOME as a
calibrated stochastic channel so the rest of the detector -- the deterministic
comparator (L2), the single open-model L3 judge, and the truncated-SPRT
controller -- can be built and stress-tested against realistic noise.

Three things make wireless reproduction noisy, and the model captures all three:

  1. Device flakiness. A truly-reproducing subset is *missed* a large fraction of
     the time, and a non-reproducing subset occasionally *phantoms* a crash. We
     calibrate to the FlakeFlagger rerun corpus: false-negative ~0.44 (near a coin
     flip), false-positive ~0.03 -- strongly FN-dominant. [Luo+ FSE'14; FlakeFlagger]

  2. Bursty RF. Wireless loss is not i.i.d.; it clusters. The canonical model is
     Gilbert-Elliott: a 2-state Markov chain GOOD/BAD with per-state loss and a
     geometric burst length 1/p_bg in BAD. Stationary P(BAD)=p_gb/(p_gb+p_bg); the
     lag-k state autocorrelation is lambda^k with lambda=1-p_gb-p_bg. BLE field
     studies put a healthy link at <3% loss / 97-99% reliability, degrading sharply
     under interference -- our GOOD/BAD split. [Gilbert'60, Elliott'63; MDPI'21]

  3. Connection-establishment failure. A rep can fail to even exchange (pairing /
     MITM drop), which is NOT 'the bug did not reproduce' -- conflating the two is
     exactly how a recipe gets wrongly emptied. So the channel emits a third
     outcome, INVALID, that the controller must treat as a discarded trial, never
     as a false-negative.

BURSTINESS NOTE.
At the OBSERVABLE rep-outcome level the GE RF channel's autocorrelation is far
below the hidden RF-state autocorrelation, because the FN-dominant emission noise
attenuates it: observable_ac ~ eta*lambda (eta = the miss-variance the state
explains) -- an attenuation HEURISTIC, not a strict bound: within the calibrated
regime the measured autocorr sits ~15-25% BELOW eta*lambda. The unconditional-eta
form is exceeded only OUTSIDE that regime, at stationary P(BAD) > ~0.6 (a >50%-loss
link where conditioning on valid reps pushes P(BAD|valid) toward the variance-max
0.5); the exceedance is governed by P(BAD), NOT burst length / lambda (the ratio is
lambda-invariant), and the among-valid-weighted eta is the exact bound there.
Under realistic calibration this tops out near ~0.18 (interior) and cannot reach
the rho~0.6 regime. So RF modulation ALONE cannot model the consecutive-rerun
correlation a sequential controller must survive. We therefore add a SECOND,
orthogonal, marginal-PRESERVING source:

  * rho_dev -- device-state persistence: a sticky 2-state Markov error
    (p11=p+rho(1-p), p01=p(1-rho)) layered on the GE emission. Stationary mean = p
    (marginal preserved exactly); lag-1 autocorr = rho_dev. It models warm
    internal/connection state across *immediate* reps -- a real phenomenon GE's
    external RF channel cannot represent. Because no ordered-rerun dataset exists
    (FlakeFlagger is counts-only), rho_dev is an explicitly SWEPT unknown.

TWO de-correlation knobs, with different cost (this is design-relevant -- spacing
is cheap, power-cycling is not):

  * reset      -- a fresh, SPACED connection: resamples the RF state from
                  stationary. A continuous rate in [0,1]; marginal-neutral at ANY
                  value (every mixing step -- transition or resample -- preserves
                  the stationary law). Breaks only the RF (<=~0.18) component.
  * dev_settle -- the device is power-cycled between reps, breaking the rho_dev
                  sticky-error memory. A BOOLEAN policy (every rep, or never): the
                  two design-relevant regimes -- full device-decorrelation vs none
                  -- are exactly its {0,1} endpoints, both marginal-EXACT. A
                  *fractional* settle is DISALLOWED: it would clear the memory at a
                  state-correlated rate and inject a marginal bias that grows with
                  rho_dev and RF contrast. Immediate reruns reset neither knob and
                  are known ineffective [Luo+ FSE'14].

Both knobs preserve the marginal loss rate exactly (reset at any rate; dev_settle
at its boolean endpoints), so de-correlation buys back independent-sample
efficiency without making the average rep easier. All randomness flows through an
injected ``random.Random`` (seed-reproducible).

Note on calibration target: the detector only ever sees VALID reps, and INVALID
is state-correlated (more likely in BAD, which also has higher FN), so the
among-VALID false-negative is the quantity to calibrate. We set p_fn so the
among-valid conditional lands on the FlakeFlagger anchor
~0.44 (the real corpus modal-fail FN mean/median is 0.440/0.446); the
unconditional marginal is then ~0.46. Calibrating to the conditional -- what the
detector actually observes -- is the correct target.
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


# the canonical Outcome -> tool Rep map the device oracles return per rep (the full 3-key form;
# live.py keeps its own 2-key variant that routes REPRODUCED through the identity check by hand).
OUT2REP = {Outcome.REPRODUCED: Rep.YES, Outcome.NOT_REPRODUCED: Rep.NO, Outcome.INVALID: Rep.INVALID}


@dataclass(frozen=True)
class GEChannelParams:
    """Gilbert-Elliott RF x FlakeFlagger flakiness x device persistence x BLE invalids.

    Defaults: stationary P(BAD)=0.2, mean BAD burst 1/p_bg=5 reps; among-valid
    false-negative ~0.44 (FlakeFlagger anchor), false-positive ~0.03, invalid
    ~0.07; rho_dev=0 (set it to sweep observable burstiness); dev_settle is a
    BOOLEAN policy in {0,1} (fractional is rejected -- it biases the marginal).
    """

    # --- Gilbert-Elliott RF channel (2-state Markov) ---
    p_gb: float = 0.05   # P(GOOD -> BAD)
    p_bg: float = 0.20   # P(BAD  -> GOOD); mean burst length = 1/p_bg = 5
    # --- device flakiness per RF state (FlakeFlagger-calibrated, FN-dominant) ---
    p_fn_good: float = 0.366   # calibrated so the among-VALID FN ~ 0.44
    p_fn_bad: float = 0.836    #   (the FlakeFlagger anchor)
    p_fp_good: float = 0.02
    p_fp_bad: float = 0.07
    # --- wireless connection-establishment failure -> INVALID trial ---
    p_invalid_good: float = 0.02
    p_invalid_bad: float = 0.27
    # --- device-state persistence: sticky-error autocorrelation (swept unknown) ---
    rho_dev: float = 0.0
    # --- de-correlation knobs ---
    reset: float = 0.0       # RF resample rate in [0,1] (cheap spacing; marginal-neutral)
    dev_settle: float = 0.0  # BOOLEAN {0,1}: power-cycle every rep, or never (costly)

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
        # 1) connection-establishment failure: independent of bug truth AND of the
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
