"""The crash-observation type the tool consumes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DumpObs:
    """A crash report: log lines, backtrace frames (top first) and the fault token. Field-compatible
    with ``rdd.l2.CrashObservation``."""
    log_lines: list
    stack: list
    fault: str

    def to_crash_observation(self):
        """Convert to the L2 ``CrashObservation``; the import is deferred so drain3 loads only when L2 is used."""
        from .l2 import CrashObservation
        return CrashObservation(log_lines=self.log_lines, stack=self.stack, fault=self.fault)
