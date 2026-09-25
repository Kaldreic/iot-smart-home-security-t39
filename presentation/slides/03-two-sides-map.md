# Public research has already attacked every wireless protocol we use

<div class="slide-tagline">Wi-Fi, Bluetooth, 5G — concrete prior art on each</div>

<div class="protocol-cards">
  <div class="card">
    <div class="card-head">
      <svg class="icon" viewBox="0 0 32 32" width="26" height="26" xmlns="http://www.w3.org/2000/svg"><path d="M 4 12 A 14 14 0 0 1 28 12" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round"/><path d="M 8 17 A 10 10 0 0 1 24 17" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round"/><path d="M 12 22 A 6 6 0 0 1 20 22" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round"/><circle cx="16" cy="27" r="2" fill="#ffffff"/></svg>
      <div class="head-text">
        <div class="card-title">Wi-Fi</div>
        <div class="card-kicker">CSI side-channel leakage</div>
      </div>
    </div>
    <div class="card-body">
      <div class="text"><strong>WindTalker</strong> <span class="year">· 2016</span> — keystroke recovery from hotspot CSI.</div>
      <div class="text"><strong>Zhu et al.</strong> — stealth eavesdrop from a single smartphone.</div>
      <div class="text"><strong>Banerjee et al.</strong> — localising and tracking humans through walls.</div>
    </div>
    <div class="card-foot">All three: Wi-Fi channel measurement</div>
  </div>
  <div class="card">
    <div class="card-head">
      <svg class="icon" viewBox="0 0 32 32" width="26" height="26" xmlns="http://www.w3.org/2000/svg"><path d="M 8 10 L 24 22 L 16 28 L 16 4 L 24 10 L 8 22" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/></svg>
      <div class="head-text">
        <div class="card-title">Bluetooth · BLE</div>
        <div class="card-kicker">Protocol-stack crashes</div>
      </div>
    </div>
    <div class="card-body vcenter"><div class="text"><strong>BrakTooth-family</strong> <span class="year">· 2021</span> — over-the-air fuzzing revealing numerous stack bugs across COTS devices.</div></div>
    <div class="card-foot">Dozens of disclosed BT stack bugs</div>
  </div>
  <div class="card">
    <div class="card-head">
      <svg class="icon" viewBox="0 0 32 32" width="26" height="26" xmlns="http://www.w3.org/2000/svg"><rect x="4" y="20" width="4" height="8" fill="#ffffff" rx="0.5"/><rect x="11" y="15" width="4" height="13" fill="#ffffff" rx="0.5"/><rect x="18" y="10" width="4" height="18" fill="#ffffff" rx="0.5"/><rect x="25" y="5" width="4" height="23" fill="#ffffff" rx="0.5"/></svg>
      <div class="head-text">
        <div class="card-title">5G NR</div>
        <div class="card-kicker">Baseband crashes</div>
      </div>
    </div>
    <div class="card-body vcenter"><div class="text"><strong>U-Fuzz</strong> — baseband-level crashes over the air; the framework AirBugCatcher later leverages.</div></div>
    <div class="card-foot">Open-source 5G NR fuzzing</div>
  </div>
</div>

<div class="protocol-flow">
  <span class="pill">Everyday wireless</span>
  <svg class="icon" viewBox="0 0 24 10" width="24" height="10" xmlns="http://www.w3.org/2000/svg"><line x1="2" y1="5" x2="18" y2="5" stroke="#822433" stroke-width="1.4" stroke-linecap="round"/><path d="M 16 2 L 22 5 L 16 8 Z" fill="#822433"/></svg>
  <span class="pill-solid">Already broken</span>
  <svg class="icon" viewBox="0 0 24 10" width="24" height="10" xmlns="http://www.w3.org/2000/svg"><line x1="2" y1="5" x2="18" y2="5" stroke="#822433" stroke-width="1.4" stroke-linecap="round"/><path d="M 16 2 L 22 5 L 16 8 Z" fill="#822433"/></svg>
  <span class="pill">Surface keeps widening</span>
</div>
