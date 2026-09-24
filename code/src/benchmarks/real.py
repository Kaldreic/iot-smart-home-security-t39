"""benchmarks.real — the real-target campaign driver shared by the runner and the cache tests.

The device (the truth-table oracle and the captured reference dumps) lives in ``emulation.multibug`` and the
cached open-model L3 identity in ``benchmarks.identity_cache``; both are re-exported here. ``_run`` drives
one campaign function over every (bug, seed); ``benchmarks.run`` chooses the arm.
"""

from __future__ import annotations

import random

from benchmarks.identity_cache import L2, L3CACHE, L3_BAND_LO, TARGET_TEXT, id_l2l3  # noqa: F401  (re-exports)
from emulation.multibug import BUGS, MODEL, MultibugOracle, _mbug, id_exact  # noqa: F401  (device re-exports)


def _run(arm, identity, bugs, seeds, *, params=None, **kw):
    """Run one campaign function (``scoring.run_baseline_campaign`` or ``run_tool_campaign``) over every
    (bug, seed), with a fresh oracle per campaign. ``params`` overrides the device's channel (the sensitivity
    table uses it)."""
    rows = []
    for b in bugs:
        bug = _mbug(b)
        for s in seeds:
            o = MultibugOracle(identity=identity) if params is None else MultibugOracle(identity=identity, params=params)
            r = dict(arm(o, [bug], random.Random(s), **kw)[0])
            r["reads"] = o.calls
            r["bug"] = b
            rows.append(r)
    return rows
