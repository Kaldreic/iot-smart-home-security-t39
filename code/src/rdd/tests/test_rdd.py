"""rdd — lean invariant suite (compacted from the ~22 scattered phase ``_test_``/``_verify_`` scripts to
the load-bearing guarantees). Self-contained: no external data, no network, no real LLM.

  * minimiser SOUNDNESS — a credited recipe provably crashes (0 false-credit), on non-monotone bugs
  * minimiser RECOVERY  — recovers the suppressor-free minimal where classical ddmin bails
  * monotone PARITY     — on monotone bugs RDD matches ddmin (no regression)
  * oracle UNITS        — the SPRT controller (sustained-YES floor, CAPPED/UNHEALTHY, trust-gating) + the
                          monotone cache (closure soundness + the no-YES-⊆-NO frontier invariant), directly
  * pipeline END-TO-END — under a noisy SPRT oracle the tool recovers + the ablation bails + 0 false-credit

Run:  ``python -m rdd.tests.test_rdd``   (after `pip install -e code/`)
"""

from __future__ import annotations

import random
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # code/src -> `import rdd`

import rdd  # noqa: E402
from emulation.channel import GEChannelParams, L1Channel, Outcome  # noqa: E402
from rdd.minimizer import robust_minimize  # noqa: E402
from rdd.sprt import Rep  # noqa: E402

_OUTCOME_TO_REP = {Outcome.NOT_REPRODUCED: Rep.NO, Outcome.INVALID: Rep.INVALID}


def _nonmonotone_bug(rng, n=8):
    """A random non-monotone bug: minimal M crashes; suppressors X (disjoint, |X| in 1..2) un-crash it."""
    elems = list(range(n))
    M = set(rng.sample(elems, rng.randint(1, 3)))
    rest = [e for e in elems if e not in M]
    X = set(rng.sample(rest, rng.randint(1, 2)))
    return M, X, (lambda S: M <= set(S) and not (X & set(S)))


def test_minimiser_nonmonotone_sound_and_recovers():
    """200 random non-monotone bugs: every credited recipe crashes (0 false-credit); RDD recovers the
    minimal where the ddmin-only ablation (no seed-find) bails on the suppressed full window."""
    rng = random.Random(0)
    fc = recovered = bailed = 0
    for _ in range(200):
        M, X, test = _nonmonotone_bug(rng)
        r = robust_minimize(range(8), test)                                          # full robust
        if r.reproduced and not test(r.recipe):
            fc += 1                                                                   # SOUNDNESS breach
        if r.reproduced and M <= set(r.recipe):
            recovered += 1
        b = robust_minimize(range(8), test, max_remove=0, max_build=0, verify=False)  # ddmin-only ablation
        if not b.reproduced:
            bailed += 1
            assert b.strategy in ("exhausted", "none") and b.seed is None, \
                f"ablation must BAIL (seed None, exhausted/none), got strategy={b.strategy!r} seed={b.seed!r}"
    assert fc == 0, f"false-credit must be 0, got {fc}/200"
    assert recovered >= 195, f"RDD must recover the minimal, got {recovered}/200"
    assert bailed >= 195, f"ddmin-only ablation must bail on the suppressor, got {bailed}/200"
    return f"200 non-monotone bugs: 0 false-credit; RDD recovered {recovered}/200; ablation bailed {bailed}/200"


def test_monotone_parity():
    """Monotone bugs (no suppressor): RDD and the ddmin-only ablation both recover the same true minimal."""
    rng = random.Random(1)
    ok = 0
    for _ in range(100):
        M = set(rng.sample(range(8), rng.randint(1, 3)))
        test = lambda S, _M=M: _M <= set(S)
        r = robust_minimize(range(8), test)
        b = robust_minimize(range(8), test, max_remove=0, max_build=0, verify=False)
        if r.reproduced and b.reproduced and set(r.recipe) == set(b.recipe) == M:
            ok += 1
    assert ok == 100, f"monotone parity (RDD == ddmin-only == M) must hold, got {ok}/100"
    return f"100 monotone bugs: RDD == ddmin-only == true minimal (parity {ok}/100)"


class _NoisyLR:
    """The real LL_LENGTH_REQ suppressor pattern (crash <=> trigger bit3 present AND length_req bit4 absent)
    wrapped in the L1 channel + rdd.Rep -- the consistently-wired smoke for the whole pipeline."""

    def __init__(self):
        self.calls = 0
        self.p = GEChannelParams()

    @staticmethod
    def truth(subset):
        S = set(subset)
        return (3 in S) and (4 not in S)

    def rep_session(self, bug, subset, rng, *, decorrelate=False):
        p = replace(self.p, dev_settle=1.0, reset=1.0) if decorrelate else self.p
        ch = L1Channel(p, rng)
        crashes = self.truth(subset)

        def rep():
            self.calls += 1
            out = ch.step(crashes)
            return Rep.YES if out is Outcome.REPRODUCED else _OUTCOME_TO_REP[out]
        return rep


