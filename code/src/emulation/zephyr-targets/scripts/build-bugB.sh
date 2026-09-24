#!/usr/bin/env bash
# Bug B — build the subset-selectable CIS divide-by-zero oracle binary on the vulnerable Zephyr LL
# controller and verify its channel-off exhaustive sweep + true 1-minimal.
#
# The harness (patches/bugB-cis-window.patch) adds one ZTEST (test_bug_b) to the ctrl_cis_create suite;
# a no-op unless selected by env HARNESS_BUG=B (whole suite, no per-test CLI filter, selection by getenv --
# the existing PROBE_ID pattern). HARNESS_SUBSET is a bitmask over the LL-PDU window, for a channel-off
# exhaustive sweep.
#
#   HARNESS_BUG=B  test_bug_b: confirmed CIS divide-by-zero. A single-packet minimal (like Bug A). 8-bit
#             trigger-last window: bits0..3 = transparent (droppable) drained local LE-Pings, bit7 (0x80) =
#             the malformed LL_CIS_REQ trigger (iso_interval=0 and conn_event_count=0). On accept,
#             llcp_rp_cc_tx_rsp (ull_llcp_cc.c:177) divides by iso_interval_us=0 -> SIGFPE. An in-test
#             signal(SIGFPE,...) handler prints a real backtrace + "=== CRASH sig=SIGFPE ===" to stderr
#             then _exit(136). Channel-off true 1-minimal = {7} (bit7=128). Python returncode 136 / shell
#             136 (a clean handler exit, not a -8 signal death -- match returncode==136).
#
# -rdynamic lets backtrace_symbols_fd resolve the exported controller frames in the dump (the static
# faulting fn llcp_rp_cc_tx_rsp shows as a raw offset; the exported LLCP/CIS spine frames resolve by name).
# gdb (--cap-add SYS_PTRACE) anchors the exact site.
#
# Leaves build-cis/testbinary. Separate build dir; the other build dirs are untouched.
# Idempotent; re-uses the clone + SDK. Run: bash scripts/build-bugB.sh
set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
WS="${HARNESS_WS:-$WS_DEFAULT}"
T="tests/bluetooth/controller/ctrl_cis_create/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_cc.c"
TESTDIR="tests/bluetooth/controller/ctrl_cis_create"
PATCH="bugB.patch"
BUILD_DIR="build-cis"
LINK_FLAGS="-rdynamic"
mkdir -p "$WS"
cp "$HERE/patches/bugB-cis-window.patch" "$WS/$PATCH"

VERIFY=$(cat <<'EOF'
# Helper: run one HARNESS_SUBSET; never abort under set -e (binary exits nonzero on crash AND on the
# pre-existing ztest pass/fail). Key on the exit code: B=136 (SIGFPE handler _exit), else !=136.
run() { local m="$1" e; if HARNESS_BUG=B HARNESS_SUBSET="$m" "$BIN" >/dev/null 2>&1; then e=0; else e=$?; fi; echo "$e"; }

echo "### Bug B binary: build-cis/testbinary (the other build dirs are left untouched) ###"
echo "--- Bug B: channel-OFF exhaustive sweep (8-bit window) -> crash(136) <=> bit7 (0x80) ---"
cnt=0; bad=0
for m in $(seq 0 255); do
  e=$(run "$m")
  if [ "$e" = "136" ]; then cnt=$((cnt+1)); [ $((m & 128)) -eq 0 ] && bad=1; else [ $((m & 128)) -ne 0 ] && bad=1; fi
done
echo "    crashing subsets = $cnt / 256 (expect 128 = the bit7-set half); crash<=>bit7 holds: $([ $bad -eq 0 ] && echo YES || echo NO)"
echo "    true 1-minimal {7}=128 alone: exit=$(run 128) (expect 136);  empty=0: exit=$(run 0) (no crash)"
echo "    decoy transparency (trigger+each decoy still crashes): 0x81=$(run 129) 0x82=$(run 130) 0x84=$(run 132) 0x88=$(run 136) all4+trig 0x8F=$(run 143) (expect 136 each)"
echo "    decoys alone benign (never 136): 0x01=$(run 1) 0x0F=$(run 15)"
echo "    determinism (3x on 128): $(run 128) $(run 128) $(run 128)"

echo "### example dump (HARNESS_BUG=B HARNESS_SUBSET=128) — SIGFPE handler backtrace ###"
HARNESS_BUG=B HARNESS_SUBSET=128 "$BIN" 2>&1 | sed -n "/=== CRASH/,\$p" | grep -E "CRASH|llcp_rp_cc_run|ull_cp_run|event_prepare" | head
EOF
)
build_harness
