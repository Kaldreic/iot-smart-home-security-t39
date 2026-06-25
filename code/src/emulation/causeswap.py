"""emulation.causeswap — a co-present multi-bug deployment binary as a HW-free oracle (Mode-2 cause-swap).

The device for RDD's identity-guard demonstration: a binary in which bugs A and C are CO-PRESENT in one PDU
window, driven under a CRASH-ONLY in-loop reproduction oracle (the in-loop sees only a crash/no-crash BIT,
as in exit-code fuzzing). ``_which_bug`` is the modelled deterministic binary (which co-present bug fires for
a subset); ``_binary_dump`` returns the FIRED bug's committed real dump (from ``emulation.multibug.MODEL``),
exactly what a real binary's stderr would yield. The guard's identity matcher is INJECTED by the benchmark
(the tool's L2/L3 cascade), so the pipeline runs verbatim. The real build-multibug binary keeps A and C in
SEPARATE per-bug harnesses on DISJOINT windows, so the co-presence is MODELLED + DISCLOSED; replace this
module with a real co-present binary and the RDD tool is unchanged (the benchmark re-wires its oracle)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from emulation.channel import GEChannelParams, L1Channel, OUT2REP
from emulation.multibug import MODEL

_WINDOW = 8                                       # the co-present window (A trigger-last bit 7; C IND-pair {3,4})
_TRIG = {"A": frozenset({7}), "C": frozenset({3, 4})}   # each bug's real 1/2-minimal within the window


@dataclass(frozen=True)
class _Bug:
    bug: str
    window: int = _WINDOW
    crash_sig: str = ""
    kind: str = "crash"


@dataclass
class _CoPresentOracle:
    """A co-present multi-bug binary under a CRASH-ONLY in-loop reproduction oracle: ``reachable`` names the bug
    that ACTUALLY fires in this window (its real crash). ``rep`` is YES on ANY observed crash with NO in-loop
    identity check (exit-code fuzzing); the channel-OFF ``truth`` (scoring) is TARGET-specific; the guard
    ``identity_truth`` is the ONLY identity check and uses the REAL dump of the bug that actually fired through
    the INJECTED ``identity`` cascade."""
    reachable: str                                # the bug that REALLY fires here ("A" or "C")
    identity: object                              # the guard's identity matcher, INJECTED (the tool's L2/L3)
    params: GEChannelParams = field(default_factory=GEChannelParams)
    calls: int = 0

    def _which_bug(self, subset):                 # the modelled deterministic binary: which co-present bug FIRES
        return self.reachable if _TRIG[self.reachable] <= frozenset(subset) else None

    def _binary_dump(self, subset):
        """The REAL crash dump the (modelled) binary EMITS for ``subset``: the bug that fires determines the
        artifact (build-multibug emits that bug's backtrace), so running it channel-OFF yields the fired bug's
        committed real dump, CLEANED -- exactly what emulation.live.LiveBinaryOracle.identity_truth compares
        (it ``parse_base_dump``'s the live stderr then ``clean_obs``'s it). None if ``subset`` does not crash.
        The guard READS this artifact; it does NOT know a-priori which bug fired -- the identity cascade infers that."""
        wb = self._which_bug(subset)
        return MODEL.clean_obs(wb) if wb is not None else None

    def truth(self, bug, subset) -> bool:         # channel-OFF scoring truth: does this subset crash the TARGET?
        return self._which_bug(subset) == bug.bug

    def identity_truth(self, bug, subset) -> bool:
        """Mode-2 guard (final-validation, run ONCE channel-OFF): READ the binary's REAL dump for ``subset``
        and let the injected identity cascade INFER whether it is the TARGET bug. The identity DECISION is the
        cascade's, NOT oracle knowledge -- here L2 settles A-vs-C (A has a ``ull_conn_update_parameters`` stack,
        C is a stackless ``LL_ASSERT`` exit) so L3 never escalates (the correct FrugalGPT behaviour); this demo
        exercises the guard's CAUSE-DISCRIMINATION, not L2/L3's robustness to dump VARIATION (that is the
        in-loop / l3_eval's domain, and the channel-OFF guard sees the CLEANED dump like the live guard).
        Demote-only: False if no crash, or a DIFFERENT bug's real dump fails the target identity."""
        obs = self._binary_dump(subset)
        return obs is not None and bool(self.identity(bug.bug, obs))

    def rep_session(self, bug, subset, rng, *, decorrelate: bool = False):
        crashes = self._which_bug(subset) is not None        # the in-loop sees ONLY this crash/no-crash BIT --
        params = replace(self.params, dev_settle=1.0, reset=1.0) if decorrelate else self.params  # NOT which bug
        ch = L1Channel(params, rng)

        def rep():
            self.calls += 1
            return OUT2REP[ch.step(crashes)]                # CRASH-ONLY raw_test: an observed crash -> YES, with
            #                                                  NO in-loop identity (that is the guard's job, once)
        return rep

    def ground_truth_minimals(self, bug):
        return [_TRIG[bug.bug]]                    # the TARGET's true minimal (size_gap is scored vs the target)


class _NoGuardOracle(_CoPresentOracle):
    """Guard OFF: no ``identity_truth`` attribute, so ``rdd.pipeline`` getattr-probes it as None and skips the
    Phase-4b gate (the pre-guard behaviour). Everything else is identical -> a clean A/B for the guard's effect."""
    identity_truth = None                          # getattr(...) is None -> pipeline skips the Phase-4b gate
