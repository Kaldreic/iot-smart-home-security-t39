# Attack Strategies: Technique of disturbance

<div class="slide-tagline">How does AirBugCatcher trigger a crash?</div>

<div class="testcase-grid">
<div class="testcase-card">
<div class="testcase-num">1</div>
<div class="testcase-title">Malformed packet</div>
<div class="testcase-body">Overwrite target bytes of a captured packet.</div>
</div>
<div class="testcase-card">
<div class="testcase-num">2</div>
<div class="testcase-title">Replay</div>
<div class="testcase-body">Retransmit a captured packet unchanged.</div>
</div>
<div class="testcase-card">
<div class="testcase-num">3</div>
<div class="testcase-title">Flooding</div>
<div class="testcase-body">Continuously repeat the same packet.</div>
</div>
</div>

<div class="attack-flow">
<div class="feedback">
<div class="kicker">Feedback</div>
<div class="feedback-chain">
  <span class="chip">Run</span>
  <svg class="icon" viewBox="0 0 22 10" width="22" height="10" xmlns="http://www.w3.org/2000/svg"><line x1="2" y1="5" x2="16" y2="5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="15,2 20,5 15,8" fill="#822433"/></svg>
  <span class="chip">Target</span>
  <svg class="icon" viewBox="0 0 22 10" width="22" height="10" xmlns="http://www.w3.org/2000/svg"><line x1="2" y1="5" x2="16" y2="5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="15,2 20,5 15,8" fill="#822433"/></svg>
  <span class="chip">Logs + behaviour</span>
  <svg class="icon" viewBox="0 0 22 10" width="22" height="10" xmlns="http://www.w3.org/2000/svg"><line x1="2" y1="5" x2="16" y2="5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="15,2 20,5 15,8" fill="#822433"/></svg>
  <span class="chip chip-solid">Bug ID match?</span>
  <svg class="icon" viewBox="0 0 40 60" width="40" height="60" xmlns="http://www.w3.org/2000/svg"><line x1="0" y1="30" x2="16" y2="30" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="16" y1="14" x2="16" y2="46" stroke="#822433" stroke-width="1.5"/><line x1="16" y1="14" x2="33" y2="14" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="32,11 37,14 32,17" fill="#822433"/><line x1="16" y1="46" x2="33" y2="46" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="32,43 37,46 32,49" fill="#822433"/></svg>
  <div class="outcomes">
    <div class="hbox">
      <span class="kicker">YES</span>
      <span class="chip chip-tint">Reproduced <strong>✓</strong></span>
    </div>
    <div class="hbox">
      <span class="kicker">NO</span>
      <span class="chip chip-tint chip-dashed">Timeout → retry<svg class="icon" viewBox="0 0 14 14" width="11" height="11" xmlns="http://www.w3.org/2000/svg"><circle cx="7" cy="7" r="5.5" fill="none" stroke="#822433" stroke-width="1.3"/><line x1="7" y1="7" x2="7" y2="3.6" stroke="#822433" stroke-width="1.3" stroke-linecap="round"/><line x1="7" y1="7" x2="10" y2="7" stroke="#822433" stroke-width="1.3" stroke-linecap="round"/></svg></span>
    </div>
  </div>
</div>
</div>
<div class="caveat">
<span class="evidence-protocol">Caveat</span>
<div class="caveat-items">
<svg class="icon" viewBox="0 0 18 16" width="18" height="16" xmlns="http://www.w3.org/2000/svg"><path d="M 9 2 L 17 14 L 1 14 Z" fill="#ffffff" stroke="#822433" stroke-width="1.5" stroke-linejoin="round"/><line x1="9" y1="6" x2="9" y2="10.5" stroke="#822433" stroke-width="1.6" stroke-linecap="round"/><circle cx="9" cy="12.3" r="0.85" fill="#822433"/></svg>
<span class="chip"><strong>FP</strong> · same bug, different IDs</span>
<span class="chip"><strong>FN</strong> · different bugs, same ID</span>
</div>
</div>
</div>
