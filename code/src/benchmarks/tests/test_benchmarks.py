"""benchmarks — lean self-test: the suite runs and the PRESERVED arms reproduce the committed numbers.

Run:  ``PYTHONHASHSEED=0 python -m benchmarks.tests.test_benchmarks``   (after `pip install -e code/`)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # code/src -> import rdd + benchmarks

from benchmarks import run  # noqa: E402
from emulation import multibug  # noqa: E402


def test_suite_smoke():
    """The suite runs end-to-end; on the real suppressor the tool RECOVERS and the ablation BAILS."""
    r = run.run_real(5)
    s = run.run_suppressor(5, ablate=True)
    assert run._metric(r["baseline"]) > 0 and run._metric(r["tool"]) > 0, "real suite produced no reproductions"
    assert run._metric(s["tool"]) >= 0.8, f"tool must recover the suppressor, got {run._metric(s['tool']):.2f}"
    assert run._metric(s["ablation"]) == 0.0, f"ablation must bail on the suppressor, got {run._metric(s['ablation']):.2f}"
    return (f"smoke: real tool {run._metric(r['tool']):.2f}; suppressor tool {run._metric(s['tool']):.2f} / "
            f"ablation {run._metric(s['ablation']):.2f} (bails)")


def test_real_suppressor_coherence():
    """The fresh real+suppressor suite reproduces the committed PRESERVED-arm numbers within the gate's
    +/-0.02 tolerance (delta 0.000 in practice) (baseline==arm_a, tool==arm_b_plus, suppressor ablation bails==arm_b) vs realbench_robust.json. The
    synthetic resilience sweep (B2) has its OWN exact, model-free gate, pinned by test_b2_resilience_smoke
    here and reproduced in full by `python -m benchmarks.resilience --coherence`."""
    assert run.coherence(), "fresh real+suppressor suite must reproduce committed baseline (arm_a) + tool (arm_b_plus)"
    return "real+suppressor coherence within +/-0.02 (delta 0.000: baseline==arm_a, tool==arm_b_plus, ablation bails)"


def test_l3_judge_eval_anchored():
    """The committed judge-quality eval (data/reference/l3_judge_eval.json) re-derives its recall/rejection
    from the STORED verdicts WITHOUT the model — so Llama's residual-recall (1.00) and cross-rejection are
    a reproducible, gated artifact, not an observed-once-live number."""
    import json as _json

    from benchmarks.eval import l3_eval
    p = l3_eval._DATA / "reference" / "l3_judge_eval.json"
    assert p.exists(), "missing committed judge-eval reference (run `l3_eval eval --model ...` to generate)"
    d = _json.loads(p.read_text(encoding="utf-8"))
    fresh = l3_eval.score(d["cases"], d["verdicts"])           # re-score offline from committed verdicts
    assert abs(fresh["l3_residual_recovery"] - d["score"]["l3_residual_recovery"]) < 1e-12, (fresh, d["score"])
    assert abs(fresh["l3_cross_rejection"] - d["score"]["l3_cross_rejection"]) < 1e-12, (fresh, d["score"])
    assert fresh["l3_residual_recovery"] == 1.0, f"committed Llama recall must be 1.0, got {fresh}"
    return (f"l3_judge_eval anchored ({d['model']}): recall {fresh['l3_residual_recovery']:.3f} / "
            f"rejection {fresh['l3_cross_rejection']:.3f} (re-scored model-free)")


def test_l3_collect_and_judge():
    """collect_cases pulls the real+suppressor L2-residual pairs (deterministic, model-free); base_cache
    pairs are never re-collected (the fixed-point precondition); judge_cases routes through the open-model
    backend (mocked) and PROPAGATES a parse_error."""
    from benchmarks.eval import l3_eval
    cases = l3_eval.collect_cases(seeds=3)
    assert cases and all("hash" in c and "target_text" in c and "rep_text" in c for c in cases), "no valid cases"
    again = l3_eval.collect_cases(seeds=3)
    assert {c["hash"] for c in cases} == {c["hash"] for c in again}, "collect_cases not deterministic"
    bc = {c["hash"]: {"same": True, "conf": 1.0} for c in cases}   # already-judged pairs HIT, never re-collected
    nxt = l3_eval.collect_cases(seeds=3, base_cache=bc)
    assert all(c["hash"] not in bc for c in nxt), "base_cache pairs were re-collected (breaks the fixed point)"
    orig = l3_eval.judge_ollama
    try:
        l3_eval.judge_ollama = lambda t, r, **kw: {"same": True, "conf": 0.8}
        v = l3_eval.judge_cases(cases[:5], model="m")
        assert v and all(rec["same"] is True and rec["model"] == "m" for rec in v.values()), v
        l3_eval.judge_ollama = lambda t, r, **kw: {"same": False, "conf": 0.0, "parse_error": "garbled"}
        vp = l3_eval.judge_cases(cases[:2], model="m")            # a parse_error must survive into the cache record
        assert all(rec["same"] is False and rec.get("parse_error") == "garbled" for rec in vp.values()), vp
    finally:
        l3_eval.judge_ollama = orig
    return f"collect_cases: {len(cases)} pairs (deterministic, base_cache-aware); judge_cases routes + propagates errors"


def test_l3_score():
    """score() arithmetic: recovery = same-residual judged 'same', rejection = cross judged 'different'.
    Asymmetric fixture so a `== want` -> `!= want` inversion (which flips BOTH rates) is caught."""
    from benchmarks.eval import l3_eval
    cases = [{"kind": "same_residual", "hash": "h1", "truth_same": True},
             {"kind": "same_residual", "hash": "h2", "truth_same": True},     # both residual recovered -> 1.0
             {"kind": "cross", "hash": "h3", "truth_same": False},
             {"kind": "cross", "hash": "h4", "truth_same": False},
             {"kind": "cross", "hash": "h5", "truth_same": False}]            # 2/3 cross rejected -> 0.667
    verdicts = {"h1": {"same": True}, "h2": {"same": True},
                "h3": {"same": False}, "h4": {"same": False}, "h5": {"same": True}}
    s = l3_eval.score(cases, verdicts)
    assert s["l3_residual_recovery"] == 1.0, s                    # `==`->`!=` would make this 0.0
    assert abs(s["l3_cross_rejection"] - 2 / 3) < 1e-9, s         # `==`->`!=` would make this 1/3
    assert s["n_residual"] == 2 and s["n_cross"] == 3 and s["n_judged"] == 5, s
    return f"score: recovery {s['l3_residual_recovery']:.3f} / rejection {s['l3_cross_rejection']:.3f} (arithmetic pinned)"


def test_real_credit_path_strict():
    """id_l2l3's L3 cache read is STRICT (`v["same"] is True`): a non-bool cache value (a model that emitted
    a STRING "true") must NOT credit — pins the fix against a bool() revert — while a genuine bool True still
    credits and extra keys (conf/model) are ignored."""
    import random as _r

    import benchmarks.real as real
    from rdd.l3 import _pair_hash, render_dump
    rng = _r.Random(0)
    b = real.BUGS[0]
    obs = None
    for _ in range(20000):                                          # synthesize an L3-band residual (L2 abstains)
        o = real.MODEL.emit(b, rng)
        same, sc = real.L2.is_same(b, o)
        if not same and sc >= real.L3_BAND_LO:
            obs = o
            break
    assert obs is not None, "could not synthesize an L3-band residual obs for the credit-path test"
    h = _pair_hash(real.TARGET_TEXT[b], render_dump(obs))
    saved = dict(real.L3CACHE)
    try:
        real.L3CACHE.clear()
        real.L3CACHE[h] = {"same": "true", "conf": 1.0, "model": "x"}   # STRING poison: a bool() read would credit
        assert real.id_l2l3(b, obs) is False, "string non-bool cache value credited — strict `is True` not enforced"
        real.L3CACHE[h] = {"same": 1, "conf": 1.0}                      # NUMERIC poison: only `== True` (not `is True`) credits
        assert real.id_l2l3(b, obs) is False, "numeric 1 credited — `is True` weakened to `== True`?"
        real.L3CACHE[h] = {"same": True}                                # genuine bool, extra keys absent
        assert real.id_l2l3(b, obs) is True, "a real bool True failed to credit"
    finally:
        real.L3CACHE.clear()
        real.L3CACHE.update(saved)
    return "real.id_l2l3: string 'true' -> NO credit (strict is True); bool True -> credit (extra keys ignored)"


def test_l3_judge_fixed_point():
    """_judge_to_fixed_point ITERATES until no new L2-residual pair (the pre-fix single pass left fresh pairs
    unjudged -> conservative NO -> under-credit). Model-free (canned same=True, worst case for control-flow
    change): it converges to a TRUE fixed point, AND a forced single pass (max_iters=1) is NOT yet a fixed
    point — so the loop is provably load-bearing (a break-after-one regression would leave pairs unjudged)."""
    from benchmarks.eval import l3_eval
    orig = l3_eval.judge_cases
    l3_eval.judge_cases = lambda cases, *, model, host=None: {
        c["hash"]: {"same": True, "conf": 1.0, "model": model} for c in cases}
    try:
        acc, cbh, converged = l3_eval._judge_to_fixed_point("FAKE", None, seeds=3)
        assert converged, "loop did not converge"
        assert l3_eval.collect_cases(seeds=3, base_cache=acc) == [], "result is not a true fixed point"
        assert set(cbh) == set(acc), "cases_by_hash and verdicts disagree"
        acc1, _, conv1 = l3_eval._judge_to_fixed_point("FAKE", None, seeds=3, max_iters=1)
        assert not conv1 and l3_eval.collect_cases(seeds=3, base_cache=acc1) != [], \
            "a single pass is already a fixed point at seeds=3 — test cannot catch the single-pass regression"
    finally:
        l3_eval.judge_cases = orig
    return f"_judge_to_fixed_point: converged ({len(acc)} pairs); single pass leaves residual (loop load-bearing)"


def test_l3_judge_seed_cache_incremental():
    """_judge_to_fixed_point(seed_cache=...) GROWS the cache: seeded verdicts are preserved BYTE-EXACT (never
    re-judged -> no GPU-nondeterminism flip on the LOCKED A-D verdicts), and ONLY new pairs are judged. Pins
    the incremental re-baseline that added bugs E,F to the cached anchor without disturbing A-D."""
    from benchmarks.eval import l3_eval
    orig = l3_eval.judge_cases
    try:
        l3_eval.judge_cases = lambda cases, *, model, host=None: {
            c["hash"]: {"same": True, "conf": 1.0, "model": model} for c in cases}
        full, _, _ = l3_eval._judge_to_fixed_point("BASE", None, seeds=3)        # learn the full pair set
        assert len(full) >= 2, "fixture: need >=2 residual pairs to split"
        # seed HALF with a DISTINGUISHABLE verdict; judge the rest with a NEW model id
        seed = {h: {"same": True, "conf": 0.42, "model": "SEEDED"} for h in list(full)[:len(full) // 2]}
        l3_eval.judge_cases = lambda cases, *, model, host=None: {
            c["hash"]: {"same": True, "conf": 1.0, "model": "NEW"} for c in cases}
        acc, cbh, conv = l3_eval._judge_to_fixed_point("NEW", None, seeds=3, seed_cache=seed)
        assert conv, "incremental did not converge"
        assert all(acc[h] == seed[h] for h in seed), "seeded verdicts were RE-JUDGED (not preserved byte-exact)"
        assert all(h not in cbh for h in seed), "a seeded pair was re-collected/re-judged (seed not load-bearing)"
        assert cbh and all(acc[h]["model"] == "NEW" for h in cbh), "new pairs were not judged with the NEW model"
        assert set(seed) <= set(full), "non-vacuity: seeded pairs must be ones the empty-seed run WOULD judge"
    finally:
        l3_eval.judge_cases = orig
    return f"_judge_to_fixed_point(seed_cache): {len(seed)} seeded preserved byte-exact, only {len(cbh)} new judged"


def test_l3_gen_cases_dedup_and_bugset():
    """gen_cases de-dups by hash (unique pairs) and, via real.MODEL, spans the FULL benchmark bug set
    (not the old 2-bug default) so the judge-quality eval samples the real population."""
    from benchmarks.eval import l3_eval

    import benchmarks.real as real
    cases = l3_eval.gen_cases(real.MODEL)
    hashes = [c["hash"] for c in cases]
    assert len(hashes) == len(set(hashes)), "gen_cases emitted duplicate-hash cases"
    bugset = {c["target_bug"] for c in cases}
    assert bugset == set(real.BUGS), f"gen_cases must span {real.BUGS}, got {sorted(bugset)}"
    return f"gen_cases: {len(cases)} unique-hash cases spanning {''.join(sorted(bugset))}"


def test_l3_campaign_warns_on_nonconvergence():
    """_judge_campaign prints a LOUD WARNING when the loop fails to reach a fixed point (pins the
    `if not converged:` branch). Model-free + ISOLATED: judge_cases never accumulates (-> never converges)
    and _DATA is redirected to a temp dir, so the shipped cache is untouched."""
    import contextlib
    import io
    import pathlib
    import shutil
    import tempfile

    from benchmarks.eval import l3_eval
    orig_judge, orig_data = l3_eval.judge_cases, l3_eval._DATA
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="l3test-"))
    l3_eval.judge_cases = lambda cases, *, model, host=None: {}     # accumulates nothing -> never converges
    l3_eval._DATA = tmp
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            l3_eval._judge_campaign("FAKE", None, seeds=3, max_iters=2)
        out = buf.getvalue()
        assert "WARNING" in out and "did NOT reach a fixed point" in out, f"no non-convergence warning: {out!r}"
        assert (tmp / "llm_cache" / "l3_verdicts.json").exists(), "must still persist the (partial) cache"
    finally:
        l3_eval.judge_cases, l3_eval._DATA = orig_judge, orig_data
        shutil.rmtree(tmp, ignore_errors=True)
    return "_judge_campaign: loud WARNING fires on non-convergence (isolated temp write)"


def test_live_run_binary_returncode_and_dump():
    """benchmarks.live.run_binary maps the exit code to crash truth (== crash_rc) and captures the dump
    text. Model-free: subprocess is faked, no real binary needed."""
    import subprocess

    from benchmarks import live

    class _CP:
        def __init__(self, rc, out):
            self.returncode, self.stderr, self.stdout = rc, out.encode(), b""

    seen = {}

    def fake(cmd, env=None, capture_output=None, timeout=None):
        seen.update(env)
        return _CP(136 if env["HARNESS_SUBSET"] == "128" else 1, "DUMPTEXT" if env["HARNESS_SUBSET"] == "128" else "")

    orig = subprocess.run
    subprocess.run = fake
    try:
        c1, t1 = live.run_binary("/bin/true", "A", frozenset({7}), 136)    # mask 128 (trigger present)
        c0, t0 = live.run_binary("/bin/true", "A", frozenset(), 136)       # mask 0
        assert c1 is True and "DUMP" in t1, (c1, t1)
        assert c0 is False and t0 == "", (c0, t0)
        assert seen["HARNESS_BUG"] == "A", seen
    finally:
        subprocess.run = orig
    return "run_binary: exit==crash_rc -> crashed + dump captured; else not-crashed"


def test_live_oracle_reproduces_offshelf():
    """The off-the-shelf live runner (mocked binary + fake judge) drives the binary for crash truth, varies
    the LIVE-captured dump, escalates to L3, and reproduces bug A at 0 false-credit — the deployable path."""
    import subprocess

    from benchmarks import live
    dump = ("=== CRASH sig=SIGFPE ===\n"
            "./testbinary(ull_conn_update_parameters+0xdc) [0x56639338]\n"
            "./testbinary(llcp_rp_cu_run+0x20) [0x5663bfeb]\n"
            "./testbinary(ull_cp_run+0x1d) [0x5663209d]\n")

    class _CP:
        def __init__(self, rc, out):
            self.returncode, self.stderr, self.stdout = rc, out.encode(), b""

    def fake(cmd, env=None, capture_output=None, timeout=None):
        crash = bool(int(env["HARNESS_SUBSET"]) & (1 << 7))                  # bug-A trigger = index 7
        return _CP(136 if crash else 1, dump if crash else "")

    orig = subprocess.run
    subprocess.run = fake
    try:
        rows, oracle, identity = live.run_live("A", seeds=2, binary=live.__file__,
                                               judge=lambda t, r, **k: {"same": True, "conf": 0.9})
        agg = live._agg(rows)
        assert agg["genuine"] == 1.0 and agg["false_credit"] == 0.0, agg
        assert oracle.binary_runs > 0, "the live binary was never driven"
        assert identity.stats["l2_decided"] > 0, identity.stats
        assert identity.stats["l3_live"] > 0, \
            f"the live L3 must ACTUALLY escalate (the off-the-shelf headline); got {identity.stats}"
    finally:
        subprocess.run = orig
    return (f"off-the-shelf: genuine {agg['genuine']:.2f} / fc {agg['false_credit']:.2f}; "
            f"binary_runs {oracle.binary_runs}; L3 {identity.stats['l3_live']} live / {identity.stats['l3_memo']} memo")


def test_live_offshelf_bug_c():
    """Bug C (an ASSERT — exit 255, site-only dump, no backtrace) reproduces off-the-shelf with a mocked
    binary — pins _CRASH_RC['C']=255 and the assert-dump path MODEL-FREE (the binary-agrees test SKIPs in CI)."""
    import subprocess

    from benchmarks import live
    cdump = "ASSERTION FAIL [ntf] @ ull_llcp_conn_upd.c:247\n=== CRASH sig=SIGABRT ===\n"

    class _CP:
        def __init__(self, rc, out):
            self.returncode, self.stderr, self.stdout = rc, out.encode(), b""

    def fake(cmd, env=None, capture_output=None, timeout=None):
        crash = (int(env["HARNESS_SUBSET"]) & 24) == 24                      # bug-C trigger = indices {3,4} (mask 24)
        return _CP(255 if crash else 1, cdump if crash else "")

    orig = subprocess.run
    subprocess.run = fake
    try:
        rows, oracle, identity = live.run_live("C", seeds=2, binary=live.__file__,
                                               judge=lambda t, r, **k: {"same": True, "conf": 0.9})
        agg = live._agg(rows)
        assert agg["genuine"] == 1.0 and agg["false_credit"] == 0.0, agg     # exit 255 -> crash mapping pins _CRASH_RC['C']
        assert oracle.binary_runs > 0
    finally:
        subprocess.run = orig
    return f"off-the-shelf bug C (assert, exit 255): genuine {agg['genuine']:.2f} / fc {agg['false_credit']:.2f}"


def test_live_binary_agrees_with_truth():
    """If the REAL target binaries are present, EACH bug's LIVE crash truth matches the committed truth
    table — and each bug routes to its OWN harness (A,C=multibug, B=cis, D=phy, E=dle; routing all to
    multibug silently breaks B,D,E). SKIPs when any binary is absent (e.g. CI)."""
    from benchmarks import live
    truth = multibug.TRUTH
    bugs = tuple(truth)                                       # validate every bug the committed truth file declares
    if not all(b in live._BINARIES and live._BINARIES[b].exists() for b in bugs):
        return "SKIP (a target binary is absent — build via src/emulation/zephyr-targets/scripts/*.sh)"
    mism = []
    for bug in bugs:
        W = live._WINDOW[bug]
        trig = sum(1 << i for i in live._TRUE_MIN[bug])
        for mask in (0, 1, trig, (1 << W) - 1):                # benign, a lone decoy, the trigger, full window
            subset = frozenset(i for i in range(W) if mask & (1 << i))
            crashed, _ = live.run_binary(live._BINARIES[bug], bug, subset, live._CRASH_RC[bug])
            if crashed != (truth[bug].get(str(mask)) == bug):
                mism.append((bug, mask, crashed, truth[bug].get(str(mask))))
    assert not mism, f"live-binary vs truth-table disagreements: {mism}"
    return "live binary crash-truth == committed truth-multibug.json (all 6 bugs on their OWN harness binaries)"


def test_scenario_dedup_families():
    """Scenario crash-dedup distinguishes all real families on VARIED crash logs — splitting A from B (both
    SIGFPE) and C, D, E, F (four asserts at distinct sites) by crash SITE, not just fault type. The
    load-bearing classify step."""
    import random

    from benchmarks import scenario
    from emulation.dump import DumpModel, DumpParams
    m = DumpModel.from_logs(multibug.LOGS, bugs=scenario._BUGS)
    refs = {b: m.clean_obs(b) for b in scenario._BUGS}
    dd = scenario.CrashDeduper(refs)
    rng = random.Random(0)
    ok = wrong = tot = 0
    for _ in range(60):
        for b in scenario._BUGS:
            p = dd.classify(m.emit(b, rng))
            ok += int(p == b)
            wrong += int(p is not None and p != b)             # a WRONG family = false-merge (a mis-route)
            tot += 1
    assert wrong == 0, f"dedup must be FAIL-SAFE: {wrong} wrong-family false-merges (errors must abstain ∅, not mis-route)"
    assert ok / tot >= 0.95, f"dedup recall only {ok}/{tot}"
    # the fail-safe property must hold even under SEVERE report-noise (errors -> more ∅, never a false-merge)
    hard = DumpModel.from_logs(multibug.LOGS, bugs=scenario._BUGS,
                               params=DumpParams(p_garble=0.6, p_truncate=0.6, p_lose_top=0.5))
    wrong_hard = sum(1 for _ in range(40) for b in scenario._BUGS
                     if (p := dd.classify(hard.emit(b, rng))) is not None and p != b)
    assert wrong_hard == 0, f"under SEVERE noise dedup false-merged {wrong_hard} times (must only abstain)"
    return f"scenario dedup: {ok}/{tot} correct, 0 wrong-family (fail-safe: errors -> ∅, never false-merge; incl. severe noise)"


def test_scenario_trace_realism():
    """generate_campaign yields realistic traces: spread across all real bugs, each a noisy session with decoys
    + cross-bug LOOK-ALIKES + the bug's real trigger pattern + its varied crash log."""
    import random

    from benchmarks import scenario
    from emulation.dump import DumpModel
    m = DumpModel.from_logs(multibug.LOGS, bugs=scenario._BUGS)
    traces = scenario.generate_campaign(40, m, random.Random(1))
    assert {t.bug for t in traces} == set(scenario._BUGS), "campaign must span every bug"
    for t in traces:
        assert all(p in t.pdus for p in scenario._TRIGGERS[t.bug]), (t.bug, "trace missing its trigger pattern")
        assert t.crash_obs is not None
    assert any(any(la in t.pdus for la in scenario._LOOKALIKES) for t in traces), "no cross-bug look-alikes (combinations)"
    return f"scenario traces: {len(traces)} sessions spanning all {len(scenario._BUGS)} bugs (decoys + triggers + look-alikes)"


