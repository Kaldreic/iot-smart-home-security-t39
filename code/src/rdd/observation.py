"""rdd.observation — the crash-observation type the tool consumes.

``DumpObs`` is the tool's crash-report INPUT contract (log lines + backtrace + fault),
field-compatible with the L2 ``CrashObservation``. The emulation
suite's dump-variation model produces these; the tool's identity layer (L2/L3) consumes them."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DumpObs:
    """Field-compatible with the L2 CrashObservation (log_lines, stack, fault)."""
    log_lines: list
    stack: list
    fault: str

    def to_crash_observation(self):
        """Adapt to the L2 CrashObservation (lazy import to avoid pulling l2's drain3 dep unless needed)."""
        from .l2 import CrashObservation
        return CrashObservation(log_lines=self.log_lines, stack=self.stack, fault=self.fault)
