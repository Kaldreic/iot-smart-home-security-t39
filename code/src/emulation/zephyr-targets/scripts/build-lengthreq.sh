#!/usr/bin/env bash
# Build the REAL length_req-SUPPRESSOR oracle binary on the vulnerable Zephyr controller and
# capture its channel-OFF exhaustive truth (a genuinely NON-MONOTONE real bug), for the Arm A/B/B+ run.
#
# Reuses the LOCKED oracle harness (patches/oracle-harness.patch) -- the 4-PDU window [0]=PING [1]=VERSION
# [2]=FEATURE (transparent decoys) [3]=interval=0 trigger -- and ADDS window[4] = LL_LENGTH_REQ, the
# REAL suppressor found + independently reproduced: a peer LL_LENGTH_REQ starts a Data-Length
# procedure that, injected BEFORE the trigger, collides with / defers the conn-update so the trigger no
# longer applies (CONFIG_BT_CTLR_DATA_LENGTH=y makes the colliding procedure live). The injection is
# added by a small documented python edit (not a hand-counted patch) on top of oracle-harness.patch's output.
#
# SIGFPE (shell exit 136 / Python returncode -8) iff window[3] set AND window[4] NOT set => non-monotone.
# Emits build-lengthreq/truth-lengthreq.json (mask -> crash bool, 5-bit window) + a human log.
# Idempotent. Run: bash scripts/build-lengthreq.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
EXP="$(cd "$HERE/../../.." && pwd)"
WS="${HARNESS_WS:-$EXP/upstream/zephyr-cve-lengthreq}"
# isolation guard: this builds a DIFFERENT binary (LL_LENGTH_REQ + BT_DATA_LEN_UPDATE) than the
# shared oracle, so it must live in its own *-lengthreq workspace + build-lengthreq dir and NEVER dirty the
# shared zephyr-cve oracle workspace. Refuse anything else (even if HARNESS_WS is force-supplied).
case "$(basename "$WS")" in
  *-lengthreq) ;;
  *) echo "refuse: this script needs an isolated *-lengthreq workspace (got '$(basename "$WS")') — it would clobber the shared oracle workspace. Unset HARNESS_WS for the default." >&2; exit 1 ;;
esac
IMG="ghcr.io/zephyrproject-rtos/zephyr-build@sha256:a9b3f2228810bff6f3cb3a15450aa55d5b943803e26e6f17db8c5a781e3f69fe"
VULN="4ae207ccac8e763c4d81ea88e397e17f294169ba"
FIX="e91b3e3638765680c092d583023a92e719e7b8c4"
T="tests/bluetooth/controller/ctrl_conn_update/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_conn_upd.c"
TESTDIR="tests/bluetooth/controller/ctrl_conn_update"

mkdir -p "$WS"
cp "$HERE/patches/oracle-harness.patch" "$WS/oracle.patch"

docker run --rm -v "$WS:/work" -w /work -e HOME=/work --user "$(id -u):$(id -g)" \
  -e ZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 "$IMG" bash -lc '
set -e
VULN='"$VULN"'; FIX='"$FIX"'; T="'"$T"'"; GUARD="'"$GUARD"'"; TESTDIR="'"$TESTDIR"'"