def test_scenario_pipeline_end_to_end():
    """The full scenario pipeline (dedup -> route to the correct per-bug binary -> RDD minimise -> score) over
    a small campaign on the REAL binaries with a fake judge: 0 false-credit, dedup routes correctly, genuine
    PoCs delivered. SKIPs if a binary is absent (e.g. CI)."""
    from benchmarks import live, scenario
    if not all(live._BINARIES[b].exists() for b in scenario._BUGS):
        return "SKIP (a target binary is absent — build the 6 bugs' harnesses first)"
    rows, confusion, _ = scenario.run_scenario(8, judge=lambda t, r, **k: {"same": True, "conf": 0.9})
    s = scenario._summary(rows, confusion)
    assert s["false_credit"] == 0.0, s
    assert s["dedup_accuracy"] >= 0.75 and s["end_to_end_genuine"] >= 0.75, s
    assert s["exact_minimal_of_genuine"] >= 0.5 and s["mean_size_gap_genuine"] <= 1.0, s   # PoCs mostly exact-minimal
    return (f"scenario e2e: dedup {s['dedup_accuracy']:.2f} / genuine {s['end_to_end_genuine']:.2f} / "
            f"fc {s['false_credit']:.2f} / exact-min {s['exact_minimal_of_genuine']:.2f} (real binaries, fake judge)")


