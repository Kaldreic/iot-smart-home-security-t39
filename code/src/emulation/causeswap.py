"""emulation.causeswap — a co-present multi-bug binary as a hardware-free oracle (Mode-2 cause-swap).

The device for RDD's identity-guard demonstration: a binary in which bugs A and C are co-present in one PDU
window, driven under a crash-only in-loop oracle (the in-loop sees only a crash/no-crash bit, as in
exit-code fuzzing). ``_which_bug`` is the modelled deterministic binary -- which co-present bug fires for a
subset; ``_binary_dump`` returns the fired bug's committed real dump (from ``emulation.multibug.MODEL``),
what a real binary's stderr would yield. The guard's identity matcher is injected by the benchmark (the
tool's L2/L3 cascade), so the pipeline runs verbatim.

The real build-multibug binary keeps A and C in separate per-bug harnesses on disjoint windows, so the
co-presence here is modelled. Replacing this module with a real co-present binary leaves the RDD tool
unchanged; the benchmark re-wires its oracle.
"""

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


@dataclass
class _CoPresentOracle:
    """Co-present multi-bug binary under a crash-only in-loop oracle. ``reachable`` names the bug that fires in
    this window; ``rep`` returns YES on any observed crash with no in-loop identity check (exit-code fuzzing);
    ``truth`` (channel-off scoring) is target-specific; only ``identity_truth`` checks identity, running the
    injected ``identity`` cascade on the real dump of the bug that fired."""
    reachable: str                                # the bug that fires here ("A" or "C")
    identity: object                              # the guard's identity matcher, injected (the tool's L2/L3)
    params: GEChannelParams = field(default_factory=GEChannelParams)
    calls: int = 0

    def _which_bug(self, subset):                 # the modelled deterministic binary: which co-present bug fires
        return self.reachable if _TRIG[self.reachable] <= frozenset(subset) else None

    def _binary_dump(self, subset):
        """The crash dump the modelled binary emits for ``subset``: the fired bug fixes the artifact (build-multibug
        emits that bug's backtrace), so running channel-off yields the fired bug's committed real dump, cleaned
        -- the same cleaned form ``emulation.live`` captures from the binary's stderr. None if ``subset`` does not crash. The
        guard reads this dump without knowing which bug fired; the identity cascade infers that."""
        wb = self._which_bug(subset)
        return MODEL.clean_obs(wb) if wb is not None else None

    def truth(self, bug, subset) -> bool:         # channel-off scoring truth: does this subset crash the target?
        return self._which_bug(subset) == bug.bug

    def identity_truth(self, bug, subset) -> bool:
        """Mode-2 guard: final validation, run once channel-off. Read the binary's real dump for ``subset`` and let
        the injected identity cascade decide whether it is the target bug; the decision is the cascade's, not
        oracle knowledge. Here L2 settles A against C (A has a ``ull_conn_update_parameters`` stack, C is a
        stackless ``LL_ASSERT`` exit) so L3 never escalates. The demo exercises cause discrimination, not
        L2/L3's robustness to dump variation (the in-loop / l3_eval's domain); the channel-off guard sees the
        cleaned dump (no report variation is applied to it). Demote-only: False on no crash, or when a different bug's real
        dump fails the target identity."""
        obs = self._binary_dump(subset)
        return obs is not None and bool(self.identity(bug.bug, obs))

    def rep_session(self, bug, subset, rng, *, decorrelate: bool = False):
        crashes = self._which_bug(subset) is not None        # the in-loop sees only this crash/no-crash bit --
        params = replace(self.params, dev_settle=1.0, reset=1.0) if decorrelate else self.params  # not which bug
        ch = L1Channel(params, rng)

        def rep():
            self.calls += 1
            return OUT2REP[ch.step(crashes)]                # crash-only raw_test: an observed crash -> YES, with
            #                                                  no in-loop identity (that is the guard's job, once)
        return rep

    def ground_truth_minimals(self, bug):
        return [_TRIG[bug.bug]]                    # the target's true minimal (size_gap is scored vs the target)


class _NoGuardOracle(_CoPresentOracle):
    """Guard off: ``identity_truth`` is None, so ``rdd.pipeline``'s getattr probe skips the Phase-4b gate (the
    pre-guard behaviour). Everything else is identical, giving a clean A/B for the guard's effect."""
    identity_truth = None                          # getattr(...) is None -> pipeline skips the Phase-4b gate