def test_pipeline_recovers_and_ablation_bails():
    """Under the noisy SPRT oracle on the real suppressor: the tool recovers (>=0.8) at 0 false-credit;
    the ddmin-only ablation bails to 0."""
    bug = type("B", (), {"window": 5})()

    def run(**kw):
        g = fc = 0
        for s in range(30):
            o = _NoisyLR()
            r = rdd.minimize(o, bug, random.Random(s), decorrelate=True, **kw)
            if r.reproduced:
                if o.truth(r.subset):
                    g += 1
                else:
                    fc += 1
        return g / 30, fc

    g, fc = run()
    ga, _ = run(ablate_robust=True)
    assert fc == 0, f"pipeline false-credit must be 0, got {fc}"
    assert g >= 0.8, f"tool must recover the suppressor (>=0.8), got {g:.3f}"
    assert ga == 0.0, f"ddmin-only ablation must bail (0.0), got {ga:.3f}"
    return f"noisy SPRT pipeline: tool genuine={g:.3f} (0 false-credit); ablation genuine={ga:.3f}"


def test_final_validation_gate_blocks_false_credit():
    """Gate guard (catches removal of the Phase-4 RAW final-validation): a CACHED ``test`` holding a
    trusted false-YES below the true minimal misleads the in-seed ddmin into a non-crashing cone; the raw
    final-validation must demote it, so no reproduced recipe is ever a non-crasher. Deleting the gate
    (``reproduced = bool(recipe)``) makes this test FAIL."""
    from rdd.cache import MonotoneOracleCache
    M = frozenset({2, 3})
    raw = lambda S: M <= set(S)                              # monotone truth
    cache = MonotoneOracleCache()
    cache.observe(frozenset({3}), True, trustworthy=True)    # a LIE: {3} alone does not crash
    def cached(s):
        a = cache.query(frozenset(s))
        return a if a is not None else raw(s)
    r = robust_minimize(range(6), cached, raw_test=raw)
    assert not r.reproduced, f"poisoned cache produced a FALSE reproduction: recipe={r.recipe} validated={r.validated}"
    assert r.recipe and not r.validated, "expected ddmin to take the cache lie and final-validation to demote it"
    assert not raw(r.recipe), "sanity: the demoted recipe really is a non-crasher"
    # the RAW gate is IDENTITY-STRICT (`is True`), symmetric with the Phase-4b identity_check: a raw_test that
    # returns a TRUTHY NON-BOOL (violating the Callable[..., bool] contract) is rejected even for a GENUINE
    # crasher -- weakening the gate to ``bool(raw(...))`` would wrongly credit it.
    raw_nonbool = lambda S: 1 if M <= set(S) else 0
    rb = robust_minimize(range(6), raw_nonbool, raw_test=raw_nonbool)
    assert not rb.reproduced and not rb.validated, \
        f"a truthy non-bool raw_test must fail the is-True gate (got reproduced={rb.reproduced})"
    return f"final-validation demoted the poisoned-cache recipe {sorted(r.recipe)}; truthy-non-bool raw fails is-True gate"


def test_identity_check_blocks_cause_swap():
    """Mode-2 cause-swap guard (catches removal of the Phase-4b identity_check): when the only reachable
    crash in the window is a DIFFERENT cause {4,5} than the TARGET {0,1}, raw_test ('does it crash?') credits
    the wrong-bug recipe; identity_check ('is it the TARGET crash?') must DEMOTE it. Deleting the Phase-4b
    gate makes this FAIL. A genuine target still credits (no false rejection); a non-bool check fails closed."""
    raw = lambda s: {4, 5} <= set(s)                          # the only reachable crash is a DIFFERENT cause
    r0 = robust_minimize(range(6), raw, raw_test=raw)         # no identity_check -> mis-credits the wrong bug
    assert r0.reproduced and set(r0.recipe) == {4, 5}, f"fixture: must converge to the wrong-bug crash, got {r0.recipe}"
    idok = lambda s: {0, 1} <= set(s)                         # the TARGET crash identity
    r1 = robust_minimize(range(6), raw, raw_test=raw, identity_check=idok)
    assert not r1.reproduced, "identity_check must DEMOTE the cause-swapped recipe (a wrong-bug credit)"
    assert set(r1.recipe) == {4, 5} and not r1.validated, "recipe kept for diagnosis, but validated=False"
    raw2 = lambda s: {0, 1} <= set(s)                         # the TARGET crash IS reachable
    r2 = robust_minimize(range(6), raw2, raw_test=raw2, identity_check=idok)
    assert r2.reproduced and set(r2.recipe) == {0, 1}, "identity_check must NOT reject the genuine target"
    r3 = robust_minimize(range(6), raw2, raw_test=raw2, identity_check=lambda s: 1 if idok(s) else 0)
    assert not r3.reproduced, "non-bool identity_check must fail closed (is True strict)"
    return f"identity_check: cause-swap recipe {sorted(r1.recipe)} DEMOTED; genuine target credited; non-bool fail-closed"