def test_scenario_dedup_is_load_bearing():
    """A WRONG dedup ROUTES the minimiser to the wrong binary -> NO genuine PoC for that trace (genuine is
    gated on predicted==bug). Inject an always-'A' deduper: only A-traces stay genuine; B/C/D/E/F mis-route and
    fail — at 0 false-credit (the minimiser is still sound, it just reproduced the wrong bug). SKIPs if a
    binary is absent."""
    from benchmarks import live, scenario
    if not all(live._BINARIES[b].exists() for b in scenario._BUGS):
        return "SKIP (a target binary is absent)"

    class _AlwaysA:
        def classify(self, obs):
            return "A"

    rows, confusion, campaigns = scenario.run_scenario(8, judge=lambda t, r, **k: {"same": True, "conf": 0.9},
                                                       deduper=_AlwaysA())
    assert set(campaigns) == {"A"}, \
        f"always-A dedup must ROUTE the minimiser ONLY to A's binary (route-on-PREDICTION), got {set(campaigns)}"
    by_bug = {}
    for r in rows:
        by_bug.setdefault(r.bug, []).append(r.genuine)
    assert by_bug.get("A") and all(by_bug["A"]), "A-traces (dedup correct) must still be genuine"
    assert not any(g for b in ("B", "C", "D", "E", "F") for g in by_bug.get(b, [])), "mis-routed B/C/D/E/F must NOT be genuine"
    assert scenario._summary(rows, confusion)["false_credit"] == 0.0, "mis-routing must not cause false-credit"
    return "scenario dedup load-bearing: always-A dedup -> routes only to A, only A genuine, B/C/D/E/F fail, 0 fc"


