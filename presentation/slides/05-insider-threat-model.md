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

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; max-width: 54rem; margin: 1.1rem auto 0 auto; align-items: stretch;"><div style="display: flex; align-items: center; justify-content: center; gap: 0.55rem; padding: 0.5rem 0.9rem; border: 1.5px dashed rgba(130, 36, 51, 0.45); border-radius: 4px; background: var(--sapienza-red-soft);"><svg viewBox="0 0 16 16" width="14" height="14" xmlns="http://www.w3.org/2000/svg" style="flex-shrink: 0;"><path d="M 3.5 8 L 6.8 11.3 L 12.5 5" stroke="#822433" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg><div style="font-size: 0.8rem; color: var(--sapienza-ink); line-height: 1.35;">Outsider — <strong style="color: var(--sapienza-red);">defended</strong> by fencing</div></div><div style="display: flex; align-items: center; justify-content: center; gap: 0.55rem; padding: 0.5rem 0.9rem; border: 2px solid var(--sapienza-red); border-radius: 4px; background: #ffffff; box-shadow: 0 1px 4px rgba(130, 36, 51, 0.12);"><svg viewBox="0 0 16 16" width="14" height="14" xmlns="http://www.w3.org/2000/svg" style="flex-shrink: 0;"><line x1="4" y1="4" x2="12" y2="12" stroke="#822433" stroke-width="2.1" stroke-linecap="round"/><line x1="12" y1="4" x2="4" y2="12" stroke="#822433" stroke-width="2.1" stroke-linecap="round"/></svg><div style="font-size: 0.8rem; color: var(--sapienza-ink); line-height: 1.35;">Insider — <strong style="color: var(--sapienza-red);">exposed</strong>, fencing useless</div></div></div>

<div style="text-align: center; font-size: 0.72rem; color: var(--sapienza-muted); font-style: italic; margin: 0.6rem auto 0 auto; max-width: 54rem; letter-spacing: 0.02em;">Prior Wi-Fi sensing attacks — <strong style="color: var(--sapienza-red); font-style: normal;">WindTalker</strong> · <strong style="color: var(--sapienza-red); font-style: normal;">Zhu et al.</strong> · <strong style="color: var(--sapienza-red); font-style: normal;">Banerjee &amp; Zhu</strong> — all target the outsider; the insider gap is WiShield's new concern.</div>
