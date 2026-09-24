"""benchmarks self-test: the suites run and the committed references reproduce.

Run:  ``PYTHONHASHSEED=0 python -m benchmarks.tests.test_benchmarks``   (after `pip install -e code/`)
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # code/src -> import rdd + benchmarks

from benchmarks import run
from benchmarks import identity_cache as idc
from emulation import multibug
from emulation import baseline as emulation_baseline


def test_suite_smoke():
    """The real and suppressor suites run; the tool recovers the suppressor and the ddmin-only ablation does not."""
    r = run.run_real(5)
    s = run.run_suppressor(5, ablate=True)
    assert run._metric(r["baseline"]) > 0 and run._metric(r["tool"]) > 0, "real suite produced no reproductions"
    assert run._metric(s["tool"]) >= 0.8, f"tool must recover the suppressor, got {run._metric(s['tool']):.2f}"
    assert run._metric(s["ablation"]) == 0.0, f"ablation must bail on the suppressor, got {run._metric(s['ablation']):.2f}"
    return (f"smoke: real tool {run._metric(r['tool']):.2f}; suppressor tool {run._metric(s['tool']):.2f} / "
            f"ablation {run._metric(s['ablation']):.2f} (bails)")


def test_real_suppressor_coherence():
    """A fresh anchor reproduces anchor.json: every gated arm within +/-0.02 and the tool's L3 provenance equal."""
    assert run.coherence(), "the fresh anchor must reproduce the committed anchor.json"
    return "anchor coherence within +/-0.02 incl. the L3 provenance"


def test_l3_judge_eval_anchored():
    """l3_judge_eval.json re-scores from its stored verdicts without the model."""
    import json as _json

    from benchmarks.eval import l3_eval
    p = l3_eval._DATA / "reference" / "l3_judge_eval.json"
    assert p.exists(), "missing committed judge-eval reference (run `l3_eval eval --model ...` to generate)"
    d = _json.loads(p.read_text(encoding="utf-8"))
    fresh = l3_eval.score(d["cases"], d["verdicts"])           # re-score offline from committed verdicts
    assert abs(fresh["l3_residual_recovery"] - d["score"]["l3_residual_recovery"]) < 1e-12, (fresh, d["score"])
    assert abs(fresh["l3_cross_rejection"] - d["score"]["l3_cross_rejection"]) < 1e-12, (fresh, d["score"])
    return (f"l3_judge_eval anchored ({d['model']}): recall {fresh['l3_residual_recovery']:.3f} / "
            f"rejection {fresh['l3_cross_rejection']:.3f} (re-scored model-free)")


def test_l3_collect_and_judge():
    """collect_cases is deterministic and never re-collects base_cache pairs; judge_cases records the model and
    propagates a parse_error."""
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
    """score() on an asymmetric fixture: recovery counts residuals judged same, rejection counts cross pairs
    judged different."""
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
    """id_l2l3 credits only a cache entry whose ``same`` is the bool True: a string "true" or a numeric 1 does
    not credit."""
    import random as _r

    import benchmarks.real as real
    from rdd.l3 import _pair_hash, render_dump
    rng = _r.Random(0)
    b = real.BUGS[0]
    obs = None
    for _ in range(20000):                                          # synthesize an L3-band residual (L2 abstains)
        o = real.MODEL.emit(b, rng)
        same, sc = idc.L2.is_same(b, o)
        if not same and sc >= idc.L3_BAND_LO:
            obs = o
            break
    assert obs is not None, "could not synthesize an L3-band residual obs for the credit-path test"
    h = _pair_hash(idc.TARGET_TEXT[b], render_dump(obs))
    saved = dict(idc.L3CACHE)
    try:
        idc.L3CACHE.clear()
        idc.L3CACHE[h] = {"same": "true", "conf": 1.0, "model": "x"}   # a string: bool() would credit
        assert idc.id_l2l3(b, obs) is False, "string non-bool cache value credited — strict `is True` not enforced"
        idc.L3CACHE[h] = {"same": 1, "conf": 1.0}                      # numeric 1: `== True` would credit
        assert idc.id_l2l3(b, obs) is False, "numeric 1 credited — `is True` weakened to `== True`?"
        idc.L3CACHE[h] = {"same": True}                                # genuine bool, extra keys absent
        assert idc.id_l2l3(b, obs) is True, "a real bool True failed to credit"
    finally:
        idc.L3CACHE.clear()
        idc.L3CACHE.update(saved)
    return "idc.id_l2l3: string 'true' -> NO credit (strict is True); bool True -> credit (extra keys ignored)"


