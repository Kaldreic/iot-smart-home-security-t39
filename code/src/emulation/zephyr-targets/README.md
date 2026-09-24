# Zephyr target build recipe

The *live* benchmarks -- B1 (`benchmarks.headtohead`), B3 (`benchmarks.levers`), the end-to-end
`benchmarks.scenario` and the off-the-shelf `benchmarks.live` -- run against real, vulnerable Zephyr
Bluetooth-controller binaries. Those binaries are **not committed**; they build into the gitignored
`code/upstream/zephyr-cve/build-*/`. These scripts are the recipe that produces them.

Each `scripts/build-*.sh` is self-contained and idempotent: inside the pinned `zephyr-build` Docker image it
shallow-clones Zephyr at a fixed vulnerable commit, restores the vulnerable controller guard, applies its
harness patch from `patches/`, and `cmake`/`ninja`-builds a `testbinary`.

| Script | Builds (`upstream/zephyr-cve/…`) | Bug(s) |
| --- | --- | --- |
| `build-multibug.sh` | `build-multibug/` | A (CVE-2024-4785, SIGFPE) + C |
| `build-bugB.sh` | `build-cis/` | B |
| `build-bugD.sh` | `build-phy/` | D |
| `build-bugE.sh` | `build-dle/` | E |
| `build-bugF.sh` | `build-cisc/` | F |
| `build-lengthreq.sh` | `../zephyr-cve-lengthreq/build-lengthreq/` (its own workspace) | non-monotone suppressor harness |

**Requires Docker.** The first build pulls the pinned `zephyr-build` image (~31 GB), shallow-clones Zephyr
(~1 GB) and downloads the Zephyr SDK (~42 MB) before building, so budget disk and time; run e.g.
`bash scripts/build-multibug.sh`. You only need these to re-run the live benchmarks from scratch -- the
offline reproduce gate (`python -m benchmarks.run coherence`) and every committed report number need none
of it. Every script honours `HARNESS_WS=<dir>` to relocate its workspace; `build-lengthreq.sh` insists on a
`*-lengthreq` directory so it never dirties the shared clone.

The built `testbinary` is a **32-bit i386** host executable (Zephyr's `unit_testing` board). To *run* it on a
64-bit host (the `b1`/`b3`/`scenario`/`live` benchmarks), install the 32-bit runtime once:
`sudo dpkg --add-architecture i386 && sudo apt-get update && sudo apt-get install -y libc6:i386`
(Debian/Ubuntu) or `sudo dnf install -y glibc.i686` (Fedora/RHEL). Without it the binary fails to exec with
a misleading `FileNotFoundError` (the ELF interpreter `/lib/ld-linux.so.2` is absent).

_Attribution: the `patches/` modify Zephyr controller test sources ([zephyrproject-rtos/zephyr](https://github.com/zephyrproject-rtos/zephyr), Apache-2.0) at the pinned vulnerable commit; those modifications ship under this repo's MIT licence, and the underlying Zephyr code remains Apache-2.0._