def test_scenario_soundness_mocked():
    """Model-free scenario soundness — pins genuine>0 / fc==0 / route-on-PREDICTED WITHOUT the real binaries,
    so the scenario soundness is NOT SKIP-only in CI. Mocks each bug's binary (crash on its trigger, its real
    captured dump) + a fake judge; points _BINARIES at an existing file so the setup check passes."""
    import subprocess
    from pathlib import Path as _P

    from benchmarks import live, scenario
    logs = {b: (multibug.LOGS / f"dump-bug-{b.lower()}.txt").read_text(encoding="utf-8") for b in scenario._BUGS}

    class _CP:
        def __init__(self, rc, out):
            self.returncode, self.stderr, self.stdout = rc, out.encode(), b""

    def fake(cmd, env=None, capture_output=None, timeout=None):
        bug, mask = env["HARNESS_BUG"], int(env["HARNESS_SUBSET"])
        crash = bool(mask & (1 << 7)) if bug in ("A", "B") else (mask & 24) == 24    # trigger-last / two-IND
        return _CP(live._CRASH_RC[bug] if crash else 1, logs[bug] if crash else "")

    orig_run, orig_bins = subprocess.run, dict(live._BINARIES)
    subprocess.run = fake
    for b in scenario._BUGS:
        live._BINARIES[b] = _P(live.__file__)                  # an existing file (subprocess is mocked anyway)
    try:
        fj = {"same": True, "conf": 0.9}
        rows, confusion, _ = scenario.run_scenario(8, judge=lambda t, r, **k: fj)
        s = scenario._summary(rows, confusion)
        assert s["false_credit"] == 0.0, s
        assert s["end_to_end_genuine"] > 0.0, s
        for r in rows:                                         # route-on-prediction: a genuine row reproduced its
            assert (not r.genuine) or r.predicted == r.bug, r  #   OWN correctly-deduped family
        # the LOAD-BEARING gate + routing, MODEL-FREE: an always-A dedup routes ONLY to A; B/C/D mis-route
        always_a = type("_AllA", (), {"classify": lambda self, o: "A"})()
        rows2, conf2, camps2 = scenario.run_scenario(8, judge=lambda t, r, **k: fj, deduper=always_a)
        assert set(camps2) == {"A"}, f"always-A dedup must ROUTE only to A, got {set(camps2)}"
        assert not any(r.genuine for r in rows2 if r.bug != "A"), "mis-routed B/C/D/E must NOT be genuine"
        assert scenario._summary(rows2, conf2)["false_credit"] == 0.0, "mis-route must not false-credit"
    finally:
        subprocess.run = orig_run
        live._BINARIES.clear()
        live._BINARIES.update(orig_bins)
    return f"scenario soundness (mocked, model-free): genuine {s['end_to_end_genuine']:.2f} / fc {s['false_credit']:.2f}"