def test_l3_judge_fixed_point():
    """_judge_to_fixed_point converges to a true fixed point, and a single pass (max_iters=1) is not yet one."""
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
    """With seed_cache, seeded verdicts are preserved byte-exact and never re-judged; only new pairs are judged."""
    from benchmarks.eval import l3_eval
    orig = l3_eval.judge_cases
    try:
        l3_eval.judge_cases = lambda cases, *, model, host=None: {
            c["hash"]: {"same": True, "conf": 1.0, "model": model} for c in cases}
        full, _, _ = l3_eval._judge_to_fixed_point("BASE", None, seeds=3)        # learn the full pair set
        assert len(full) >= 2, "fixture: need >=2 residual pairs to split"
        # seed half with a distinguishable verdict; judge the rest with a new model id
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
    """gen_cases emits unique-hash cases spanning the full benchmark bug set."""
    from benchmarks.eval import l3_eval

    import benchmarks.real as real
    cases = l3_eval.gen_cases(real.MODEL)
    hashes = [c["hash"] for c in cases]
    assert len(hashes) == len(set(hashes)), "gen_cases emitted duplicate-hash cases"
    bugset = {c["target_bug"] for c in cases}
    assert bugset == set(real.BUGS), f"gen_cases must span {real.BUGS}, got {sorted(bugset)}"
    return f"gen_cases: {len(cases)} unique-hash cases spanning {''.join(sorted(bugset))}"


def test_l3_campaign_warns_on_nonconvergence():
    """_judge_campaign warns when the loop does not reach a fixed point and still persists the partial cache
    (written to a temp dir)."""
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
    """run_binary maps exit code == crash_rc to a crash and captures the dump text (subprocess faked)."""
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
    """The live runner with a mocked binary and a fake judge drives the binary, escalates to L3 and reproduces
    bug A at 0 false credit."""
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
    """Bug C (an assert: exit 255, site-only dump) reproduces with a mocked binary; pins _CRASH_RC['C'] and the
    assert-dump path."""
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
        rows, oracle, _ = live.run_live("C", seeds=2, binary=live.__file__,
                                               judge=lambda t, r, **k: {"same": True, "conf": 0.9})
        agg = live._agg(rows)
        assert agg["genuine"] == 1.0 and agg["false_credit"] == 0.0, agg     # exit 255 maps to a crash
        assert oracle.binary_runs > 0
    finally:
        subprocess.run = orig
    return f"off-the-shelf bug C (assert, exit 255): genuine {agg['genuine']:.2f} / fc {agg['false_credit']:.2f}"


def test_live_binary_agrees_with_truth():
    """With the real binaries present, each bug's live crash truth matches the committed truth table on its
    own harness, over every subset of its window. SKIPs when a binary is absent."""
    from benchmarks import live
    truth = multibug.TRUTH
    bugs = tuple(truth)                                       # validate every bug the committed truth file declares
    if not all(b in live._BINARIES and live._BINARIES[b].exists() for b in bugs):
        return "SKIP (a target binary is absent — build via src/emulation/zephyr-targets/scripts/*.sh)"
    mism = []
    for bug in bugs:
        W = multibug.WINDOW[bug]
        for mask in range(1 << W):                              # every subset of the window
            subset = frozenset(i for i in range(W) if mask & (1 << i))
            crashed, _ = live.run_binary(live._BINARIES[bug], bug, subset, live._CRASH_RC[bug])
            if crashed != (truth[bug].get(str(mask)) == bug):
                mism.append((bug, mask, crashed, truth[bug].get(str(mask))))
    assert not mism, f"live-binary vs truth-table disagreements: {mism}"
    return "live binary crash-truth == committed truth-multibug.json (all six bugs, every subset, on their own harness binaries)"