def test_pipeline_wires_identity_truth():
    """Wiring guard (catches removal of the identity_truth passthrough in pipeline.minimize): an oracle whose
    in-loop rep CRASHES on a DIFFERENT cause {4,5} but whose REAL identity_truth is the TARGET {0,1} must have
    its wrong-bug recipe DEMOTED end-to-end; an otherwise-identical oracle WITHOUT identity_truth mis-credits
    it (exactly the deployment gap the wiring closes)."""
    class _Base:
        def __init__(self):
            self.calls = 0
        def rep_session(self, bug, subset, rng, *, decorrelate=False):
            crashes = {4, 5} <= set(subset)                   # the in-loop crash IS a different cause
            def rep():
                self.calls += 1
                return Rep.YES if crashes else Rep.NO
            return rep

    class _Guarded(_Base):
        def identity_truth(self, bug, subset):                # the REAL target identity (NOT the reachable crash)
            return {0, 1} <= set(subset)

    bug = type("B", (), {"window": 6})()
    r_gap = rdd.minimize(_Base(), bug, random.Random(0), decorrelate=True)
    assert r_gap.reproduced and set(r_gap.subset) == {4, 5}, f"control: without identity_truth the wrong bug is credited, got {r_gap.subset}"
    r_guard = rdd.minimize(_Guarded(), bug, random.Random(0), decorrelate=True)
    assert not r_guard.reproduced, "pipeline must wire identity_truth -> demote the cause-swapped recipe"
    return f"pipeline identity_truth wiring: control mis-credits {sorted(r_gap.subset)}, guarded demotes it"


def test_submodule_imports_smoke():
    """Import + lightly call every rdd submodule, so the suite is not blind to import bugs (a dropped
    ``Path``, an unrewritten ``from l2_comparator``/``from dump_model``)."""
    import importlib
    for m in ["sprt", "cache", "ddmin", "minimizer", "observation", "l2",
              "identity", "l3", "pipeline", "oracle"]:
        importlib.import_module(f"rdd.{m}")
    from emulation.baseline import exact_crash_id
    from rdd.l3 import render_dump
    obs = type("O", (), {"stack": [], "fault": "ASSERT", "site": None,
                         "log_lines": ["ASSERTION FAIL @ foo.c:42"]})()
    cid = exact_crash_id(obs)                                # exercises _site_from_log -> Path (the NameError path)
    assert cid[0] == "site" and "foo.c:42" in str(cid), f"exact_crash_id site path broke: {cid}"
    assert "crash report" in render_dump(obs)
    from rdd.observation import DumpObs
    co = DumpObs(log_lines=["assert at f.c:9"], stack=["k_oops+0x1a"], fault="ASSERT").to_crash_observation()
    assert co.fault == "ASSERT", "DumpObs.to_crash_observation (the dump->l2 deferred import) broke"
    return f"12 submodules import; exact_crash_id site-path OK {cid[2]!r}; render_dump + dump->l2 OK"


def test_budget_floor_bail_reports_capped():
    """The budget-floor bail (max_seed_calls exhausted before a seed is found) reports strategy='none' +
    capped=True + seed None -- distinct from genuine 'exhausted'. Covers the capped/`none` path the
    strategy mapping depends on (a mutation collapsing it to always-'exhausted' slips past the others)."""
    M, X = {2, 5}, {0, 1}                                    # 2 suppressors: the seed needs a leave-2-out
    test = lambda S: M <= set(S) and not (X & set(S))
    r = robust_minimize(range(8), test, max_seed_calls=1)    # 1 probe: too few to reach the leave-2-out seed
    assert r.capped and r.strategy == "none" and r.seed is None and not r.reproduced, \
        f"budget-floor must be capped/none/seed-None/not-reproduced, got capped={r.capped} strategy={r.strategy!r} seed={r.seed!r}"
    return f"budget-floor: max_seed_calls=1 -> strategy={r.strategy!r} capped={r.capped} (bailed, not 'exhausted')"