def test_scenario_multiseed_robust_invariants():
    """PIECE 4 -- the off-the-shelf scenario over MULTIPLE seeds, model-free + binary-mocked so it RUNS IN CI.
    It pins the ROBUST invariants the disclosed-live end-to-end rests on -- dedup robustly high + 0 false-credit across
    EVERY seed -- AND that genuine reproduces ROBUSTLY (mean >= 0.75, every seed >= 0.65, in line with the
    disclosed-live ~0.87). It does NOT reproduce the LIVE genuine RANGE itself: that is substantiated separately
    by the disclosed-live benchmarks/data/reference/scenario_multiseed.json (8 live seeds: mean 0.872, range
    [0.825, 0.925]), which a live model + OTA channel make non-bit-reproducible -- so the RANGE is that claim."""
    import subprocess
    from pathlib import Path as _P

    from benchmarks import live, scenario
    logs = {b: (multibug.LOGS / f"dump-bug-{b.lower()}.txt").read_text(encoding="utf-8") for b in scenario._BUGS}

    class _CP:
        def __init__(self, rc, out):
            self.returncode, self.stderr, self.stdout = rc, out.encode(), b""

    def fake(cmd, env=None, capture_output=None, timeout=None):
        bug, mask = env["HARNESS_BUG"], int(env["HARNESS_SUBSET"])
        crash = bool(mask & (1 << 7)) if bug in ("A", "B") else (mask & 24) == 24
        return _CP(live._CRASH_RC[bug] if crash else 1, logs[bug] if crash else "")

    orig_run, orig_bins = subprocess.run, dict(live._BINARIES)
    subprocess.run = fake
    for b in scenario._BUGS:
        live._BINARIES[b] = _P(live.__file__)
    try:
        out = scenario.run_multiseed(40, 4, judge=lambda t, r, **k: {"same": True, "conf": 0.9})
    finally:
        subprocess.run = orig_run
        live._BINARIES.clear()
        live._BINARIES.update(orig_bins)
    assert out["false_credit"]["max"] == 0.0, f"false-credit must be 0 across ALL seeds, got {out['false_credit']}"
    assert out["dedup_accuracy"]["min"] > 0.8, f"dedup must be robustly high across seeds, got {out['dedup_accuracy']}"
    g = out["genuine"]
    # genuine must reproduce ROBUSTLY (not merely not-collapse): mean in line with the disclosed-live ~0.87,
    # and EVERY seed materially reproducing -- tight enough to catch a real regression (deterministic fixture).
    assert g["n"] == 4 and g["mean"] >= 0.75 and g["min"] >= 0.65, f"genuine must reproduce robustly every seed, got {g}"
    return (f"scenario multi-seed (mocked CI, 4 seeds): genuine mean {g['mean']:.2f} range [{g['min']:.2f},{g['max']:.2f}]; "
            f"dedup min {out['dedup_accuracy']['min']:.2f}; fc max {out['false_credit']['max']:.2f} (robust across seeds)")


def test_l3_provenance_self_documents_source():
    """PIECE 2 -- every benchmark family self-documents its L3 SOURCE, and the cached-real headline is
    LIVE-FREE. (1) real + suppressor: source=cached_open_model, model read from the committed cache (not
    hard-coded), the reproducibility-critical invariant live_calls==0 (id_l2l3 has NO live-model call -- a
    cache miss is a conservative NO), and escalations == cache_hits + rule_no_fallback (every escalation
    resolves one way). The EXACT committed counts (164/40, 0 fallback) are gated by coherence(); this pins
    the structural invariant cheaply. (2) synthetic: source=deterministic_rule, model=None -- the resilience
    headline never exercises the open model."""
    r = run.run_real(5)
    s = run.run_suppressor(5, ablate=True)
    for tag, prov in (("real", r["l3_provenance"]), ("supp", s["l3_provenance"])):
        assert prov["source"] == "cached_open_model", f"{tag} source: {prov['source']}"
        assert prov["live_calls"] == 0, f"{tag} cached path must be LIVE-FREE, got {prov['live_calls']} live calls"
        assert prov["escalations"] == prov["cache_hits"] + prov["rule_no_fallback"], f"{tag}: {prov}"
        assert prov["model"] and prov["model"] != "none", f"{tag} model must come from the cache, got {prov['model']!r}"
    from benchmarks import resilience
    y = resilience.run(120, 1)                                   # the B2 sweep self-documents its source
    assert y["l3_provenance"] == resilience.L3_PROVENANCE == {"source": "deterministic_rule", "model": None}, y["l3_provenance"]
    return (f"L3 source self-documented: real cached_open_model ({r['l3_provenance']['model']}, live=0, "
            f"hits={r['l3_provenance']['cache_hits']}); B2 resilience deterministic_rule (no LLM)")


def test_scenario_l3_provenance_live():
    """PIECE 2 -- the live off-the-shelf scenario self-documents its LIVE L3 usage. _summary aggregates the
    per-bug identity stats into l3_provenance (source=live_open_model); the live total matches the per-trace
    deltas, and WITHOUT campaigns the field is omitted (back-compat)."""
    from benchmarks import live, scenario
    if not all(live._BINARIES[b].exists() for b in scenario._BUGS):
        return "SKIP (a target binary is absent — build the 6 bugs' harnesses first)"
    rows, confusion, campaigns = scenario.run_scenario(8, judge=lambda t, r, **k: {"same": True, "conf": 0.9})
    s = scenario._summary(rows, confusion, campaigns, "fake-judge")
    lp = s["l3_provenance"]
    assert lp["source"] == "live_open_model" and lp["model"] == "fake-judge", lp
    assert lp["l3_live"] == sum(r.l3_live for r in rows), f"live total {lp['l3_live']} != per-trace sum {sum(r.l3_live for r in rows)}"
    assert lp["l3_live"] >= 0 and lp["l3_memo"] >= 0 and lp["l2_decided"] >= 0, lp
    assert "l3_provenance" not in scenario._summary(rows, confusion), "campaigns=None must omit l3_provenance (back-compat)"
    return f"scenario L3 live provenance: {lp['l3_live']} live / {lp['l3_memo']} memo / {lp['l2_decided']} L2-decided"


def test_cached_and_synthetic_paths_never_call_live_judge():
    """PIECE 2 -- make the live-free claim NON-VACUOUS. l3_provenance's live_calls is a hardcoded 0, so
    asserting it alone is tautological; here we pin the BEHAVIOUR. (1) the cached-real + synthetic identity
    modules must not even import the live judge; (2) wrapping rdd.l3.judge_ollama with a call counter, a full
    cached-real (real + suppressor) + synthetic run makes ZERO live judge calls. A future regression that wires
    a live model call into id_l2l3 (the reproducibility-breaking change) FAILS here."""
    import rdd.identity as _ident                               # binds judge_ollama at import: LiveL2L3Identity's
    import rdd.l3 as _l3                                        # default judge resolves THERE, so patch both names
    from benchmarks import real, resilience, synthetic
    assert not hasattr(real, "judge_ollama"), "real.py must NOT import the live judge (cached path is live-free)"
    assert not hasattr(synthetic, "judge_ollama"), "synthetic.py must NOT import the live judge (deterministic rule)"
    assert not hasattr(resilience, "judge_ollama"), "resilience.py (B2) must NOT import the live judge"
    calls, orig = [0], _l3.judge_ollama
    def _counting(*a, **k):
        calls[0] += 1
        return orig(*a, **k)
    _l3.judge_ollama = _ident.judge_ollama = _counting
    try:
        run.run_real(3)
        run.run_suppressor(3)
        resilience.run(120, 1)                                  # the B2 synthetic sweep (id_l2l3 deterministic rule)
    finally:
        _l3.judge_ollama = _ident.judge_ollama = orig
    assert calls[0] == 0, f"cached-real + B2 synthetic paths must make ZERO live judge calls, made {calls[0]}"
    return "live-free pinned behaviourally: 0 live judge calls across cached-real + B2 synthetic; no judge_ollama import"