def test_scenario_dedup_families():
    """CrashDeduper never assigns a varied crash log to the wrong family (it abstains instead), also under
    severe report noise, and recalls at least 95%."""
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
            wrong += int(p is not None and p != b)             # a wrong family is a mis-route
            tot += 1
    assert wrong == 0, f"dedup must be FAIL-SAFE: {wrong} wrong-family false-merges (errors must abstain ∅, not mis-route)"
    assert ok / tot >= 0.95, f"dedup recall only {ok}/{tot}"
    # under severe report noise errors must still be abstentions, never a wrong family
    hard = DumpModel.from_logs(multibug.LOGS, bugs=scenario._BUGS,
                               params=DumpParams(p_garble=0.6, p_truncate=0.6, p_lose_top=0.5))
    wrong_hard = sum(1 for _ in range(40) for b in scenario._BUGS
                     if (p := dd.classify(hard.emit(b, rng))) is not None and p != b)
    assert wrong_hard == 0, f"under SEVERE noise dedup false-merged {wrong_hard} times (must only abstain)"
    return f"scenario dedup: {ok}/{tot} correct, 0 wrong-family (fail-safe: errors -> ∅, never false-merge; incl. severe noise)"


def test_scenario_trace_realism():
    """generate_campaign spans every bug; each trace carries its trigger pattern and a crash log, and
    look-alikes appear."""
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
    """The scenario on the real binaries with a fake judge: 0 false credit, dedup and genuine at least 0.75,
    PoCs mostly exact-minimal. SKIPs without the binaries."""
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
    """An always-'A' deduper routes only to A's binary: A traces stay genuine, the others do not, at 0 false
    credit. SKIPs without the binaries."""
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
    """The scenario with mocked binaries and a fake judge: genuine > 0, 0 false credit, every genuine row
    correctly grouped, and an always-'A' deduper routes only to A."""
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
        for r in rows:                                         # a genuine row was correctly grouped
            assert (not r.genuine) or r.predicted == r.bug, r
        # an always-A deduper routes only to A
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
    """run_multiseed with mocked binaries and a fake judge: 0 false credit on every seed, dedup min > 0.8,
    genuine mean >= 0.75 and every seed >= 0.65."""
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
    # thresholds tight enough to catch a regression (deterministic fixture)
    assert g["n"] == 4 and g["mean"] >= 0.75 and g["min"] >= 0.65, f"genuine must reproduce robustly every seed, got {g}"
    return (f"scenario multi-seed (mocked CI, 4 seeds): genuine mean {g['mean']:.2f} range [{g['min']:.2f},{g['max']:.2f}]; "
            f"dedup min {out['dedup_accuracy']['min']:.2f}; fc max {out['false_credit']['max']:.2f} (robust across seeds)")


def test_l3_provenance_self_documents_source():
    """The real and suppressor runs report source=cached_open_model with live_calls == 0 and escalations ==
    hits + rule fallbacks; B2 reports the deterministic rule."""
    r = run.run_real(5)
    s = run.run_suppressor(5, ablate=True)
    for tag, prov in (("real", r["l3_provenance"]), ("supp", s["l3_provenance"])):
        assert prov["source"] == "cached_open_model", f"{tag} source: {prov['source']}"
        assert prov["live_calls"] == 0, f"{tag} cached path must be LIVE-FREE, got {prov['live_calls']} live calls"
        assert prov["escalations"] == prov["cache_hits"] + prov["rule_no_fallback"], f"{tag}: {prov}"
        assert prov["model"] and prov["model"] != "none", f"{tag} model must come from the cache, got {prov['model']!r}"
    from benchmarks import resilience
    y = resilience.run(120, 1)                                   # B2 reports its own source
    assert y["l3_provenance"] == resilience.L3_PROVENANCE == {"source": "deterministic_rule", "model": None}, y["l3_provenance"]
    return (f"L3 source self-documented: real cached_open_model ({r['l3_provenance']['model']}, live=0, "
            f"hits={r['l3_provenance']['cache_hits']}); B2 resilience deterministic_rule (no LLM)")


