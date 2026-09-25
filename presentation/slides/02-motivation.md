# Smart-home wireless: leaks out, crashes in

<div class="slide-tagline">Every device is always transmitting and listening</div>

<div class="leak-crash">
  <div class="card">
    <div class="card-head">
      <span class="card-title">Leaks out</span>
      <span class="card-kicker">outbound · privacy</span>
    </div>
    <div class="flow">
      <div class="endpoint">
        <svg viewBox="0 0 40 40" width="40" height="40" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="19" width="28" height="14" fill="#ffffff" stroke="#822433" stroke-width="1.8" rx="1.5"/><circle cx="11" cy="26" r="1.3" fill="#822433"/><circle cx="15.5" cy="26" r="1" fill="none" stroke="#822433" stroke-width="0.8"/><circle cx="20" cy="26" r="1" fill="none" stroke="#822433" stroke-width="0.8"/><line x1="12" y1="19" x2="9" y2="6" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><circle cx="9" cy="5" r="1.3" fill="#822433"/><line x1="28" y1="19" x2="31" y2="6" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><circle cx="31" cy="5" r="1.3" fill="#822433"/></svg>
        <div class="endpoint-label">Smart device</div>
      </div>
      <div class="channel">
        <div class="channel-label">Wi-Fi signal</div>
        <svg viewBox="0 0 100 14" width="100%" height="16" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none"><path d="M 2 7 Q 8 1.5 14 7 T 26 7 T 38 7 T 50 7 T 62 7 T 74 7 T 84 7" fill="none" stroke="#822433" stroke-width="1.5"/><path d="M 82 3.5 L 92 7 L 82 10.5 Z" fill="#822433"/></svg>
      </div>
      <div class="endpoint">
        <svg viewBox="0 0 40 40" width="40" height="40" xmlns="http://www.w3.org/2000/svg"><ellipse cx="20" cy="20" rx="17" ry="9" fill="#ffffff" stroke="#822433" stroke-width="1.8"/><circle cx="20" cy="20" r="6" fill="#822433"/><circle cx="22" cy="18" r="2" fill="#ffffff"/></svg>
        <div class="endpoint-label">Eavesdropper</div>
      </div>
    </div>
    <div class="card-foot">
      <div class="text">Motion, gestures, even keystrokes — inferred from Wi-Fi perturbations.</div>
      <div class="subline">e.g. WindTalker · 2016 — keystrokes from CSI</div>
    </div>
  </div>
  <div class="card">
    <div class="card-head">
      <span class="card-title">Crashes in</span>
      <span class="card-kicker">inbound · reliability</span>
    </div>
    <div class="flow">
      <div class="endpoint">
        <svg viewBox="0 0 40 40" width="40" height="40" xmlns="http://www.w3.org/2000/svg"><path d="M 20 5 L 36 32 L 4 32 Z" fill="#ffffff" stroke="#822433" stroke-width="1.8" stroke-linejoin="round"/><line x1="20" y1="14" x2="20" y2="24" stroke="#822433" stroke-width="2.2" stroke-linecap="round"/><circle cx="20" cy="28" r="1.7" fill="#822433"/></svg>
        <div class="endpoint-label">Attacker</div>
      </div>
      <div class="channel">
        <div class="channel-label">Malformed packet</div>
        <svg viewBox="0 0 100 16" width="100%" height="16" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none"><line x1="2" y1="8" x2="84" y2="8" stroke="#822433" stroke-width="1.8" stroke-dasharray="4 3"/><path d="M 82 4 L 92 8 L 82 12 Z" fill="#822433"/><rect x="40" y="2.5" width="16" height="11" fill="#ffffff" stroke="#822433" stroke-width="1.2" rx="1"/><line x1="42.5" y1="5.5" x2="53.5" y2="5.5" stroke="#822433" stroke-width="0.6"/><line x1="42.5" y1="8" x2="50" y2="8" stroke="#822433" stroke-width="0.6"/><line x1="42.5" y1="10.5" x2="53.5" y2="10.5" stroke="#822433" stroke-width="0.6"/></svg>
      </div>
      <div class="endpoint">
        <svg viewBox="0 0 40 40" width="40" height="40" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="19" width="28" height="14" fill="#ffffff" stroke="#822433" stroke-width="1.8" rx="1.5"/><line x1="12" y1="19" x2="9" y2="6" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><circle cx="9" cy="5" r="1.3" fill="#822433"/><line x1="28" y1="19" x2="31" y2="6" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><circle cx="31" cy="5" r="1.3" fill="#822433"/><path d="M 20 21 L 16 27 L 20 27 L 17 32 L 24 25 L 20 25 Z" fill="#822433"/><line x1="3" y1="14" x2="0.5" y2="11.5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="37" y1="14" x2="39.5" y2="11.5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="3" y1="37" x2="0.5" y2="39.5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="37" y1="37" x2="39.5" y2="39.5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/></svg>
        <div class="endpoint-label">Device · crashes</div>
      </div>
    </div>
    <div class="card-foot">
      <div class="text">Protocol stacks crash on malformed Wi-Fi, Bluetooth, or 5G packets.</div>
      <div class="subline">e.g. BrakTooth · 2021 — dozens of BT stack bugs</div>
    </div>
  </div>
</div>

<div class="diagram-caption" style="margin-top: 2.5rem;">Defending the smart home requires hardening <strong>both directions</strong></div>
