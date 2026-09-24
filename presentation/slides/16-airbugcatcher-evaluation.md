# AirBugCatcher succeeds where simple replay cannot

<div class="slide-tagline">The MITM advantage — and why 5G NR wins the most</div>

<div class="callout"><strong>Simple replay</strong> only triggers bugs sporadically on Bluetooth, scoring zero on 5G NR and Wi-Fi. <strong>AirBugCatcher</strong> reproduces across all three — with 5G NR reaching <strong>93%</strong> because most of those bugs fire on a single mutated RRC packet.</div>

<div class="cmp-grid">
  <div class="cmp cmp-abc">
    <div class="cmp-head">
      <span>AirBugCatcher</span>
      <span class="cmp-unit">expected</span>
    </div>
    <div class="cmp-body">
      <div class="cmp-row">
        <span class="cmp-target"><svg class="icon" viewBox="0 0 32 32" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><rect x="4" y="20" width="4" height="8" fill="#822433" rx="0.5"/><rect x="11" y="15" width="4" height="13" fill="#822433" rx="0.5"/><rect x="18" y="10" width="4" height="18" fill="#822433" rx="0.5"/><rect x="25" y="5" width="4" height="23" fill="#822433" rx="0.5"/></svg>5G NR · OnePlus</span>
        <strong class="num">13 / 14 · 93%</strong>
      </div>
      <div class="cmp-row">
        <span class="cmp-target"><svg class="icon" viewBox="0 0 32 32" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><path d="M 8 10 L 24 22 L 16 28 L 16 4 L 24 10 L 8 22" fill="none" stroke="#822433" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>Bluetooth · ESP32</span>
        <strong class="num">11 / 16 · 69%</strong>
      </div>
      <div class="cmp-row">
        <span class="cmp-target"><svg class="icon" viewBox="0 0 32 32" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><path d="M 4 12 A 14 14 0 0 1 28 12" fill="none" stroke="#822433" stroke-width="2" stroke-linecap="round"/><path d="M 8 17 A 10 10 0 0 1 24 17" fill="none" stroke="#822433" stroke-width="2" stroke-linecap="round"/><path d="M 12 22 A 6 6 0 0 1 20 22" fill="none" stroke="#822433" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="27" r="2" fill="#822433"/></svg>Wi-Fi · ESP-WROVER</span>
        <strong class="num">2 / 4 · 50%</strong>
      </div>
    </div>
  </div>
  <div class="cmp cmp-replay">
    <div class="cmp-head">
      <span>Simple Replay · baseline</span>
      <span class="cmp-unit">triggered</span>
    </div>
    <div class="cmp-body">
      <div class="cmp-row">
        <span class="cmp-target"><svg class="icon" viewBox="0 0 32 32" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><rect x="4" y="20" width="4" height="8" fill="#822433" rx="0.5"/><rect x="11" y="15" width="4" height="13" fill="#822433" rx="0.5"/><rect x="18" y="10" width="4" height="18" fill="#822433" rx="0.5"/><rect x="25" y="5" width="4" height="23" fill="#822433" rx="0.5"/></svg>5G NR · OnePlus</span>
        <span class="num"><svg class="icon" viewBox="0 0 12 12" width="11" height="11" xmlns="http://www.w3.org/2000/svg"><line x1="2" y1="2" x2="10" y2="10" stroke="#822433" stroke-width="1.8" stroke-linecap="round"/><line x1="10" y1="2" x2="2" y2="10" stroke="#822433" stroke-width="1.8" stroke-linecap="round"/></svg><strong>0 (5 trials)</strong></span>
      </div>
      <div class="cmp-row">
        <span class="cmp-target"><svg class="icon" viewBox="0 0 32 32" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><path d="M 8 10 L 24 22 L 16 28 L 16 4 L 24 10 L 8 22" fill="none" stroke="#822433" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>Bluetooth · ESP32</span>
        <strong class="num">13–23 of 190 crashes (5 trials)</strong>
      </div>
      <div class="cmp-row">
        <span class="cmp-target"><svg class="icon" viewBox="0 0 32 32" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><path d="M 4 12 A 14 14 0 0 1 28 12" fill="none" stroke="#822433" stroke-width="2" stroke-linecap="round"/><path d="M 8 17 A 10 10 0 0 1 24 17" fill="none" stroke="#822433" stroke-width="2" stroke-linecap="round"/><path d="M 12 22 A 6 6 0 0 1 20 22" fill="none" stroke="#822433" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="27" r="2" fill="#822433"/></svg>Wi-Fi · ESP-WROVER</span>
        <span class="num"><svg class="icon" viewBox="0 0 12 12" width="11" height="11" xmlns="http://www.w3.org/2000/svg"><line x1="2" y1="2" x2="10" y2="10" stroke="#822433" stroke-width="1.8" stroke-linecap="round"/><line x1="10" y1="2" x2="2" y2="10" stroke="#822433" stroke-width="1.8" stroke-linecap="round"/></svg><strong>0 (5 trials)</strong></span>
      </div>
    </div>
  </div>
</div>

<div class="cmp-grid">
  <div class="testcase-card">
    <div class="testcase-title hbox"><svg class="icon" viewBox="0 0 16 16" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><circle cx="8" cy="8" r="6.5" fill="none" stroke="#822433" stroke-width="1.4"/><line x1="4.2" y1="4.2" x2="11.8" y2="11.8" stroke="#822433" stroke-width="1.6" stroke-linecap="round"/></svg>Why replay fails</div>
    <div class="testcase-body">Non-deterministic RX: the target expects context-dependent values (authentication parameters, message order) that a static replay cannot carry, so it rejects or drops the connection.</div>
  </div>
  <div class="testcase-card">
    <div class="testcase-title hbox"><svg class="icon" viewBox="0 0 16 16" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><polygon points="8,1.5 10,6 14.5,6.5 11,9.5 12,14 8,11.5 4,14 5,9.5 1.5,6.5 6,6" fill="#822433" stroke="#822433" stroke-width="0.8" stroke-linejoin="round"/></svg>Why 5G NR wins most</div>
    <div class="testcase-body">Most OnePlus bugs trigger on a single mutated RRC packet — one well-placed mutation does the job, no replay or flooding across protocol states needed.</div>
  </div>
</div>