def test_causeswap_cause_swap_guard():
    """PIECE 3 -- the Mode-2 cause-swap guard DEMONSTRATED on a co-present multi-bug deployment under a
    CRASH-ONLY in-loop oracle (the case the guard is FOR), using the REAL A/C crash dumps + the REAL L2+L3
    identity (the guard's check) + the full pipeline. The A+C co-presence AND the crash-only in-loop are
    MODELLED + disclosed (the cached-real benchmark's in-loop IS identity-aware, so the guard is a no-op
    there). The guard ELIMINATES the cause-swap false-credit while PRESERVING genuine reproduction
    (demote-only). Deterministic -> also reproduces the committed reference byte-for-byte."""
    import json
    from benchmarks import causeswap
    d = causeswap.run(30)
    ref = json.loads((run._REF / "causeswap.json").read_text(encoding="utf-8"))
    assert d == ref, "causeswap must reproduce the committed reference exactly (incl. the provenance prose)"
    sw = d["arms"]["swap"]
    # the cause-swap: guard OFF mis-credits the co-present C crash as an A reproduction; guard ON DEMOTES it.
    assert sw["guard_off"]["false_credit"] > 0.5, f"guard OFF must false-credit the cause-swap, got {sw['guard_off']}"
    assert sw["guard_on"]["false_credit"] == 0.0, f"guard ON must DEMOTE the cause-swap to fc 0, got {sw['guard_on']}"
    assert sw["guard_off"]["genuine"] == 0.0 and sw["guard_on"]["genuine"] == 0.0, "the swap is never genuinely A"
    # demote-only: the guard never reduces a genuine reproduction (both correct-target arms IDENTICAL on/off).
    for arm in ("genuine_A", "genuine_C"):
        a = d["arms"][arm]
        assert a["guard_on"]["genuine"] == a["guard_off"]["genuine"] > 0.5, f"{arm} genuine must be unchanged + high: {a}"
        assert a["guard_on"]["false_credit"] == 0.0, f"{arm} must not false-credit: {a}"
    return (f"Mode-2 guard demo (real dumps+identity, crash-only in-loop): cause-swap fc "
            f"{sw['guard_off']['false_credit']:.2f}->{sw['guard_on']['false_credit']:.2f}; "
            f"genuine_A/C unchanged {d['arms']['genuine_A']['guard_on']['genuine']:.2f}")


def test_l2_threshold_not_overfit():
    """PIECE 5 -- the L2 identity THRESHOLD is NOT overfit to the real bugs A--F (under the modelled OTA noise;
    the eval validates the THRESHOLD, not the literature-grounded weights). On the real base dumps + modelled
    variation: (1) same-vs-cross L2 similarity is near-perfectly separable (AUC >= 0.95) and STABLE across
    variation seeds (not a seed-0 fluke); (2) the fit-on-A--F Youden-J optimum ~= the FIXED default 0.5
    (|diff| <= 0.1 -> near-optimal, not arbitrary); (3) balanced accuracy is FLAT on a WIDE plateau CONTAINING
    0.5 (not a fragile tuned peak); (4) the L3 band 0.05 is conservative (0 same-bug at risk). Deterministic ->
    reproduces the committed reference byte-for-byte."""
    import json

    from benchmarks.eval import l2_threshold_eval as lt
    d = lt.evaluate()
    ref = json.loads((lt._DATA / "reference" / "l2_threshold_eval.json").read_text(encoding="utf-8"))
    assert abs(d["auc"] - ref["auc"]) < 1e-9 and abs(d["youden_threshold"] - ref["youden_threshold"]) < 1e-9, "must reproduce committed"
    assert d["sweep"] == ref["sweep"] and d["plateau"] == ref["plateau"] and d["band"] == ref["band"] and d["stability"] == ref["stability"], "sweep/plateau/band/stability must reproduce committed"
    assert d["auc"] >= 0.95 and d["stability"]["auc_min"] >= 0.95, f"same/cross must be near-separable + STABLE across seeds, got {d['auc']:.3f}/{d['stability']}"
    assert d["stability"]["default_in_plateau_all_seeds"] is True, f"the default 0.5 must be on the plateau in EVERY seed, got {d['stability']}"
    lo_c, hi_c = d["stability"]["plateau_common"]               # the band that is a plateau in ALL seeds (semantic, not just reproduced)
    assert lo_c <= d["default_threshold"] <= hi_c and (hi_c - lo_c) >= 0.2, f"the cross-seed COMMON plateau must contain 0.5 + be WIDE, got {d['stability']['plateau_common']}"
    assert abs(d["youden_threshold"] - d["default_threshold"]) <= 0.1, f"default must be ~data-optimal, got Youden {d['youden_threshold']:.3f}"
    lo, hi = d["plateau"]
    assert lo <= d["default_threshold"] <= hi and (hi - lo) >= 0.2, f"default 0.5 must sit inside a WIDE flat plateau, got {d['plateau']}"
    assert d["sweep"]["0.50"]["balanced"] >= d["best_balanced"] - 0.02, "the default 0.5 must be ~flat (not a fragile peak)"
    assert d["same"]["mean"] - d["cross"]["mean"] >= 0.5, f"same vs cross must separate: {d['same']['mean']:.2f} vs {d['cross']['mean']:.2f}"
    # the L3 band is conservative: it risks NO same-bug miss and sits far below the same-bug score floor.
    assert d["band"]["same_at_risk_below_band"] == 0.0, f"the L3 band must risk no same-bug miss, got {d['band']}"
    assert d["band"]["max_safe_band_same_min"] >= d["band"]["band"] + 0.2, f"the band must be far below the safe ceiling, got {d['band']}"
    return (f"L2 threshold NOT overfit (A--F, modelled noise): AUC {d['auc']:.3f} (stable {d['stability']['auc_min']:.3f}-{d['stability']['auc_max']:.3f}); "
            f"default 0.5 ~ Youden {d['youden_threshold']:.3f}; flat plateau {d['plateau']}; band 0.05 safe<{d['band']['max_safe_band_same_min']:.2f}")


def test_b1_headtohead_coherence():
    """B1 (the real head-to-head, benchmarks.headtohead) reproduces its committed reference EXACTLY from the
    FROZEN L3 memo with 0 live model calls. SKIPS without the built host-native binaries (like the other
    real-binary tests); where they exist it gates EVERY published B1 number vs data/reference/headtohead.json."""
    from benchmarks import headtohead, live
    from benchmarks.scenario import _BUGS
    if not all(live._BINARIES[b].exists() for b in _BUGS):
        return "SKIP (host-native binaries absent — build via src/emulation/zephyr-targets/)"
    assert headtohead.coherence(42, 8), "B1 frozen replay must reproduce the committed reference (delta=0, 0 live calls)"
    return "B1 head-to-head: frozen replay reproduces the committed reference (every leaf; 0 live calls)"


