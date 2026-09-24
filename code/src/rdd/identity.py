"""Crash identity: is this crash dump the same bug as the target?

``L2Matcher`` wraps the ``rdd.l2`` comparator, which tolerates truncated or reordered backtraces and
changed addresses where the baseline's exact top-frame bucket does not. ``LiveL2L3Identity`` adds
the ``rdd.l3`` judge for the pairs L2 is unsure about, memoising each verdict. Requires drain3.
"""

from __future__ import annotations

import json
from pathlib import Path

from .observation import DumpObs
from .l3 import _pair_hash, judge_ollama, render_dump


class L2Matcher:
    """Fuzzy crash identity via ``L2Comparator``, fitted on the base observations of all target bugs."""

    def __init__(self, base_obs: dict[str, DumpObs], threshold: float = 0.5):
        from .l2 import L2Comparator
        self.l2 = L2Comparator(threshold=threshold)
        cobs = {b: o.to_crash_observation() for b, o in base_obs.items()}
        self.l2.fit(list(cobs.values()))
        self.sig = {b: self.l2.signature(c) for b, c in cobs.items()}

    def is_same(self, target_bug: str, obs: DumpObs):
        same, s = self.l2.same_crash(obs.to_crash_observation(), self.sig[target_bug])
        return bool(same), float(s)


class LiveL2L3Identity:
    """Identity callable for a live campaign: ``identity(target_bug, obs) -> bool``.

    L2 decides the confident cases; when it says "different" with similarity at least ``band`` the
    pair goes to the L3 judge (``judge_ollama`` by default) and the verdict is memoised by pair hash,
    so no pair is judged twice. A connection error from the judge propagates. A garbled or non-bool
    verdict, or a corrupt memo entry, counts as "different". ``stats`` counts L2-decided, live-L3 and
    memo-hit reads; ``memo`` can be loaded and saved with ``from_memo_file`` and ``save_memo``."""

    def __init__(self, base_obs: dict[str, DumpObs], *, band: float = 0.05, model: str = "llama3.1:8b",
                 host: str | None = None, memo: dict | None = None, judge=None, threshold: float = 0.5):
        self.l2 = L2Matcher(base_obs, threshold=threshold)
        self.target_text = {b: render_dump(o) for b, o in base_obs.items()}
        self.band = band
        self.model = model
        self.host = host
        self.memo: dict = memo if memo is not None else {}
        self._judge = judge or judge_ollama
        self.stats = {"l2_decided": 0, "l3_live": 0, "l3_memo": 0}

    def __call__(self, target_bug: str, obs: DumpObs) -> bool:
        same, score = self.l2.is_same(target_bug, obs)
        if same:
            self.stats["l2_decided"] += 1
            return True
        if score < self.band:                                       # confidently different
            self.stats["l2_decided"] += 1
            return False
        h = _pair_hash(self.target_text[target_bug], render_dump(obs))   # uncertain band: escalate to L3
        if h in self.memo:                                          # `in`, not get(): a stored None is a hit
            self.stats["l3_memo"] += 1
            v = self.memo[h]
        else:
            self.stats["l3_live"] += 1
            kw = {"model": self.model} if self.host is None else {"model": self.model, "host": self.host}
            v = self._judge(self.target_text[target_bug], render_dump(obs), **kw)
            self.memo[h] = v
        return isinstance(v, dict) and v.get("same") is True        # a corrupt memo entry reads as "different"

    def save_memo(self, path) -> None:
        """Write the verdict memo to ``path`` as JSON, creating parent directories as needed."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.memo, indent=1) + "\n", encoding="utf-8")

    @classmethod
    def from_memo_file(cls, base_obs: dict[str, DumpObs], path, **kw) -> "LiveL2L3Identity":
        """Construct with the memo loaded from ``path`` (empty if the file does not exist)."""
        p = Path(path)
        memo = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return cls(base_obs, memo=memo, **kw)
