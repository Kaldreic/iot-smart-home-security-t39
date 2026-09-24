<div align="center">

# IoT and Smart Home Security — T39

**Data and Network Security · MSc Cybersecurity · Sapienza University of Rome**

A deep-dive into Wi-Fi sensing defences and automated IoT bug reproduction, with a look at where the field could go next.

[![Build](https://github.com/Kaldreic/iot-smart-home-security-t39/actions/workflows/build.yml/badge.svg)](https://github.com/Kaldreic/iot-smart-home-security-t39/actions/workflows/build.yml)
[![Slides](https://img.shields.io/badge/slides-live-blue)](https://kaldreic.github.io/iot-smart-home-security-t39/)
[![Report](https://img.shields.io/badge/report-live-blue)](https://kaldreic.github.io/iot-smart-home-security-t39/report.pdf)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Status: complete](https://img.shields.io/badge/status-complete-success)](#project-status)

</div>

## Project status

**Complete.** The coursework was delivered and graded in June 2026 (release `v1.0.0`); the repository is kept as an
archival record and is not under active development. A final audit in September 2026 (release `v1.0.1`) re-verified
every link and reference, rebuilt all three deliverables from a clean clone, and confirmed that the benchmark suite
reproduces the report's numbers exactly.

## Deliverables

| Artifact              | Source                            | Build output                                                                                  |
| --------------------- | --------------------------------- | --------------------------------------------------------------------------------------------- |
| Presentation          | [`presentation/`](./presentation) | `presentation/dist/` · [live](https://kaldreic.github.io/iot-smart-home-security-t39/)        |
| Academic report       | [`report/`](./report)             | `report/main.pdf` · [live](https://kaldreic.github.io/iot-smart-home-security-t39/report.pdf) |
| RDD tool + benchmarks | [`code/`](./code)                 | `pip install -e code/`                                                                        |

## Source papers

1. **[WiShield: Fine-grained Countermeasure Against Malicious Wi-Fi Sensing in Smart Home](https://www.yangzhice.com/docforweb/WiShield/WiShield_ACSAC.pdf)** — Y. Yan and Z. Yang, ACSAC 2024 · [DOI](https://doi.org/10.1109/ACSAC63791.2024.00057)
2. **[AirBugCatcher: Automated Wireless Reproduction of IoT Bugs](https://asset-group.github.io/papers/airbugcatcher.pdf)** — G. Hua, M. E. Garbelini and S. Chattopadhyay, ACSAC 2024 · [DOI](https://doi.org/10.1109/ACSAC63791.2024.00058)

## Authors

**Group 19**

- **Aldo Ristori** (2086552) — [@Kaldreic](https://github.com/Kaldreic)
- **Nicole Sperandini** (2264712) — [@Nicole03Spera](https://github.com/Nicole03Spera)

## Quickstart

**Prerequisites** — you only need the ones for the deliverable you want to run:

- **git** — clone the repository
- **[Node.js](https://nodejs.org/) 22+** and **[pnpm](https://pnpm.io/installation)** — slides (`corepack enable` activates pnpm)
- **make** and a **[TeX Live](https://www.tug.org/texlive/)** install with **latexmk** — report
- **[Python](https://www.python.org/) 3.11+** — tool and benchmarks

Each block below is an independent deliverable — feel free to run whichever you need.

```bash
git clone https://github.com/Kaldreic/iot-smart-home-security-t39
cd iot-smart-home-security-t39

# Slides — live dev server at http://localhost:3030
pnpm install && pnpm slides:dev

# Report — builds report/main.pdf
make -C report

# Tool + benchmarks — reproduce the report's numbers
python3 -m venv .venv && source .venv/bin/activate
pip install -e code/
PYTHONHASHSEED=0 python -m benchmarks.run coherence
```

The [`presentation/`](./presentation) and [`code/`](./code) deliverables each have their own README with full detail.

## Repository layout

```text
.
├── .github/        # CI: build + test checks, live slides + report deploy
├── presentation/   # Slidev source — the delivered talk
├── report/         # LaTeX source (IEEEtran) — the academic report
└── code/           # the RDD tool + benchmark suite (pip-installable)
    ├── src/rdd/        # robust delta-debugging, SPRT-stabilised oracle
    ├── src/emulation/  # hardware-free test bed + the Zephyr target build recipe
    └── src/benchmarks/ # AirBugCatcher baseline + reproducibility gate
```

## License

Released under the [MIT License](./LICENSE) — code, report, and slides alike.

To cite this work, use the metadata in [`CITATION.cff`](./CITATION.cff) (GitHub's _Cite this repository_ button).

## Acknowledgements

Built with [Slidev](https://sli.dev) and LaTeX (IEEEtran), with development assistance from [Claude Code](https://claude.com/claude-code). Thanks to Prof. [Dorjan Hitaj](https://sites.google.com/view/dorjanhitaj/) for the assignment and guidance.