def test_b2_resilience_smoke():
    """B2 (benchmarks.resilience) runs, exposes B1's FULL metric set per arm, is DETERMINISTIC (re-run
    identical at a small size — the property the full gate rests on), and the AS-SHIPPED head-to-head
    invariants hold across EVERY regime: RDD is sound (false_credit ~0, alpha-bounded) and materially
    out-reproduces the fixed-K AirBug baseline (which false-credits) — at a higher device-read cost (the
    honest trade). TWO arms only; the ablation / lever decomposition is B3. The full 2500x5 leaf-exact
    reproducibility gate is the CI step `python -m benchmarks.run coherence` (it re-runs this B2 sweep + the
    real anchor, model-free, so it runs in vanilla CI -- unlike the binary-gated B1 gate above)."""
    from benchmarks import resilience, scoring
    a = resilience.run(150, 2)
    b = resilience.run(150, 2)
    assert scoring.leaf_diffs(scoring.clean_nan(b), scoring.clean_nan(a)) == [], "B2 must be deterministic (re-run identical)"
    regs = a["regimes"]
    assert set(regs) == {"standard", "high_card", "suppressor", "far_trigger", "deep_noise", "wide_window", "OVERALL"}, f"B2 regimes: {set(regs)}"
    assert set(regs["standard"]) == set(resilience.ARMS) == {"baseline", "tool"}, "B2 is a 2-arm head-to-head (ablation/levers are B3)"
    assert set(regs["standard"]["tool"]) == set(resilience.METRICS) == {
        "genuine", "false_credit", "exact_minimal", "mean_size_gap", "reads"}, "B2 must report B1's full metric set"
    g = lambda reg, arm, k="genuine": regs[reg][arm][k][0]       # noqa: E731  (CI mean)
    for reg in regs:                                             # RDD sound + out-reproduces AirBug in every regime
        assert g(reg, "tool", "false_credit") <= 0.02, f"RDD false_credit must be ~0 in {reg}, got {g(reg, 'tool', 'false_credit')}"
        assert g(reg, "tool") > g(reg, "baseline") + 0.2, f"RDD genuine must beat AirBug in {reg}: {g(reg,'tool'):.2f} vs {g(reg,'baseline'):.2f}"
    assert g("standard", "baseline", "false_credit") > 0.1, "the fixed-K AirBug baseline must false-credit"
    assert g("OVERALL", "tool", "reads") > g("OVERALL", "baseline", "reads"), "RDD's robustness costs more device reads (the honest trade)"
    assert a["l3_provenance"] == {"source": "deterministic_rule", "model": None}, "B2 is model-free"
    return (f"B2 smoke (150x2, deterministic, 2 arms x 6 regimes): RDD fc<=0.02 + out-reproduces AirBug every regime; "
            f"OVERALL genuine RDD {g('OVERALL', 'tool'):.2f} vs AirBug {g('OVERALL', 'baseline'):.2f}; "
            f"reads {g('OVERALL', 'tool', 'reads'):.0f} vs {g('OVERALL', 'baseline', 'reads'):.0f}; baseline fc {g('standard', 'baseline', 'false_credit'):.2f}")


def test_b3_levers_coherence():
    """B3 (the real lever decomposition, benchmarks.levers) reproduces its committed reference EXACTLY from the
    FROZEN L3 memo with 0 live model calls. SKIPS without the built host-native binaries (like the other
    real-binary tests); where they exist it gates EVERY published B3 number — the 4-arm cube over A--F, the
    suppressor arms, and the 3 lever deltas — vs data/reference/levers.json."""
    from benchmarks import levers, live
    from benchmarks.scenario import _BUGS
    if not all(live._BINARIES[b].exists() for b in _BUGS):
        return "SKIP (host-native binaries absent — build via src/emulation/zephyr-targets/)"
    assert levers.coherence(8), "B3 frozen replay must reproduce the committed reference (delta=0, 0 live calls)"
    return "B3 lever decomposition: frozen replay reproduces the committed reference (every leaf; 0 live calls)"


def test_leaf_diffs_comparator():
    """The hoisted coherence comparator (scoring.leaf_diffs — shared by B1/B2/B3) pinned DIRECTLY, so a future
    edit can't silently weaken every headline's reproducibility gate: a numeric leaf matches within tol (not
    exactly), a NaN-as-null leaf must stay null, bool/string match exactly, a bool fresh must NOT match an int
    ref (1 != True), a missing key is a diff, and skip_top skips ONLY at the TOP level (a NESTED 'l3_live' must
    still be gated, else a per-arm metric could drift undetected)."""
    from benchmarks import scoring
    ld = scoring.leaf_diffs
    assert ld({"a": 1.0}, {"a": 1.0 + 1e-12}) == [], "a numeric leaf within tol must match"
    assert ld({"a": 1.0}, {"a": 1.1}) == [("a", 1.0, 1.1)], "a numeric leaf outside tol must diff"
    assert ld({"a": None}, {"a": None}) == [], "null stays null"
    assert ld({"a": 5}, {"a": None}) == [("a", 5, None)], "non-null where ref is null must diff"
    assert ld({"a": True}, {"a": False}) == [("a", True, False)], "bool matches exactly"
    assert ld({"a": "x"}, {"a": "y"}) == [("a", "x", "y")], "string matches exactly"
    assert ld({"a": True}, {"a": 1}) == [("a", True, 1)], "a bool fresh must NOT match an int ref (1 is not True)"
    assert ld({}, {"a": 1.0}) == [("a", None, 1.0)], "a missing key (-> None lookup) must diff"
    # skip_top is TOP-LEVEL ONLY: a top-level l3_live is ignored, a NESTED one is still gated
    assert ld({"l3_live": 9, "x": 1.0}, {"l3_live": 0, "x": 1.0}, skip_top=("l3_live",)) == [], "top-level l3_live must be skipped"
    assert ld({"r": {"l3_live": 9}}, {"r": {"l3_live": 0}}, skip_top=("l3_live",)) == [("r.l3_live", 9, 0)], "a NESTED l3_live must still be gated"
    return "leaf_diffs: tol-numeric + null + bool/str exact + bool!=int + missing-key + skip_top TOP-LEVEL-only"


