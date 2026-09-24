# RDD — Robust Delta-Debugging

The reference implementation and benchmark suite behind the report
[_Stabilising the Oracle: Robust Delta-Debugging for Reproducing Wireless IoT
Fuzzing Bugs_](../report/) (LaTeX source; CI builds the PDF).

## What it does

Fuzzing the wireless stack of a smart-home device yields crashes; a developer needs a
proof of concept, the shortest packet sequence that still triggers the bug. Delta
debugging (`ddmin`) finds one, but it assumes a stable "does it still crash?" answer, and
a noisy wireless target does not give one. RDD makes the answer stable enough in software:

- a **truncated SPRT** turns repeated noisy attempts into one decision with a bounded
  error rate;
- a **two-tier crash-identity oracle**, a deterministic matcher that escalates only its
  uncertain cases to a small open language model, recognises the same bug through a
  garbled dump;
- a **suppressor-robust minimiser** drives `ddmin` from a crashing starting window and
  credits a recipe only after an independent re-confirmation.

The judge (L3) is a recall aid, not the soundness mechanism: on the pairs it is asked
about it says "same" almost always, so cross-bug discrimination rests on the
deterministic matcher, and the false-credit bound rests on the SPRT re-confirmation.

## Install

Python 3.11 or newer. From `code/`:

```bash
python3 -m venv .venv && source .venv/bin/activate   # required on PEP 668 distributions
python -m pip install -e .
```

The only dependencies are `numpy` and `drain3`. Everything below runs offline, on CPU.

## Run

```bash
PYTHONHASHSEED=0 python -m rdd.tests.test_rdd                # the tool's 18 invariants (seconds)
PYTHONHASHSEED=0 python -m benchmarks.tests.test_benchmarks  # the suite self-test (~15 s without binaries)
PYTHONHASHSEED=0 python -m benchmarks.run coherence          # reproduce the committed numbers (about 4 min; 7 on a GitHub runner)
PYTHONHASHSEED=0 python -m benchmarks.run sensitivity        # the same anchor with the noise models switched off
```

`PYTHONHASHSEED=0` pins the synthetic population. The tests need no `pytest`; a small
runner prints `ALL PASS`, `SKIP` or `FAIL`. `coherence` re-runs the model-free
benchmarks and checks them against `src/benchmarks/data/reference/`: the real-bug anchor
within ±0.02 (it reproduces exactly, delta 0.000) and the synthetic sweep leaf for leaf.

## Benchmarks

`PYTHONHASHSEED=0 python -m benchmarks.run <command>`:

| Command       | What it measures                                                       | Genuine recovery, RDD vs. baseline |
| ------------- | ---------------------------------------------------------------------- | ---------------------------------- |
| `b1`          | six real Zephyr bugs through the full pipeline (frozen judge cache)    | 0.848 vs. 0.759; false credit 0.000 vs. 0.137 |
| `b2`          | 75,000-campaign, six-regime synthetic sweep (model-free)               | 0.824 vs. 0.266; false credit 0.000 vs. 0.632 |
| `b3`          | real-bug lever decomposition (oracle, identity, minimiser)             | one arm per lever                  |
| `coherence`   | the model-free reproducibility gate (real anchor + B2)                 | delta 0.000                        |
| `sensitivity` | the real anchor with report variation and phantom crashes switched off | see below                          |
| `freeze`      | regenerate the anchor's committed reference                            | writes `anchor.json`               |

Every arm is scored by the same rule: a reproduction is genuine only if the arm credited
its recipe and the recipe crashes the target with the channel off; it is a false credit
if the arm credited a recipe that does not. The baseline is a re-implementation of
AirBugCatcher's reproduction strategy (bounded enumeration up to three packets, one
attempt per candidate, exact signature match), not the original tool. A third arm,
`baseline_confirm`, is the confirmation control: the same baseline that credits a
candidate only after one confirming re-run.

The comparison is a mechanism study under an assumed noise model, and the `sensitivity`
command shows how much of it is the model. On the six real bugs (30 runs each):

| Noise model            | Baseline          | Baseline + 1 confirm | RDD               |
| ---------------------- | ----------------- | -------------------- | ----------------- |
| as committed           | 0.867 / 0.089 / 10 | 0.761 / 0.006 / 19   | 0.933 / 0.000 / 49 |
| report variation off   | 0.911 / 0.067 / 9  | 0.911 / 0.000 / 17   | 0.928 / 0.000 / 50 |
| phantom crashes off    | 0.933 / 0.000 / 11 | 0.750 / 0.000 / 19   | 0.933 / 0.000 / 48 |
| both off               | 0.978 / 0.000 / 10 | 0.933 / 0.000 / 17   | 0.928 / 0.000 / 47 |

