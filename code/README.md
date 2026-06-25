# RDD — Robust Delta-Debugging

The reference implementation and benchmark suite behind the report
[_Stabilising the Oracle: Robust Delta-Debugging for Reproducing Wireless IoT
Fuzzing Bugs_](../report/) (LaTeX source; the PDF is built by CI).

## What it does

When you fuzz the wireless stack of a smart-home device you get **crashes**, but what
a developer needs is a **Proof-of-Concept**: the _shortest_ packet sequence that still
triggers the bug. Shrinking a crash to that minimal PoC is the job of **delta
debugging** (`ddmin`) — but on a noisy wireless target the "does it still crash?"
oracle gives inconsistent answers, and `ddmin`, which assumes a stable answer, breaks.
**RDD makes the answer stable in software** so classical minimisation works again:

- a **truncated SPRT** turns many noisy per-attempt verdicts into one accountable
  decision with a bounded error rate;
- a **two-tier crash-identity oracle** — a fast deterministic matcher that escalates
  only its hard cases to a small open LLM judge — recognises the same bug through a
  garbled dump;
- a **non-monotone-robust minimiser** drives `ddmin` to a minimal PoC and credits it
  only after an independent re-confirmation.

> **The L3 LLM judge is a recall aid, not the soundness mechanism.** It is deliberately
> biased toward "same" — its job is to _recover_ a same-bug reproduction L2 abstained on
> through a garbled dump, not to discriminate — so the committed numbers reproduce even
> with it forced to "same". Zero false credit comes from the minimiser's independent
> re-confirmation that the PoC _provably crashes the right bug_, never from the judge.

## Install

Requires **Python 3.11+**. From `code/`:

```bash
python3 -m venv .venv && source .venv/bin/activate   # recommended; required on PEP-668 distros (Ubuntu 24.04+, Debian 12+)
python -m pip install -e .
```

The only third-party dependencies are `numpy` and `drain3`; everything below runs
**offline, on CPU**.

## Run it

```bash
PYTHONHASHSEED=0 python -m rdd.tests.test_rdd                # the tool's 18 invariants (~seconds)
PYTHONHASHSEED=0 python -m benchmarks.tests.test_benchmarks  # the suite self-test (~1 min)
PYTHONHASHSEED=0 python -m benchmarks.run coherence          # reproduce the committed numbers (delta = 0.000)
```

`PYTHONHASHSEED=0` pins determinism (the tests need no `pytest` — a tiny runner prints
`ALL PASS` / `SKIP` / `FAIL`). `coherence` re-runs the benchmarks from scratch and
checks the fresh numbers match the committed references exactly; if it prints
`COHERENT`, the report's results reproduce on your machine.

The three headline benchmarks — `PYTHONHASHSEED=0 python -m benchmarks.run <cmd>`:

| Command      | What it measures                                                    | RDD vs. AirBugCatcher  |
| ------------ | ------------------------------------------------------------------- | ---------------------- |
| `b1`         | real `native_sim` head-to-head through the full pipeline (live L3)  | 0.863 vs. 0.759 genuine |
| `b2`         | 75k-campaign, 6-regime synthetic resilience sweep (model-free)      | 0.916 vs. 0.282 genuine |
| `b3`         | real-target lever decomposition (oracle / identity / minimiser)     | isolates each lever     |
| `coherence`  | the model-free reproducibility gate: the real anchor + B2           | delta = 0.000           |

`b2` and `coherence` are fully model-free, so they run on a bare clone. `b1`/`b3` need
the real Zephyr binaries (built below) — with `--frozen` they replay from the committed
L3 cache; without the binaries they exit with a build pointer. The suite self-test stays
green on a fresh clone: its binary-gated B1/B3 checks SKIP cleanly when those are absent.

## Reproduce the live Zephyr campaigns

`b1`, `b3`, the end-to-end `scenario`, and the off-the-shelf `benchmarks.live` drive real, vulnerable Zephyr
Bluetooth-controller binaries on `native_sim`. **Build them** (needs Docker) with the
recipe in [`src/emulation/zephyr-targets/`](./src/emulation/zephyr-targets/). The binaries are **32-bit**
(`native_sim`), so on a 64-bit host install the i386 runtime once before running them:

```bash
sudo dpkg --add-architecture i386 && sudo apt-get update && sudo apt-get install -y libc6:i386   # Debian/Ubuntu
sudo dnf install -y glibc.i686                                                                   # Fedora/RHEL
```

Then replay offline (the frozen L3 cache is keyed on the build-reproducible controller frames, so the replay
reproduces on **any** machine) or run live against an [Ollama](https://ollama.com) `llama3.1:8b` judge:

```bash
PYTHONHASHSEED=0 python -m benchmarks.run b1 --frozen        # offline replay, no model
PYTHONHASHSEED=0 python -m benchmarks.run b1 --seeds 8       # live (needs Ollama)
PYTHONHASHSEED=0 python -m benchmarks.scenario --traces 40   # the full fuzz -> dedup -> RDD -> PoC run
PYTHONHASHSEED=0 python -m benchmarks.live --bug A --seeds 5 # the RDD tool off-the-shelf, one live bug
```

## Layout

```text
code/
├── pyproject.toml      # packaging + the two dependencies
└── src/
    ├── rdd/            # THE TOOL — self-contained: pipeline, SPRT oracle, L2/L3 identity, robust ddmin
    ├── emulation/      # THE HARDWARE-FREE TEST BED — device oracles + the channel/dump noise models
    │   └── zephyr-targets/   #   Docker build recipe for the real native_sim bug binaries
    └── benchmarks/     # THE SUITE — AirBugCatcher baseline vs. the tool + the reproducibility gate
```

The import graph is one-way **`benchmarks` → `emulation` → `rdd`**: the tool imports
neither of the others; the test bed depends only on the tool's interfaces and injects
its device oracles into it. Swap `emulation` for a real radio + device and the tool is
unchanged.

## Reproducibility

Every benchmark is deterministic under `PYTHONHASHSEED=0`. The crash-identity LLM judge
(L3) runs only on the real-bug anchor and the live campaigns; its verdicts are
**committed to a cache** (`src/benchmarks/data/llm_cache/`), so every reported number
reproduces with **no LLM, GPU, or network** — a cache hit returns the stored verdict, a
miss falls back to a conservative "different bug". Tests that need the compiled binaries
(under the gitignored `upstream/`) skip cleanly when absent, so a fresh clone is always
green.

## License & citation

Released under the [MIT License](../LICENSE); to cite the project see
[`../CITATION.cff`](../CITATION.cff).
