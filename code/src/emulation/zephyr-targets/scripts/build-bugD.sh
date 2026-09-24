#!/usr/bin/env bash
# Bug D — build the subset-selectable PHY-update doubled-IND assert oracle binary on the vulnerable Zephyr
# LL controller and verify its channel-off exhaustive sweep + true 2-minimal.
#
# The harness (patches/bugD-phy-window.patch) adds one ZTEST (test_bug_d) to the ctrl_phy_update suite;
# a no-op unless selected by env HARNESS_BUG=D (whole suite, no per-test CLI filter, selection by getenv --
# the existing PROBE_ID pattern). HARNESS_SUBSET is a bitmask over the LL-PDU window.
#
#   HARNESS_BUG=D  test_bug_d: confirmed PHY doubled-IND assert. A multi-packet minimal (like Bug C).
#             5-bit window: bits0..2 = transparent (droppable) drained local LE-Pings, bit3 =
#             LL_PHY_UPDATE_IND #1, bit4 = LL_PHY_UPDATE_IND #2 (load-bearing). The LL_PHY_REQ precondition
#             (procedure start) is injected whenever any IND is present. A second IND while in WAIT_INSTANT
#             desyncs the retained NTF rx node; at the instant pu_ntf (ull_llcp_phy.c:437) hits
#             LL_ASSERT(ntf) -> mocked bt_ctlr_assert_handle -> exit(-1). Channel-off true 2-minimal =
#             {IND1,IND2} = 24 (0x18). The assert emits its own message (ASSERTION FAIL [ntf] @
#             ull_llcp_phy.c:437); no SIGFPE handler needed. Python rc 255 / shell 255.
#
# -rdynamic is passed for symbol-rich dumps (parity with the other bug scripts); Bug D reproduces
# identically without it (the assert message is the artifact, not a backtrace).
#
# Leaves build-phy/testbinary. Separate build dir; the other build dirs are untouched.
# Idempotent; reuses the clone + SDK. Run: bash scripts/build-bugD.sh
set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
WS="${HARNESS_WS:-$WS_DEFAULT}"
T="tests/bluetooth/controller/ctrl_phy_update/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_phy.c"
TESTDIR="tests/bluetooth/controller/ctrl_phy_update"
PATCH="bugD.patch"
BUILD_DIR="build-phy"
LINK_FLAGS="-rdynamic"
mkdir -p "$WS"
cp "$HERE/patches/bugD-phy-window.patch" "$WS/$PATCH"

VERIFY=$(cat <<'EOF'
# Helper: run one HARNESS_SUBSET; never abort under set -e (binary exits nonzero on crash AND on the
# pre-existing ztest pass/fail). Key on the exit code: D=255 (LL_ASSERT -> exit(-1)), else !=255.
run() { local m="$1" e; if HARNESS_BUG=D HARNESS_SUBSET="$m" "$BIN" >/dev/null 2>&1; then e=0; else e=$?; fi; echo "$e"; }

echo "### Bug D binary: build-phy/testbinary (the other build dirs are left untouched) ###"
echo "--- Bug D: channel-OFF exhaustive sweep (5-bit window) -> crash(255) <=> BOTH IND bits (0x18) ---"
cnt=0; bad=0
for m in $(seq 0 31); do
  e=$(run "$m")
  if [ "$e" = "255" ]; then cnt=$((cnt+1)); [ $((m & 24)) -ne 24 ] && bad=1; fi
done
echo "    crashing subsets = $cnt / 32 (expect 8 = supersets of {IND1,IND2}); all crashers hold both INDs: $([ $bad -eq 0 ] && echo YES || echo NO)"
echo "    true 2-minimal {IND1,IND2}=24 (0x18): exit=$(run 24) (expect 255)"
echo "    each 1-smaller subset benign: {IND1}=8 exit=$(run 8), {IND2}=16 exit=$(run 16) (expect non-255)"
echo "    decoy transparency (each decoy + both INDs still crashes): 0x19=$(run 25) 0x1A=$(run 26) 0x1C=$(run 28) all3+INDs 0x1F=$(run 31) (expect 255 each)"
echo "    decoys alone benign (never 255): 0x01=$(run 1) 0x07=$(run 7) empty=0=$(run 0)"
echo "    determinism (3x on 24): $(run 24) $(run 24) $(run 24)"

echo "### example dump (HARNESS_BUG=D HARNESS_SUBSET=24) — controller assert message ###"
HARNESS_BUG=D HARNESS_SUBSET=24 "$BIN" 2>&1 | grep -E "Running TESTSUITE phy_periph|ull_llcp_phy\.c:437"
[ "$bad" -eq 0 ] || { echo "### VERIFY FAILED: the truth table does not hold ###"; exit 1; }
EOF
)
build_harness
