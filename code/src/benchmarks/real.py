"""benchmarks.real — the real-target evaluation: RDD (the tool) vs the AirBugCatcher baseline.

The device (the oracle + its channel-off truth + captured reference dumps) lives in ``emulation.multibug``,
and the shared cached open-model L3 identity (the reproducibility freeze) in ``benchmarks.identity_cache``;
this module owns the real-target per-(bug, seed) campaign driver (``_run``) and re-exports both for the runner + the
cache-strictness test. The baseline loses a true reproduction TWICE -- to the channel (fixed-K accept-first FN)
AND to the exact-id (it cannot match a varied dump); RDD recovers both. The runner (``benchmarks.run``) drives
the arms (baseline vs tool, + the ddmin-only ablation)."""

from __future__ import annotations

import random

from benchmarks.identity_cache import (L2, L3CACHE, L3_BAND_LO, TARGET_TEXT,  # noqa: F401
                                       agg as _agg, id_l2l3, l3_provenance, l3_reset)
from emulation.multibug import BUGS, MODEL, MultibugOracle, _mbug, id_exact  # noqa: F401  (device re-exports)


def _run(arm, identity, bugs, seeds, **kw):
    """Run one campaign function (``scoring.run_baseline_campaign``/``run_tool_campaign``) over every
    (bug, seed); the campaign fn is a parameter so the runner picks baseline / tool / ddmin-only ablation."""
    rows = []
    for b in bugs:
        bug = _mbug(b)
        for s in seeds:
            o = MultibugOracle(identity=identity)
            r = dict(arm(o, [bug], random.Random(s), **kw)[0])
            r["reads"] = o.calls
            r["bug"] = b
            rows.append(r)
    return rows