if [ ! -d zephyr/.git ]; then git init -q zephyr && (cd zephyr && \
   git remote add origin https://github.com/zephyrproject-rtos/zephyr.git); fi
cd zephyr
rm -f .git/shallow.lock .git/index.lock
git fetch -q --depth 1 origin $VULN && git checkout -q -f $VULN
git fetch -q --depth 1 origin $FIX
git checkout -q -f $VULN -- $GUARD
git show $FIX:$T > $T
git apply /work/oracle.patch                          # the LOCKED 4-PDU oracle harness (test_oracle)

# --- add window[4] = LL_LENGTH_REQ (the REAL suppressor) to test_oracle. Documented python
#     insertion (robust vs hand-counted patch hunks): a struct decl + one INJECT, BEFORE the trigger.
python3 - "$T" <<"PY"
import sys
f = sys.argv[1]; s = open(f).read()
assert "test_oracle" in s and "LL_FEATURE_REQ, &feat" in s, "oracle harness not found as expected"
s = s.replace(
    "\tstruct pdu_data_llctrl_feature_req feat = { .features = { 0xFFU, 0, 0, 0, 0, 0, 0, 0 } };",
    "\tstruct pdu_data_llctrl_feature_req feat = { .features = { 0xFFU, 0, 0, 0, 0, 0, 0, 0 } };\n"
    "\tstruct pdu_data_llctrl_length_req len = { 27, 328, 211, 1800 }; /* peer Data-Length */", 1)
s = s.replace(
    "\tINJECT(0x04U, LL_FEATURE_REQ, &feat);     /* window[2] */",
    "\tINJECT(0x04U, LL_FEATURE_REQ, &feat);     /* window[2] */\n"
    "\tINJECT(0x10U, LL_LENGTH_REQ, &len);       /* window[4]: REAL suppressor, BEFORE the trigger */", 1)
open(f, "w").write(s)
print("  injected LL_LENGTH_REQ as window[4]")
PY

# the Data-Length procedure must be live for the collision. BT_CTLR_DATA_LENGTH is a HIDDEN symbol
# (no prompt): it goes default-y once BT_DATA_LEN_UPDATE + the ACL buffer sizes are set (how the
# upstream ctrl_data_length_update test enables it). Set the enablers, not the hidden symbol.
{ echo "CONFIG_BT_DATA_LEN_UPDATE=y"; echo "CONFIG_BT_BUF_ACL_TX_SIZE=251";
  echo "CONFIG_BT_BUF_ACL_RX_SIZE=251"; echo "CONFIG_BT_CTLR_DATA_LENGTH_MAX=251"; } >> $TESTDIR/prj.conf

cd /work
if [ ! -d zephyr-sdk-0.16.5 ]; then
  wget -q https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v0.16.5/zephyr-sdk-0.16.5_linux-x86_64_minimal.tar.xz -O sdk.tar.xz
  tar xf sdk.tar.xz && rm -f sdk.tar.xz
fi
export ZEPHYR_BASE=/work/zephyr
rm -rf build-lengthreq
cmake -B build-lengthreq -GNinja -DBOARD=unit_testing -DZEPHYR_BASE="$ZEPHYR_BASE" \
  -DCONFIG_BT_GATT_CACHING=n -DZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 \
  "$ZEPHYR_BASE/$TESTDIR" >/dev/null
ninja -C build-lengthreq >/dev/null

echo "### channel-OFF exhaustive sweep (5-PDU window: 0=PING 1=VER 2=FEAT 3=TRIGGER 4=LENGTH_REQ) ###"
LOG=/work/build-lengthreq/truth-lengthreq.txt
JSON=/work/build-lengthreq/truth-lengthreq.json
echo "length_req-suppressor truth (5-PDU; crash iff bit3 set AND bit4 NOT set if length_req suppresses)" > "$LOG"
printf "{\n" > "$JSON"
ncr=0
for m in $(seq 0 31); do
  set +e; HARNESS_SUBSET=$m ./build-lengthreq/testbinary >/dev/null 2>&1; rc=$?; set -e
  if [ "$rc" -eq 136 ]; then cr=true; ncr=$((ncr+1)); else cr=false; fi
  t3=$(( (m>>3)&1 )); t4=$(( (m>>4)&1 ))
  printf "mask=%2d trigger=%d length_req=%d rc=%3d crash=%s\n" "$m" "$t3" "$t4" "$rc" "$cr" >> "$LOG"
  comma=","; [ "$m" -eq 31 ] && comma=""
  printf "  \"%d\": %s%s\n" "$m" "$cr" "$comma" >> "$JSON"
done
printf "}\n" >> "$JSON"
echo "  $ncr/32 masks crash -> build-lengthreq/truth-lengthreq.json (log: truth-lengthreq.txt)"
'
echo "done: $WS/build-lengthreq/truth-lengthreq.json (copy to code/src/emulation/data/truth-lengthreq.json)"