def test_l3_judge_ollama():
    """The open-model L3 backend (mocked HTTP — no live model): parses BOTH verdict directions, sends a
    deterministic temp-0/seed-0 JSON-constrained request, reads a string-typed ``same`` fail-closed (an
    explicit allow-list, never raw ``bool()`` — so ``"false"`` is NOT True), and degrades to a conservative
    NO on a non-JSON reply (so a weak/garbled judge can only under-credit, never false-match)."""
    import json as _json
    import urllib.error
    import urllib.request

    import rdd.l3 as l3
    cap = {"content": ""}

    class _Resp:
        def read(self):
            return _json.dumps({"message": {"content": cap["content"]}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake(req, timeout=None):
        cap["body"] = _json.loads(req.data)
        return _Resp()

    orig = urllib.request.urlopen
    urllib.request.urlopen = _fake
    try:
        cap["content"] = '{"same": true, "confidence": 0.9}'
        v = l3.judge_ollama("report A", "report B", model="m")
        assert v == {"same": True, "conf": 0.9}, v
        assert cap["body"]["options"] == {"temperature": 0, "seed": 0}, cap["body"]["options"]
        assert cap["body"]["format"] == "json" and cap["body"]["stream"] is False, cap["body"]
        cap["content"] = '{"same": false, "confidence": 0.8}'       # a GENUINE different verdict must be honored
        assert l3.judge_ollama("a", "b", model="m") == {"same": False, "conf": 0.8}, "valid false ignored"
        for bad, want in [('{"same": "false"}', False), ('{"same": "no"}', False), ('{"same": "0"}', False),
                          ('{"same": "different bug"}', False), ('{"same": null}', False),
                          ('{"same": "not the same bug"}', False),    # affirmative token as SUBSTRING of a negative
                          ('{"same": "definitely not true"}', False), ('{"same": "no match"}', False),
                          ('{"same": "true"}', True), ('{"same": "yes"}', True)]:
            cap["content"] = bad                                    # string/null `same`: fail CLOSED, exact-membership
            assert l3.judge_ollama("a", "b", model="m")["same"] is want, (bad, "raw bool()/substring coercion leaked")
        cap["content"] = "they look different to me"               # not JSON
        v2 = l3.judge_ollama("report A", "report B", model="m")
        assert v2["same"] is False and v2["conf"] == 0.0 and "parse_error" in v2, v2
        urllib.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(urllib.error.URLError("down"))
        raised = False                                              # a connection error must propagate LOUD,
        try:                                                        # never degrade to a silent {same:False} cache
            l3.judge_ollama("a", "b", model="m")
        except urllib.error.URLError:
            raised = True
        assert raised, "connection error must propagate, not become a silent same:False"
    finally:
        urllib.request.urlopen = orig
    return "judge_ollama: both directions + string/substring fail-closed + temp0/seed0/json + conservative NO + loud connect-error"


def test_render_dump_and_pair_hash_stable():
    """The open-model verdict CACHE is keyed by ``_pair_hash(render_dump(...))`` — pin render_dump's exact
    text and _pair_hash's determinism/order-sensitivity so a silent format drift can't invalidate a shipped
    cache (every lookup would miss -> conservative NO -> silent under-credit)."""
    from rdd.l3 import _pair_hash, render_dump
    obs = type("O", (), {"log_lines": ["SIGFPE", "at ull_conn:1"], "stack": ["a+0x1", "b"]})()
    txt = render_dump(obs)
    assert txt == "--- crash report ---\nSIGFPE\nat ull_conn:1\nbacktrace (top first):\n  #0 a+0x1\n  #1 b", repr(txt)
    no_stack = type("O", (), {"log_lines": ["ASSERT @ f.c:9"], "stack": []})()
    assert render_dump(no_stack) == "--- crash report ---\nASSERT @ f.c:9", repr(render_dump(no_stack))
    h = _pair_hash("A", "B")
    assert h == _pair_hash("A", "B") and len(h) == 16 and h != _pair_hash("B", "A"), "pair_hash unstable/symmetric"
    return f"render_dump golden (with/without stack) + _pair_hash stable & order-sensitive ({h})"


class _FakeL2:
    """Controls the L2 (same, score) verdict so the live-L3 ESCALATION logic is tested deterministically,
    independent of L2Comparator's scoring (which has its own coverage)."""

    def __init__(self, verdict):
        self.verdict = verdict

    def is_same(self, target_bug, obs):
        return self.verdict


def test_live_l2l3_cascade_and_memo():
    """LiveL2L3Identity (the DEPLOYABLE off-the-shelf identity): L2 decides the confident cases with NO
    model call; only the uncertain band escalates to a LIVE judge, which is called ONCE per pair and
    memoised (an identical pair is then served from the memo, not re-queried)."""
    from rdd.observation import DumpObs
    from rdd.identity import LiveL2L3Identity
    base = {"A": DumpObs(log_lines=["SIGFPE at ull_conn:1"], stack=["ull_conn_update", "lll_conn"], fault="SIGFPE")}
    obs = DumpObs(log_lines=["SIGFPE truncated"], stack=["ull_conn_update"], fault="SIGFPE")
    calls = []

    def judge(t, r, **kw):
        calls.append((t, r))
        return {"same": True, "conf": 0.9}

    o = LiveL2L3Identity(base, band=0.05, judge=judge)
    o.l2 = _FakeL2((True, 0.9))
    assert o("A", obs) is True and o.stats["l3_live"] == 0, "L2-same must not call the model"
    o.l2 = _FakeL2((False, 0.01))
    assert o("A", obs) is False and o.stats["l3_live"] == 0, "confidently-different (score<band) must not call the model"
    o.l2 = _FakeL2((False, 0.30))
    assert o("A", obs) is True and o.stats["l3_live"] == 1, "uncertain band must escalate to a LIVE judgment"
    assert o("A", obs) is True and o.stats["l3_live"] == 1 and o.stats["l3_memo"] == 1, "identical pair must hit the memo"
    assert len(calls) == 1, f"the live judge must be invoked exactly once, got {len(calls)}"
    return f"live cascade: L2 gates (0 calls), band escalates live (1 call) then memoises (stats={o.stats})"


def test_live_l2l3_failsafe():
    """LiveL2L3Identity mirrors the backend's soundness: a garbled / non-bool verdict yields a conservative
    NO (never a false match — strict ``is True``), and a connection error to the model PROPAGATES (loud)
    rather than silently degrading the campaign."""
    from rdd.observation import DumpObs
    from rdd.identity import LiveL2L3Identity
    base = {"A": DumpObs(log_lines=["SIGFPE @ x:1"], stack=["f", "g"], fault="SIGFPE")}
    obs = DumpObs(log_lines=["garble"], stack=["f"], fault="SIGFPE")
    for verdict, want in [({"same": False, "conf": 0.0, "parse_error": "x"}, False),   # garbled -> conservative
                          ({"same": "true", "conf": 1.0}, False),                       # non-bool -> not `is True`
                          ({"same": True, "conf": 0.9}, True)]:                         # genuine bool -> credit
        o = LiveL2L3Identity(base, band=0.05, judge=lambda t, r, _v=verdict, **kw: _v)
        o.l2 = _FakeL2((False, 0.30))
        assert o("A", obs) is want, (verdict, want)

    def boom(t, r, **kw):
        raise ConnectionError("ollama down")

    ob = LiveL2L3Identity(base, band=0.05, judge=boom)
    ob.l2 = _FakeL2((False, 0.30))
    raised = False
    try:
        ob("A", obs)
    except ConnectionError:
        raised = True
    assert raised, "a connection error must propagate (loud), not silently degrade the campaign"

    from rdd.l3 import _pair_hash, render_dump                       # a corrupt / foreign memo entry (missing
    for bad in [{"conf": 1.0}, True, None, "yes", [1]]:             # "same", or non-dict) -> conservative NO,
        oc = LiveL2L3Identity(base, band=0.05, judge=boom)          # not a KeyError/TypeError crash
        oc.l2 = _FakeL2((False, 0.30))
        oc.memo[_pair_hash(oc.target_text["A"], render_dump(obs))] = bad
        assert oc("A", obs) is False, (bad, "corrupt memo must degrade to False, not crash or credit")
    return "live failsafe: garbled/non-bool/corrupt-memo -> conservative NO; connection error propagates"


def test_live_l2l3_memo_persist():
    """A persisted memo round-trips: a verdict saved by one campaign serves the next WITHOUT a live call —
    exactly the benchmark's pre-warmed-cache EQUIVALENCE (a pre-filled memo short-circuits the model, so the
    live path with a warm memo == the cache path)."""
    import shutil
    import tempfile
    from pathlib import Path as _P
    from rdd.observation import DumpObs
    from rdd.identity import LiveL2L3Identity
    base = {"A": DumpObs(log_lines=["SIGFPE @ x:1"], stack=["f", "g"], fault="SIGFPE")}
    obs = DumpObs(log_lines=["garble"], stack=["f"], fault="SIGFPE")
    o = LiveL2L3Identity(base, band=0.05, judge=lambda t, r, **kw: {"same": True, "conf": 0.9})
    o.l2 = _FakeL2((False, 0.30))
    assert o("A", obs) is True and o.stats["l3_live"] == 1
    d = _P(tempfile.mkdtemp(prefix="rddmemo-"))
    try:
        memo_path = d / "nested" / "sub" / "memo.json"             # parent dirs don't exist -> save_memo mkdirs
        o.save_memo(memo_path)

        def boom(t, r, **kw):
            raise AssertionError("live judge called despite a pre-loaded memo")

        o2 = LiveL2L3Identity.from_memo_file(base, memo_path, band=0.05, judge=boom)
        o2.l2 = _FakeL2((False, 0.30))
        assert o2("A", obs) is True and o2.stats["l3_live"] == 0 and o2.stats["l3_memo"] == 1, o2.stats
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return "live memo persist: a saved verdict serves from a pre-loaded memo with 0 live calls (cache-equivalence)"


def test_parse_base_dump_live_format():
    """parse_base_dump must handle BOTH the captured ``)[0x..]`` AND the LIVE glibc ``) [0x..]`` (a SPACE
    before ``[``) backtrace formats — pins the _FRAME_RE ``\\s*``. Reverting it parses the real binary's live
    dump to ZERO frames, silently killing the L2 target + all L3 escalation (the suites otherwise stay green)."""
    from emulation.dump import parse_base_dump
    live = ("=== CRASH sig=SIGFPE ===\n"
            "./testbinary(+0x1284c) [0x5663084c]\n"                          # leading handler frame (sym-less)
            "linux-gate.so.1(__kernel_sigreturn+0x0) [0xf7f77250]\n"          # scaffold (dropped)
            "./testbinary(ull_conn_update_parameters+0xdc) [0x56639338]\n"    # LIVE: SPACE before [
            "./testbinary(llcp_rp_cu_run+0x20) [0x5663bfeb]\n")
    captured = ("=== CRASH sig=SIGFPE ===\n"
                "/work/build-multibug/testbinary(ull_conn_update_parameters+0xdc)[0x56663338]\n"   # captured: NO space
                "/work/build-multibug/testbinary(llcp_rp_cu_run+0x20)[0x56665feb]\n")
    for txt, label in [(live, "live `) [0x..]`"), (captured, "captured `)[0x..]`")]:
        bd = parse_base_dump(txt, "A")
        assert bd.fault == "SIGFPE" and bd.frames and bd.frames[0].sym == "ull_conn_update_parameters", \
            (label, bd.fault, [f.sym for f in bd.frames])
    return "parse_base_dump: live `) [0x..]` AND captured `)[0x..]` both parse (top=ull_conn_update_parameters)"


def test_sprt_config_validation():
    """SPRTConfig.__post_init__ rejects the degenerate parameterisations that would silently break the error
    control -- a non-informative oracle (p0 >= p1, or p0/p1 outside (0,1)), degenerate decision boundaries
    (alpha + beta >= 1), an unreachable YES (min_yes_reps < 1 or > n_max) -- so a typo'd config fails LOUD at
    construction, never as a silent mis-decision in the loop. A valid config (default + a non-default) is accepted."""
    from rdd.sprt import SPRTConfig
    bad = [dict(p0=0.5, p1=0.5),            # p0 < p1 violated (oracle not informative)
           dict(p0=0.6, p1=0.5),            # p0 < p1 violated
           dict(p0=0.0),                    # 0 < p0 violated
           dict(p1=1.0),                    # p1 < 1 violated
           dict(alpha=0.6, beta=0.5),       # alpha + beta >= 1 (boundaries degenerate)
           dict(min_yes_reps=0),            # min_yes_reps < 1 (YES unreachable)
           dict(min_yes_reps=20, n_max=16)] # min_yes_reps > n_max (YES unreachable)
    for kw in bad:
        try:
            SPRTConfig(**kw)
        except ValueError:
            continue
        raise AssertionError(f"SPRTConfig({kw}) must raise ValueError")
    SPRTConfig()                                                  # the default must be valid
    SPRTConfig(p0=0.1, p1=0.9, alpha=0.05, beta=0.2, min_yes_reps=1, n_max=4)   # a valid non-default
    return f"SPRTConfig validation: {len(bad)} degenerate configs rejected LOUD; valid configs accepted"


def test_sprt_run_and_trust_gating():
    """The truncated-SPRT controller's guarantees, DIRECTLY (covered only via the pipeline before): a
    DECIDED-YES needs SUSTAINED evidence (>= min_yes_reps valid reps -- a lucky early burst that crosses A
    must not lock in the SEVERE error); a fast NO is cheap (no floor on the safe side); truncation forces the
    SAFE NO at LOW trust (CAPPED); too many INVALID exchanges abstain (UNHEALTHY); INVALID reps are skipped as
    missing DATA, not evidence; and apply_to_cache trust-gates (a DECIDED verdict is cached, a CAPPED one is a no-op)."""
    from dataclasses import replace
    from rdd.cache import MonotoneOracleCache
    from rdd.sprt import Rep, SPRTConfig, Status, TruncatedSPRT, apply_to_cache
    cfg = SPRTConfig()
    yes, no, inv = (lambda: Rep.YES), (lambda: Rep.NO), (lambda: Rep.INVALID)

    # DECIDED-YES is gated by the min_yes_reps FLOOR: all-YES decides at reps == min_yes_reps (3), NOT at the
    # rep where the LLR first crosses A (rep 2) -- the floor blocks the lucky 2-rep burst from the severe error.
    v = TruncatedSPRT(cfg).run(yes)
    assert v.decision is True and v.trust is True and v.status is Status.DECIDED and v.reps == cfg.min_yes_reps, v
    v2 = TruncatedSPRT(replace(cfg, min_yes_reps=2)).run(yes)     # relax the floor -> decides one rep earlier
    assert v2.reps == 2, f"min_yes_reps floor not load-bearing (deleting the `valid >= min_yes_reps` guard): {v2}"

    # a fast NO is DECIDED + trusted (the deliberately looser, cheap-and-recoverable side)
    vn = TruncatedSPRT(cfg).run(no)
    assert vn.decision is False and vn.trust is True and vn.status is Status.DECIDED, vn

    # truncation -> forced SAFE NO at LOW trust (CAPPED). Tiny per-rep steps (p0 ~ p1) cannot cross A/B within n_max.
    vc = TruncatedSPRT(replace(cfg, p0=0.49, p1=0.51)).run(yes)
    assert vc.decision is False and vc.trust is False and vc.status is Status.CAPPED and vc.reps == cfg.n_max, vc

    # too many INVALID exchanges -> UNHEALTHY abstain (distinct from "did not reproduce"), low trust, 0 valid reps
    vu = TruncatedSPRT(cfg).run(inv)
    assert vu.status is Status.UNHEALTHY and vu.decision is False and vu.trust is False, vu
    assert vu.invalid == cfg.invalid_cap and vu.reps == 0, vu

    # INVALID reps are missing DATA (skipped), not evidence: 2 invalids then 3 YES still DECIDES YES at reps 3
    mixed = iter([Rep.INVALID, Rep.INVALID, Rep.YES, Rep.YES, Rep.YES])
    vm = TruncatedSPRT(cfg).run(lambda: next(mixed))
    assert vm.decision is True and vm.reps == 3 and vm.invalid == 2, vm

    # apply_to_cache trust-gates: a DECIDED verdict is recorded; a CAPPED verdict is a no-op (-> re-escalates)
    cache = MonotoneOracleCache()
    apply_to_cache(cache, frozenset({1, 2}), v)                  # DECIDED-YES -> recorded
    assert cache.query(frozenset({1, 2})) is True, "a DECIDED verdict must be cached"
    apply_to_cache(cache, frozenset({7}), vc)                    # CAPPED -> no-op (low trust)
    assert cache.query(frozenset({7})) is None, "a CAPPED verdict must NOT be cached (low trust -> re-escalate)"
    return (f"SPRT controller: YES floor reps={v.reps} (vs {v2.reps} relaxed); fast NO; CAPPED safe-NO low-trust; "
            f"UNHEALTHY@{vu.invalid} invalids; invalids skipped; apply_to_cache trust-gated")


def test_sprt_alpha_bounds_false_yes():
    """The truncated SPRT's load-bearing SEVERE-error guarantee, DIRECTLY: on the null boundary (per-valid-rep
    P(YES) == p0) the realised false-YES -- a wrongly DECIDED reproduce (trust=True -> cached -> propagated
    upward forever) -- stays <= alpha. Covered only end-to-end before (pipeline fc==0, where the Phase-4
    final-validation can MASK an SPRT regression); this isolates the controller. Loosening the YES boundary A
    lifts the realised rate above alpha -> FAIL."""
    from rdd.sprt import Rep, SPRTConfig, TruncatedSPRT
    cfg = SPRTConfig()
    rng = random.Random(0)
    n = 4000
    false_yes = sum(TruncatedSPRT(cfg).run(lambda: Rep.YES if rng.random() < cfg.p0 else Rep.NO).decision
                    for _ in range(n))
    rate = false_yes / n
    assert rate <= cfg.alpha, f"realised false-YES {rate:.4f} (={false_yes}/{n}) must stay <= alpha={cfg.alpha}"
    return f"SPRT alpha-bound: false-YES {rate:.4f} <= alpha {cfg.alpha} over {n} null-boundary (p0={cfg.p0}) trials"


def test_cache_monotone_soundness():
    """MonotoneOracleCache answers ONLY what the monotone closure forces, soundly (covered only indirectly
    before): superset-of-YES => True, subset-of-NO => False, else None; the frontiers keep the invariant "no
    YES is a subset of any NO" -- a NO ABOVE a confirmed YES is REJECTED (never prunes the reproducer's cone),
    a YES BELOW a confirmed NO SELF-HEALS by evicting that NO; the YES frontier stays a MINIMAL antichain; an
    untrustworthy read is NOT recorded; and a same-point re-measurement flip is not a cross-point violation."""
    from rdd.cache import MonotoneOracleCache

    # closure: superset-of-YES -> True, subset-of-NO -> False, unforced -> None
    c = MonotoneOracleCache()
    c.observe(frozenset({1, 2}), True)
    c.observe(frozenset({5, 6}), False)
    assert c.query(frozenset({1, 2, 3})) is True, "a superset of a confirmed YES must be True"
    assert c.query(frozenset({5})) is False, "a subset of a confirmed NO must be False"
    assert c.query(frozenset({8, 9})) is None, "an unforced point must be None (defer -> escalate)"

    # antichain invariant: a NO ABOVE a confirmed YES is a real monotonicity violation -> REJECTED (the
    # downward NO direction would wrongly prune the YES cone), so the cache never answers NO over a reproducer.
    # Pin the rejection on the FRONTIER directly (_no == []): query({1,2}) is True via YES-dominance whether or
    # not the stale NO was wrongly stored, so the query alone is vacuous -- the frontier check is what bites.
    c2 = MonotoneOracleCache()
    c2.observe(frozenset({1}), True)
    c2.observe(frozenset({1, 2}), False)                         # {1} subset of {1,2}: the NO is rejected
    assert c2._no == [], f"a NO above a confirmed YES must be REJECTED from the frontier, got {c2._no}"
    assert c2.query(frozenset({1, 2})) is True, "and the cache must never answer NO over the confirmed reproducer"

    # self-heal: a YES BELOW a confirmed NO evicts that stale NO (else the cache answers NO over a reproducer)
    c3 = MonotoneOracleCache()
    c3.observe(frozenset({1, 2, 3}), False)
    c3.observe(frozenset({1, 2}), True)                          # a subset reproduces -> evict the stale NO
    assert c3.query(frozenset({1, 2, 3})) is True, "a YES below a NO must self-heal (evict the NO)"
    assert c3._no == [], f"the contradicted NO must be evicted, got {c3._no}"

    # the YES frontier stays a MINIMAL antichain: a larger YES dominated by a smaller one is not added (GUARD)
    c4 = MonotoneOracleCache()
    c4.observe(frozenset({1}), True)
    c4.observe(frozenset({1, 2}), True)                          # dominated by {1} -> not a separate frontier elem
    assert c4._yes == [frozenset({1})], f"YES frontier must stay a minimal antichain, got {c4._yes}"

    # the frontiers also EVICT on the opposite order: a smaller YES arriving later must drop the larger one it
    # now dominates (and symmetrically a larger NO drops the smaller NOs) -- the antichains stay minimal/maximal.
    c4b = MonotoneOracleCache()
    c4b.observe(frozenset({1, 2}), True)                         # larger YES first
    c4b.observe(frozenset({1}), True)                            # a smaller reproducer -> EVICTS the larger {1,2}
    assert c4b._yes == [frozenset({1})], f"a smaller YES must EVICT the dominated larger one, got {c4b._yes}"
    c4c = MonotoneOracleCache()
    c4c.observe(frozenset({1}), False)                          # smaller NO first
    c4c.observe(frozenset({1, 2}), False)                       # a larger non-reproducer -> EVICTS the smaller {1}
    assert c4c._no == [frozenset({1, 2})], f"a larger NO must EVICT the dominated smaller one, got {c4c._no}"

    # trust-gating: an untrustworthy read is a NO-OP (used for the current step by the caller, never cached)
    c5 = MonotoneOracleCache()
    c5.observe(frozenset({4}), True, trustworthy=False)
    assert c5.query(frozenset({4})) is None, "an untrustworthy observation must NOT be recorded (re-escalates)"

    # a same-point re-measurement FLIP is not a cross-point violation: the new value wins
    c6 = MonotoneOracleCache()
    c6.observe(frozenset({2}), True)
    c6.observe(frozenset({2}), False)                            # same point, flipped
    assert c6.query(frozenset({2})) is False, "a same-point re-measurement flip must take the new value"
    return ("cache soundness: closure (sup-YES/sub-NO/None) + antichain invariant (NO-above-YES rejected, "
            "YES-below-NO self-heals) + minimal/maximal frontier eviction + trust-gating no-op + same-point flip")


TESTS = [test_minimiser_nonmonotone_sound_and_recovers, test_monotone_parity,
         test_pipeline_recovers_and_ablation_bails, test_final_validation_gate_blocks_false_credit,
         test_identity_check_blocks_cause_swap, test_pipeline_wires_identity_truth,
         test_budget_floor_bail_reports_capped, test_sprt_config_validation, test_sprt_run_and_trust_gating,
         test_sprt_alpha_bounds_false_yes, test_cache_monotone_soundness, test_submodule_imports_smoke, test_l3_judge_ollama,
         test_render_dump_and_pair_hash_stable, test_parse_base_dump_live_format,
         test_live_l2l3_cascade_and_memo, test_live_l2l3_failsafe, test_live_l2l3_memo_persist]


def main():
    print("=== rdd lean invariant suite ===\n")
    failed = 0
    for fn in TESTS:
        try:
            print(f"  PASS  {fn.__name__}: {fn()}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'ALL PASS' if not failed else f'{failed} FAILED'} ({len(TESTS) - failed}/{len(TESTS)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