def test_scenario_l3_provenance_live():
    """_summary aggregates the per-bug identity stats into l3_provenance (source=live_open_model), matching
    the per-trace deltas; without campaigns the field is omitted. SKIPs without the binaries."""
    from benchmarks import live, scenario
    if not all(live._BINARIES[b].exists() for b in scenario._BUGS):
        return "SKIP (a target binary is absent — build the 6 bugs' harnesses first)"
    rows, confusion, campaigns = scenario.run_scenario(8, judge=lambda t, r, **k: {"same": True, "conf": 0.9})
    s = scenario._summary(rows, confusion, campaigns, "fake-judge")
    lp = s["l3_provenance"]
    assert lp["source"] == "live_open_model" and lp["model"] == "fake-judge", lp
    assert lp["l3_live"] == sum(r.l3_live for r in rows), f"live total {lp['l3_live']} != per-trace sum {sum(r.l3_live for r in rows)}"
    assert lp["l3_live"] + lp["l3_memo"] + lp["l2_decided"] > 0, lp
    assert "l3_provenance" not in scenario._summary(rows, confusion), "campaigns=None must omit l3_provenance (back-compat)"
    return f"scenario L3 live provenance: {lp['l3_live']} live / {lp['l3_memo']} memo / {lp['l2_decided']} L2-decided"


def test_cached_and_synthetic_paths_never_call_live_judge():
    """The cached-real and synthetic modules do not import the live judge, and a real + suppressor + B2 run
    makes zero live judge calls (counted by wrapping rdd.l3.judge_ollama)."""
    import rdd.identity as _ident                               # rdd.identity binds judge_ollama at import,
    import rdd.l3 as _l3                                        # so patch both names
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
        resilience.run(120, 1)                                  # the B2 sweep
    finally:
        _l3.judge_ollama = _ident.judge_ollama = orig
    assert calls[0] == 0, f"cached-real + B2 synthetic paths must make ZERO live judge calls, made {calls[0]}"
    return "live-free pinned behaviourally: 0 live judge calls across cached-real + B2 synthetic; no judge_ollama import"


def test_causeswap_cause_swap_guard():
    """causeswap reproduces causeswap.json exactly; the guard takes the swap arm's false credit to 0 and
    leaves the genuine arms unchanged."""
    import json
    from benchmarks import causeswap
    d = causeswap.run(30)
    ref = json.loads((run._REF / "causeswap.json").read_text(encoding="utf-8"))
    assert d == ref, "causeswap must reproduce the committed reference exactly (incl. the provenance prose)"
    sw = d["arms"]["swap"]
    # guard off credits the C recipe as A; guard on demotes it
    assert sw["guard_off"]["false_credit"] > 0.5, f"guard OFF must false-credit the cause-swap, got {sw['guard_off']}"
    assert sw["guard_on"]["false_credit"] == 0.0, f"guard ON must DEMOTE the cause-swap to fc 0, got {sw['guard_on']}"
    assert sw["guard_off"]["genuine"] == 0.0 and sw["guard_on"]["genuine"] == 0.0, "the swap is never genuinely A"
    # demote-only: the correct-target arms are identical on and off
    for arm in ("genuine_A", "genuine_C"):
        a = d["arms"][arm]
        assert a["guard_on"]["genuine"] == a["guard_off"]["genuine"] > 0.5, f"{arm} genuine must be unchanged + high: {a}"
        assert a["guard_on"]["false_credit"] == 0.0, f"{arm} must not false-credit: {a}"
    return (f"Mode-2 guard demo (real dumps+identity, crash-only in-loop): cause-swap fc "
            f"{sw['guard_off']['false_credit']:.2f}->{sw['guard_on']['false_credit']:.2f}; "
            f"genuine_A/C unchanged {d['arms']['genuine_A']['guard_on']['genuine']:.2f}")