(cells: genuine / false credit / device reads per campaign). The baseline's false credit
comes entirely from the modelled phantom crashes, which carry the target's own crash
dump; RDD's advantage in recall comes from the modelled report variation, which defeats
exact signature matching. Without either, the baseline wins at one fifth of the reads.

`b2` and `coherence` are model-free and run on a bare clone. `b1` and `b3` drive the real
Zephyr binaries (built below); `--frozen` replays them from the committed judge cache,
`--refreeze` writes the reference from that replay, and `--freeze` re-runs them against a
live judge and rewrites cache and reference. Without the binaries they stop with a
`FileNotFoundError` naming the build recipe, and the self-test skips its binary-gated checks.

## The real Zephyr targets

`b1`, `b3`, `benchmarks.scenario` and `benchmarks.live` execute real, vulnerable Zephyr
Bluetooth-controller binaries built for Zephyr's host-native `unit_testing` board (a
32-bit ztest executable, no radio). Build them with Docker using the recipe in
[`src/emulation/zephyr-targets/`](./src/emulation/zephyr-targets/); each script also
verifies its binary's channel-off truth table. On a 64-bit host install the i386 runtime
once (`libc6:i386` on Debian/Ubuntu, `glibc.i686` on Fedora, `lib32-glibc` on Arch). `HARNESS_WS`
relocates the build workspace for both the scripts and the Python side.

```bash
PYTHONHASHSEED=0 python -m benchmarks.run b1 --frozen        # offline replay, no model
PYTHONHASHSEED=0 python -m benchmarks.run b1 --seeds 8       # live judge (needs Ollama, llama3.1:8b)
PYTHONHASHSEED=0 python -m benchmarks.scenario --traces 40   # fuzz trace -> dedup -> RDD -> PoC, live judge
PYTHONHASHSEED=0 python -m benchmarks.live --bug A --seeds 5 # the tool off the shelf on one bug, live judge
```

## Layout

```text
code/
├── pyproject.toml      # packaging + the two dependencies
└── src/
    ├── rdd/            # the tool: pipeline, SPRT oracle, L2/L3 identity, robust ddmin
    ├── emulation/      # the hardware-free test bed: device oracles, channel and dump noise models
    │   └── zephyr-targets/   #   Docker build recipe for the real bug binaries
    └── benchmarks/     # the suite: baseline, runners, scoring, committed references
```

The import graph is one-way, `benchmarks` → `emulation` → `rdd`: the tool imports
neither of the others, and the test bed injects its device oracles into it.

## Reproducibility

Every benchmark is deterministic under `PYTHONHASHSEED=0`. The judge runs only on the
real bugs; its verdicts are committed (`src/benchmarks/data/llm_cache/`), so every number
above reproduces with no model, GPU or network. A cache miss falls back to a
conservative "different bug", and the coherence gate checks that no miss occurred.

## Known limitations

- The channel is a Gilbert–Elliott process on a deterministic host binary, and every
  RDD run resets the session before each attempt, which makes attempts independent; the
  effect of correlated attempts on the sequential test is not evaluated.
- A phantom crash (a non-reproducing subset reported as crashing, 2–7% per attempt) is
  modelled as carrying the target's own dump; the miss rate is calibrated to the FlakeFlagger
  rerun corpus (Alshammari et al., ICSE 2021), the phantom rates are the authors'.
  The baseline's false credit is a direct consequence of this assumption.
- Crash-report variation is modelled with assumed rates (truncation 0.35, top-frame
  loss 0.20, frame churn 0.15, log interleaving 0.40, garbling 0.08). The identity
  layer's gain over exact matching is a function of these rates.
- The committed Bug-B dump is an abbreviated transcript with no bracketed return
  addresses, so it yields no stack frames; exact matching is stronger on B. The
  suppressor harness prints no backtrace, so its oracle re-uses Bug A's dump.
- No experiment presents a different bug's dump to the in-loop identity oracle, so the
  risk of crediting a recipe that reproduces a different bug is unmeasured.
- Roughly a third of the synthetic bugs have minimal recipes larger than the baseline's
  three-packet cap and cannot be recovered by it by construction.
- Runs with the live judge are not bit-reproducible. In the September 2026 audit `b1`
  and `b3` were replayed from their caches on rebuilt binaries; `benchmarks.live` (bug A,
  two runs: both genuine, one live judgment) and `benchmarks.scenario --traces 40` (one run:
  dedup 0.875, genuine 0.850, no false credit, 29 live judgments) were exercised against a
  local `llama3.1:8b`. Those live figures are indicative, not references.

## License and citation

MIT, see [`../LICENSE`](../LICENSE). To cite the project use [`../CITATION.cff`](../CITATION.cff).
