# Two papers, two directions — one wireless layer

<div class="slide-tagline">Outbound privacy, inbound robustness — both below closed firmware</div>

<div class="recap">
  <div class="card">
    <div class="card-head">
      <svg class="icon" viewBox="0 0 20 20" width="18" height="18" xmlns="http://www.w3.org/2000/svg"><path d="M 10 1.8 L 17 4.5 L 17 10.5 Q 17 15.5 10 18 Q 3 15.5 3 10.5 L 3 4.5 Z" fill="#ffffff"/><path d="M 6.5 10.2 L 8.8 12.6 L 13.2 7.8" fill="none" stroke="#822433" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <div class="head-text">
        <div class="card-title">WiShield</div>
        <div class="card-kicker">Outbound · privacy defense</div>
      </div>
      <svg class="icon icon-soft" viewBox="0 0 24 12" width="26" height="14" xmlns="http://www.w3.org/2000/svg"><polygon points="2,6 8,1 8,4 22,4 22,8 8,8 8,11" fill="#ffffff"/></svg>
    </div>
    <div class="card-body">
      <div class="fact">
        <span class="kicker">Threat</span>
        <span class="text">Wi-Fi CSI leaks motion and occupancy to adversarial sensing.</span>
      </div>
      <div class="fact">
        <span class="kicker">Mechanism</span>
        <span class="text">RF obfuscator between antenna and NIC — amplitude and phase distortion.</span>
      </div>
      <div class="fact">
        <span class="kicker">Outcome</span>
        <span class="text"><strong>Breaks adversarial sensing</strong>; intermittent (Run + Idle) operation cuts the PER cost of amplitude obfuscation, a stated trade-off.</span>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-head">
      <svg class="icon icon-soft" viewBox="0 0 24 12" width="26" height="14" xmlns="http://www.w3.org/2000/svg"><polygon points="22,6 16,1 16,4 2,4 2,8 16,8 16,11" fill="#ffffff"/></svg>
      <div class="head-text">
        <div class="card-title">AirBugCatcher</div>
        <div class="card-kicker">Inbound · robustness defense</div>
      </div>
      <svg class="icon" viewBox="0 0 20 20" width="18" height="18" xmlns="http://www.w3.org/2000/svg"><ellipse cx="10" cy="11" rx="4.2" ry="5" fill="#ffffff"/><line x1="10" y1="6.5" x2="10" y2="15.5" stroke="#822433" stroke-width="0.6"/><line x1="4.5" y1="8.5" x2="2" y2="7" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"/><line x1="4.5" y1="11" x2="2" y2="11" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"/><line x1="4.5" y1="13.5" x2="2" y2="15" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"/><line x1="15.5" y1="8.5" x2="18" y2="7" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"/><line x1="15.5" y1="11" x2="18" y2="11" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"/><line x1="15.5" y1="13.5" x2="18" y2="15" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"/><line x1="8.2" y1="7" x2="6.8" y2="4.2" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"/><line x1="11.8" y1="7" x2="13.2" y2="4.2" stroke="#ffffff" stroke-width="1.4" stroke-linecap="round"/></svg>
    </div>
    <div class="card-body">
      <div class="fact">
        <span class="kicker">Threat</span>
        <span class="text">OTA fuzzing finds bugs but wireless non-determinism blocks reproduction.</span>
      </div>
      <div class="fact">
        <span class="kicker">Mechanism</span>
        <span class="text">Live-MITM packet mutation — catch matching packets, modify fields, forward.</span>
      </div>
      <div class="fact">
        <span class="kicker">Outcome</span>
        <span class="text"><strong>33 of 44 unique bugs reproduced as expected</strong> (40 triggered) where simple replay scored zero on 5G and Wi-Fi.</span>
      </div>
    </div>
  </div>
</div>

<div class="recap-line">
  <svg class="icon" viewBox="0 0 14 14" width="12" height="12" xmlns="http://www.w3.org/2000/svg"><line x1="2" y1="2" x2="10.5" y2="10.5" stroke="#822433" stroke-width="1.6" stroke-linecap="round"/><polygon points="11.8,11.8 6.6,11.8 11.8,6.6" fill="#822433"/></svg>
  <span class="kicker">Both below closed firmware</span>
  <svg class="icon" viewBox="0 0 14 14" width="12" height="12" xmlns="http://www.w3.org/2000/svg"><line x1="12" y1="2" x2="3.5" y2="10.5" stroke="#822433" stroke-width="1.6" stroke-linecap="round"/><polygon points="2.2,11.8 7.4,11.8 2.2,6.6" fill="#822433"/></svg>
</div>

<div class="diagram-caption wide">Two ACSAC 2024 papers — <strong>opposite directions, same wireless layer, same bolt-on strategy</strong>.</div>