def test_l2_threshold_not_overfit():
    """l2_threshold_eval reproduces its reference; AUC >= 0.95 on every seed, the default 0.5 lies on a wide
    plateau in every seed and within 0.1 of the Youden optimum, and the L3 band risks no same-bug miss."""
    import json

    from benchmarks.eval import l2_threshold_eval as lt
    d = lt.evaluate()
    ref = json.loads((lt._DATA / "reference" / "l2_threshold_eval.json").read_text(encoding="utf-8"))
    assert abs(d["auc"] - ref["auc"]) < 1e-9 and abs(d["youden_threshold"] - ref["youden_threshold"]) < 1e-9, "must reproduce committed"
    assert d["sweep"] == ref["sweep"] and d["plateau"] == ref["plateau"] and d["band"] == ref["band"] and d["stability"] == ref["stability"], "sweep/plateau/band/stability must reproduce committed"
    assert d["auc"] >= 0.95 and d["stability"]["auc_min"] >= 0.95, f"same/cross must be near-separable + STABLE across seeds, got {d['auc']:.3f}/{d['stability']}"
    assert d["stability"]["default_in_plateau_all_seeds"] is True, f"the default 0.5 must be on the plateau in EVERY seed, got {d['stability']}"
    lo_c, hi_c = d["stability"]["plateau_common"]               # the band that is a plateau in every seed
    assert lo_c <= d["default_threshold"] <= hi_c and (hi_c - lo_c) >= 0.2, f"the cross-seed COMMON plateau must contain 0.5 + be WIDE, got {d['stability']['plateau_common']}"
    assert abs(d["youden_threshold"] - d["default_threshold"]) <= 0.1, f"default must be ~data-optimal, got Youden {d['youden_threshold']:.3f}"
    lo, hi = d["plateau"]
    assert lo <= d["default_threshold"] <= hi and (hi - lo) >= 0.2, f"default 0.5 must sit inside a WIDE flat plateau, got {d['plateau']}"
    assert d["sweep"]["0.50"]["balanced"] >= d["best_balanced"] - 0.02, "the default 0.5 must be ~flat (not a fragile peak)"
    assert d["same"]["mean"] - d["cross"]["mean"] >= 0.5, f"same vs cross must separate: {d['same']['mean']:.2f} vs {d['cross']['mean']:.2f}"
    # the L3 band sits well below the same-bug score floor
    assert d["band"]["same_at_risk_below_band"] == 0.0, f"the L3 band must risk no same-bug miss, got {d['band']}"
    assert d["band"]["max_safe_band_same_min"] >= d["band"]["band"] + 0.2, f"the band must be far below the safe ceiling, got {d['band']}"
    return (f"L2 threshold NOT overfit (A--F, modelled noise): AUC {d['auc']:.3f} (stable {d['stability']['auc_min']:.3f}-{d['stability']['auc_max']:.3f}); "
            f"default 0.5 ~ Youden {d['youden_threshold']:.3f}; flat plateau {d['plateau']}; band 0.05 safe<{d['band']['max_safe_band_same_min']:.2f}")


def test_b1_headtohead_coherence():
    """B1's frozen replay reproduces headtohead.json with 0 live calls. SKIPs without the binaries."""
    from benchmarks import headtohead, live
    from benchmarks.scenario import _BUGS
    if not all(live._BINARIES[b].exists() for b in _BUGS):
        return "SKIP (host-native binaries absent — build via src/emulation/zephyr-targets/)"
    assert headtohead.coherence(42, 8), "B1 frozen replay must reproduce the committed reference (delta=0, 0 live calls)"
    return "B1 head-to-head: frozen replay reproduces the committed reference (every leaf; 0 live calls)"


def test_b2_resilience_smoke():
    """B2 runs, is deterministic at a small size, exposes the full metric set for every arm and regime, keeps
    the tool's false credit within 0.02 in every regime, and reports no model."""
    from benchmarks import resilience, scoring
    a = resilience.run(150, 2)
    b = resilience.run(150, 2)
    assert scoring.leaf_diffs(scoring.clean_nan(b), scoring.clean_nan(a)) == [], "B2 must be deterministic (re-run identical)"
    regs = a["regimes"]
    assert set(regs) == {"standard", "high_card", "suppressor", "far_trigger", "deep_noise", "wide_window", "OVERALL"}, f"B2 regimes: {set(regs)}"
    assert set(regs["standard"]) == set(resilience.ARMS) == {"baseline", "baseline_confirm", "tool"}, "B2 arms"
    assert set(regs["standard"]["tool"]) == set(resilience.METRICS) == {
        "genuine", "false_credit", "exact_minimal", "mean_size_gap", "reads"}, "B2 must report B1's full metric set"
    g = lambda reg, arm, k="genuine": regs[reg][arm][k][0]       # CI mean
    for reg in regs:                                             # the alpha bound is a property of the tool
        assert g(reg, "tool", "false_credit") <= 0.02, f"RDD false_credit must be ~0 in {reg}, got {g(reg, 'tool', 'false_credit')}"
    assert a["l3_provenance"] == {"source": "deterministic_rule", "model": None}, "B2 is model-free"
    return (f"B2 smoke (150x2, deterministic, 3 arms x 6 regimes): RDD fc<=0.02 every regime; OVERALL genuine "
            f"RDD {g('OVERALL', 'tool'):.2f} / baseline {g('OVERALL', 'baseline'):.2f} / +1 confirm {g('OVERALL', 'baseline_confirm'):.2f}")


