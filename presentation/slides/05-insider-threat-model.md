# Insider attackers bypass the defenses built for outsider eavesdroppers

<div class="threat-models">

  <div class="threat-panel">
    <div class="threat-title">(a) Outsider model</div>
    <div class="region region-public">
      <span class="region-label on-public">Public region</span>
      <div class="public-content">
        <div class="eavesdropper-badge">Eavesdropper</div>
        <div class="sniff-arrow">↓ &nbsp;sniffs</div>
      </div>
      <div class="region region-private">
        <span class="region-label on-private">Private region</span>
        <div class="devices">
          <span class="device device-trusted">AP<span class="device-sub">trusted</span></span>
          <span class="device device-trusted">IoT<span class="device-sub">trusted</span></span>
        </div>
        <div class="safe-caption-inline">Outsider blocked by fencing</div>
      </div>
    </div>
  </div>

  <div class="threat-panel">
    <div class="threat-title">(b) Insider model</div>
    <div class="region region-public">
      <span class="region-label on-public">Public region</span>
      <div class="public-content">
        <div class="no-outsider-note">— no outsider attacker —</div>
      </div>
      <div class="region region-private">
        <span class="region-label on-private">Private region</span>
        <div class="devices">
          <span class="device device-threat">AP<span class="device-sub">sensing you</span></span>
          <span class="device device-threat">IoT<span class="device-sub">sensing you</span></span>
        </div>
        <div class="threat-caption-inline">Trusted device = potential eavesdropper</div>
      </div>
    </div>
  </div>

</div>

<div class="verdicts">
  <div class="verdict verdict-ok">
    <svg class="icon" viewBox="0 0 16 16" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><path d="M 3.5 8 L 6.8 11.3 L 12.5 5" stroke="#822433" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
    <div class="text">Outsider — <strong>defended</strong> by fencing</div>
  </div>
  <div class="verdict verdict-bad">
    <svg class="icon" viewBox="0 0 16 16" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><line x1="4" y1="4" x2="12" y2="12" stroke="#822433" stroke-width="2.1" stroke-linecap="round"/><line x1="12" y1="4" x2="4" y2="12" stroke="#822433" stroke-width="2.1" stroke-linecap="round"/></svg>
    <div class="text">Insider — <strong>exposed</strong>, fencing useless</div>
  </div>
</div>

<div class="note insider-note">Prior Wi-Fi sensing attacks — <strong>WindTalker</strong> · <strong>Zhu et al.</strong> · <strong>Banerjee et al.</strong> — all target the outsider; the insider gap is WiShield's new concern.</div>
