#!/usr/bin/env bash
# Build the real length_req-suppressor oracle binary on the vulnerable Zephyr controller and capture its
# channel-off exhaustive truth (a genuinely non-monotone real bug), for the suppressor part of the anchor, B1 and B3.
#
# Reuses the locked oracle harness (patches/oracle-harness.patch) -- the 4-PDU window [0]=PING [1]=VERSION
# [2]=FEATURE (transparent decoys), [3]=interval=0 trigger -- and adds window[4] = LL_LENGTH_REQ, the real
# suppressor found and independently reproduced: a peer LL_LENGTH_REQ starts a Data-Length procedure that,
# injected before the trigger, collides with / defers the conn-update so the trigger no longer applies
# (CONFIG_BT_CTLR_DATA_LENGTH=y makes the colliding procedure live). The injection is a small documented
# python edit on top of oracle-harness.patch's output, not a hand-counted patch.
#
# SIGFPE (shell exit 136 / Python returncode -8) iff window[3] set and window[4] not set => non-monotone.
# Emits build-lengthreq/truth-lengthreq.json (mask -> crash bool, 5-bit window) + a human log. Idempotent.
# Run: bash scripts/build-lengthreq.sh
set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
WS="${HARNESS_WS:-$(dirname "$WS_DEFAULT")/zephyr-cve-lengthreq}"
# This binary differs from the shared oracle (LL_LENGTH_REQ + BT_DATA_LEN_UPDATE), so it lives in its own
# *-lengthreq workspace and never dirties the shared clone; refuse anything else, even a forced HARNESS_WS.
case "$(basename "$WS")" in
  *-lengthreq) ;;
  *) echo "refuse: this script needs an isolated *-lengthreq workspace (got '$(basename "$WS")'). Unset HARNESS_WS for the default." >&2; exit 1 ;;
esac
T="tests/bluetooth/controller/ctrl_conn_update/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_conn_upd.c"
TESTDIR="tests/bluetooth/controller/ctrl_conn_update"
PATCH="oracle.patch"
BUILD_DIR="build-lengthreq"
mkdir -p "$WS"
cp "$HERE/patches/oracle-harness.patch" "$WS/$PATCH"

PRE_CMAKE=$(cat <<'EOF'
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
assert "pdu_data_llctrl_length_req len" in s and "LL_LENGTH_REQ, &len" in s, "LL_LENGTH_REQ injection did not apply"
open(f, "w").write(s)
print("  injected LL_LENGTH_REQ as window[4]")
PY

# the Data-Length procedure must be live for the collision. BT_CTLR_DATA_LENGTH is a HIDDEN symbol
# (no prompt): it goes default-y once BT_DATA_LEN_UPDATE + the ACL buffer sizes are set (how the
# upstream ctrl_data_length_update test enables it). Set the enablers, not the hidden symbol.
{ echo "CONFIG_BT_DATA_LEN_UPDATE=y"; echo "CONFIG_BT_BUF_ACL_TX_SIZE=251";
  echo "CONFIG_BT_BUF_ACL_RX_SIZE=251"; echo "CONFIG_BT_CTLR_DATA_LENGTH_MAX=251"; } >> $TESTDIR/prj.conf
EOF
)
VERIFY=$(cat <<'EOF'
echo "### channel-OFF exhaustive sweep (5-PDU window: 0=PING 1=VER 2=FEAT 3=TRIGGER 4=LENGTH_REQ) ###"
LOG=/work/build-lengthreq/truth-lengthreq.txt
JSON=/work/build-lengthreq/truth-lengthreq.json
echo "length_req-suppressor truth (5-PDU; crash iff bit3 set AND bit4 NOT set if length_req suppresses)" > "$LOG"
printf "{\n" > "$JSON"
ncr=0
for m in $(seq 0 31); do
  set +e; HARNESS_SUBSET=$m "$BIN" >/dev/null 2>&1; rc=$?; set -e
  if [ "$rc" -eq 136 ]; then cr=true; ncr=$((ncr+1)); else cr=false; fi
  t3=$(( (m>>3)&1 )); t4=$(( (m>>4)&1 ))
  printf "mask=%2d trigger=%d length_req=%d rc=%3d crash=%s\n" "$m" "$t3" "$t4" "$rc" "$cr" >> "$LOG"
  comma=","; [ "$m" -eq 31 ] && comma=""
  printf "  \"%d\": %s%s\n" "$m" "$cr" "$comma" >> "$JSON"
done
printf "}\n" >> "$JSON"
echo "  $ncr/32 masks crash -> build-lengthreq/truth-lengthreq.json (log: truth-lengthreq.txt)"
EOF
)
build_harness
echo "done: $WS/build-lengthreq/truth-lengthreq.json (copy to code/src/emulation/data/truth-lengthreq.json)"