def test_baseline_false_credit_is_the_phantom_rate():
    """The baseline's false credit is the phantom-crash rate: with the phantom rate zeroed it is exactly 0 and
    recall does not fall; one confirming re-run removes most of it."""
    from dataclasses import replace
    from benchmarks import scoring, synthetic
    from emulation.dump import DumpModel
    from emulation.synthetic import LargeOracle, base_dump, sev_channel
    bugs = synthetic.gen_population(80, 7)
    model = DumpModel(base={b.bid: base_dump(b) for b in bugs})
    saved = dict(synthetic._TARGET_EXACT)
    synthetic._TARGET_EXACT.clear()
    synthetic._TARGET_EXACT.update({b.bid: emulation_baseline.exact_crash_id(model.clean_obs(b.bid)) for b in bugs})
    try:
        def fc(params_of, **kw):
            rows = []
            for b in bugs:
                o = LargeOracle(synthetic.id_exact, model, params_of(b))
                rows += scoring.run_baseline_campaign(o, [b], random.Random(f"{b.bid}:0"), **kw)
            return sum(r["false_credit"] for r in rows) / len(rows), sum(r["true_reproduced"] for r in rows) / len(rows)
        on = fc(lambda b: sev_channel(b.sev))
        off = fc(lambda b: replace(sev_channel(b.sev), p_fp_good=0.0, p_fp_bad=0.0))
        conf = fc(lambda b: sev_channel(b.sev), confirm=1)
        assert off[0] == 0.0, f"with no phantom crashes the baseline cannot false-credit, got {off[0]}"
        assert off[1] >= on[1], "removing phantoms must not lower the baseline's recall"
        assert conf[0] < on[0] / 4, f"one confirming re-run must remove most false credit: {on[0]:.3f} -> {conf[0]:.3f}"
    finally:
        synthetic._TARGET_EXACT.clear()
        synthetic._TARGET_EXACT.update(saved)
    return f"phantom rate on: fc {on[0]:.3f}; off: fc {off[0]:.3f} (genuine {on[1]:.2f} -> {off[1]:.2f}); +1 confirm: fc {conf[0]:.3f}"


def test_b3_levers_coherence():
    """B3's frozen replay reproduces levers.json with 0 live calls. SKIPs without the binaries."""
    from benchmarks import levers, live
    from benchmarks.scenario import _BUGS
    if not all(live._BINARIES[b].exists() for b in _BUGS):
        return "SKIP (host-native binaries absent — build via src/emulation/zephyr-targets/)"
    assert levers.coherence(8), "B3 frozen replay must reproduce the committed reference (delta=0, 0 live calls)"
    return "B3 lever decomposition: frozen replay reproduces the committed reference (every leaf; 0 live calls)"


def test_leaf_diffs_comparator():
    """scoring.leaf_diffs: tol-numeric, null stays null, bool/str exact, bool does not match int, a missing
    key is a diff, and skip_top applies at the top level only."""
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
    # skip_top is top-level only: a nested l3_live is still gated
    assert ld({"l3_live": 9, "x": 1.0}, {"l3_live": 0, "x": 1.0}, skip_top=("l3_live",)) == [], "top-level l3_live must be skipped"
    assert ld({"r": {"l3_live": 9}}, {"r": {"l3_live": 0}}, skip_top=("l3_live",)) == [("r.l3_live", 9, 0)], "a NESTED l3_live must still be gated"
    return "leaf_diffs: tol-numeric + null + bool/str exact + bool!=int + missing-key + skip_top TOP-LEVEL-only"