def test_b1_reference_invariants():
    """B1 (headtohead.json) STRUCTURAL gate — model-free + binary-free, so it runs in vanilla CI where the
    binary-gated test_b1_headtohead_coherence SKIPs. It does NOT re-run B1 (that needs the host-native
    binaries); it gates the committed reference's PUBLISHED STORY against a silent drift / hand-edit: RDD
    out-reproduces AirBug end-to-end AND minimiser-isolated, RDD is sound (fc 0) while the fixed-K AirBug
    false-credits, RDD's PoCs are tighter, both arms share ONE (identical) dedup front-end, RDD pays more
    reads (the honest cost trade), and the real suppressor showcase has RDD strictly above AirBug at fc 0."""
    import json
    ref = json.loads((run._REF / "headtohead.json").read_text(encoding="utf-8"))
    ab, rd, sp = ref["airbug"], ref["rdd"], ref["suppressor"]
    metrics = {"genuine", "genuine_routed", "false_credit", "dedup_accuracy", "exact_minimal", "mean_size_gap", "reads"}
    assert metrics <= set(ab) and metrics <= set(rd), f"B1 arms must carry B1's metric set, got {set(ab)} / {set(rd)}"
    m = lambda arm, k: arm[k]["mean"]                            # noqa: E731
    # RDD out-reproduces AirBug end-to-end AND on the minimiser-isolated (correctly-routed) metric
    assert m(rd, "genuine") > m(ab, "genuine"), f"RDD genuine must beat AirBug: {m(rd,'genuine')} vs {m(ab,'genuine')}"
    assert m(rd, "genuine_routed") > m(ab, "genuine_routed"), "RDD genuine_routed must beat AirBug"
    # soundness: RDD false-credit is 0; the fixed-K AirBug false-credits (the lever the SPRT+gate removes)
    assert m(rd, "false_credit") == 0.0, f"RDD false_credit must be 0, got {m(rd,'false_credit')}"
    assert m(ab, "false_credit") > 0.1, f"the fixed-K AirBug must false-credit, got {m(ab,'false_credit')}"
    # tighter PoCs + the honest cost trade + the shared (identical) dedup front-end
    assert m(rd, "exact_minimal") > m(ab, "exact_minimal") and m(rd, "mean_size_gap") < m(ab, "mean_size_gap"), "RDD PoCs must be tighter"
    assert m(rd, "reads") > m(ab, "reads"), "RDD must pay more reads (the honest correctness-for-reads trade)"
    assert m(rd, "dedup_accuracy") == m(ab, "dedup_accuracy"), "both arms share ONE dedup front-end (identical accuracy)"
    # the real non-monotone suppressor showcase: RDD strictly above AirBug, sound vs the baseline's false-credit
    assert sp["rdd"]["genuine"] > sp["airbug"]["genuine"] and sp["rdd"]["false_credit"] == 0.0 < sp["airbug"]["false_credit"], f"suppressor showcase off: {sp}"
    # a loose magnitude pin (catches a wholesale value corruption without duplicating the exact binary-gated gate)
    assert 0.80 <= m(rd, "genuine") <= 0.95 and 0.70 <= m(ab, "genuine") <= 0.80, f"B1 headline magnitudes drifted: RDD {m(rd,'genuine')} / AirBug {m(ab,'genuine')}"
    assert ref["l3_live"] > 0, "the reference must record the live-freeze L3-call count"
    return (f"B1 reference invariants (model-free): RDD genuine {m(rd,'genuine'):.3f} > AirBug {m(ab,'genuine'):.3f}; "
            f"RDD fc 0 < AirBug {m(ab,'false_credit'):.3f}; RDD reads {m(rd,'reads'):.0f} > {m(ab,'reads'):.0f}; "
            f"suppressor RDD {sp['rdd']['genuine']:.2f} > AirBug {sp['airbug']['genuine']:.2f}")


def test_b3_lever_consistency():
    """B3 (levers.json) STRUCTURAL gate — model-free + binary-free, so it runs in vanilla CI where the
    binary-gated test_b3_levers_coherence SKIPs. It does NOT re-run B3; it RECOMPUTES the published lever
    deltas from the committed arm numbers and asserts they MATCH the committed `levers` block (so a hand-edit
    that desyncs a delta from its arms is caught), plus the published SIGNS: the IDENTITY lever adds genuine
    (oracle -> ablation), the ROBUST MINIMISER recovers the suppressor (bare ddmin bails, the tool recovers),
    and the ORACLE/gate lever is the false-credit INVARIANCE (the fixed-K baseline false-credits, the 3
    pipeline arms do not)."""
    import json
    ref = json.loads((run._REF / "levers.json").read_text(encoding="utf-8"))
    real, sup, lev = ref["real"], ref["suppressor"], ref["levers"]
    arms = ["baseline", "oracle", "ablation", "tool"]           # the renamed ladder (arm_c -> oracle)
    assert list(real) == arms and list(sup) == arms and list(lev["oracle_fc_invariance"]) == arms, \
        f"B3 must carry the 4-arm ladder baseline/oracle/ablation/tool, got real={list(real)}"
    close = lambda a, b: abs(a - b) <= 1e-9                      # noqa: E731
    # the lever deltas must be INTERNALLY CONSISTENT with the arms they are computed from (catches a desync)
    idd = real["ablation"]["genuine"]["mean"] - real["oracle"]["genuine"]["mean"]
    assert close(idd, lev["identity_genuine_real"]), f"identity delta desynced: arms={idd} vs levers={lev['identity_genuine_real']}"
    msup = sup["tool"]["genuine"] - sup["ablation"]["genuine"]
    assert close(msup, lev["minimiser_genuine_suppressor"]), f"minimiser delta desynced: arms={msup} vs levers={lev['minimiser_genuine_suppressor']}"
    for a in arms:
        assert close(lev["oracle_fc_invariance"][a], real[a]["false_credit"]["mean"]), f"oracle_fc_invariance[{a}] desynced from the arm fc"
    # the published SIGNS: identity adds genuine; the minimiser recovers the suppressor where bare ddmin bails
    assert lev["identity_genuine_real"] > 0, f"the IDENTITY lever must add genuine, got {lev['identity_genuine_real']}"
    assert lev["minimiser_genuine_suppressor"] > 0, f"the MINIMISER lever must recover the suppressor, got {lev['minimiser_genuine_suppressor']}"
    assert sup["ablation"]["genuine"] == 0.0 < sup["tool"]["genuine"], f"bare ddmin must BAIL (0) and the robust minimiser recover: {sup['ablation']['genuine']}/{sup['tool']['genuine']}"
    # the ORACLE/gate lever = false-credit INVARIANCE: the fixed-K baseline false-credits, the 3 pipeline arms don't
    fci = lev["oracle_fc_invariance"]
    assert fci["baseline"] > 0, f"the fixed-K baseline must false-credit, got {fci['baseline']}"
    assert fci["oracle"] == fci["ablation"] == fci["tool"] == 0.0, f"the 3 pipeline arms must have fc 0 (the gate), got {fci}"
    return (f"B3 lever consistency (model-free): identity +{lev['identity_genuine_real']:.3f} (= ablation-oracle), "
            f"minimiser +{lev['minimiser_genuine_suppressor']:.3f} (suppressor tool {sup['tool']['genuine']:.1f} vs ablation {sup['ablation']['genuine']:.1f}); "
            f"oracle-gate fc-invariance baseline {fci['baseline']:.3f} vs pipeline 0")


TESTS = [test_suite_smoke, test_l3_collect_and_judge, test_l3_score, test_real_credit_path_strict,
         test_l3_judge_fixed_point, test_l3_judge_seed_cache_incremental, test_l3_gen_cases_dedup_and_bugset,
         test_l3_campaign_warns_on_nonconvergence,
         test_l3_judge_eval_anchored, test_live_run_binary_returncode_and_dump, test_live_oracle_reproduces_offshelf,
         test_live_offshelf_bug_c, test_live_binary_agrees_with_truth, test_scenario_dedup_families,
         test_scenario_trace_realism, test_scenario_pipeline_end_to_end, test_scenario_dedup_is_load_bearing,
         test_scenario_soundness_mocked, test_real_suppressor_coherence,
         test_l3_provenance_self_documents_source, test_scenario_l3_provenance_live,
         test_cached_and_synthetic_paths_never_call_live_judge, test_causeswap_cause_swap_guard,
         test_scenario_multiseed_robust_invariants, test_l2_threshold_not_overfit, test_leaf_diffs_comparator,
         test_b1_reference_invariants, test_b1_headtohead_coherence, test_b3_lever_consistency,
         test_b2_resilience_smoke, test_b3_levers_coherence]


def main():
    print("=== benchmarks self-test ===\n")
    failed = skipped = 0
    for fn in TESTS:
        try:
            msg = fn()
            if str(msg).startswith("SKIP"):
                skipped += 1
                print(f"  SKIP  {fn.__name__}: {msg}")
            else:
                print(f"  PASS  {fn.__name__}: {msg}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    tail = f", {skipped} skipped" if skipped else ""
    print(f"\n{'ALL PASS' if not failed else f'{failed} FAILED'} ({len(TESTS) - failed - skipped}/{len(TESTS) - skipped} run{tail})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