def test_b1_reference_invariants():
    """headtohead.json is well-formed: both arms carry the metric set and share the dedup accuracy, and the
    tool's false credit is within its alpha bound."""
    import json
    ref = json.loads((run._REF / "headtohead.json").read_text(encoding="utf-8"))
    ab, rd, sp = ref["airbug"], ref["rdd"], ref["suppressor"]
    metrics = {"genuine", "genuine_routed", "false_credit", "dedup_accuracy", "exact_minimal", "mean_size_gap", "reads"}
    assert metrics <= set(ab) and metrics <= set(rd), f"B1 arms must carry B1's metric set, got {set(ab)} / {set(rd)}"
    m = lambda arm, k: arm[k]["mean"]
    assert m(rd, "false_credit") <= 0.02, f"RDD false_credit must be within its alpha bound, got {m(rd,'false_credit')}"
    assert m(rd, "dedup_accuracy") == m(ab, "dedup_accuracy"), "both arms share ONE dedup front-end (identical accuracy)"
    assert sp["rdd"]["false_credit"] <= 0.02, f"suppressor: RDD false credit within bound, got {sp['rdd']}"
    return (f"B1 reference well-formed: RDD {m(rd,'genuine'):.3f}/{m(rd,'false_credit'):.3f} vs AirBugCatcher "
            f"{m(ab,'genuine'):.3f}/{m(ab,'false_credit'):.3f}; reads {m(rd,'reads'):.0f} vs {m(ab,'reads'):.0f}")


def test_b3_lever_consistency():
    """levers.json is internally consistent: the lever deltas equal the differences of the committed arm
    numbers, the ddmin-only ablation scores 0 on the suppressor, and the three pipeline arms' false credit
    is within 0.02. Model- and binary-free."""
    import json
    ref = json.loads((run._REF / "levers.json").read_text(encoding="utf-8"))
    real, sup, lev = ref["real"], ref["suppressor"], ref["levers"]
    arms = ["baseline", "oracle", "ablation", "tool"]           # the four-arm ladder
    assert list(real) == arms and list(sup) == arms and list(lev["oracle_fc_invariance"]) == arms, \
        f"B3 must carry the 4-arm ladder baseline/oracle/ablation/tool, got real={list(real)}"
    close = lambda a, b: abs(a - b) <= 1e-9
    # each delta must equal the difference of the arms it is computed from
    idd = real["ablation"]["genuine"]["mean"] - real["oracle"]["genuine"]["mean"]
    assert close(idd, lev["identity_genuine_real"]), f"identity delta desynced: arms={idd} vs levers={lev['identity_genuine_real']}"
    msup = sup["tool"]["genuine"] - sup["ablation"]["genuine"]
    assert close(msup, lev["minimiser_genuine_suppressor"]), f"minimiser delta desynced: arms={msup} vs levers={lev['minimiser_genuine_suppressor']}"
    for a in arms:
        assert close(lev["oracle_fc_invariance"][a], real[a]["false_credit"]["mean"]), f"oracle_fc_invariance[{a}] desynced from the arm fc"
    # bare ddmin returns [] on a suppressed full window
    assert sup["ablation"]["genuine"] == 0.0, f"bare ddmin must BAIL (0) on the suppressor, got {sup['ablation']['genuine']}"
    fci = lev["oracle_fc_invariance"]
    assert max(fci["oracle"], fci["ablation"], fci["tool"]) <= 0.02, f"the 3 pipeline arms must stay within the alpha bound, got {fci}"
    return (f"B3 levers consistent with their arms: identity {lev['identity_genuine_real']:+.3f}, minimiser "
            f"{lev['minimiser_genuine_suppressor']:+.3f} (suppressor tool {sup['tool']['genuine']:.2f} vs ablation "
            f"{sup['ablation']['genuine']:.2f}); pipeline fc <= 0.02")


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
         test_baseline_false_credit_is_the_phantom_rate,
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
        except Exception as e:
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    tail = f", {skipped} skipped" if skipped else ""
    print(f"\n{'ALL PASS' if not failed else f'{failed} FAILED'} ({len(TESTS) - failed - skipped}/{len(TESTS) - skipped} run{tail})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
