# Template-based amplitude obfuscation beats random noise

<div class="mechanism-row">
<div class="mech-chip"><div class="mech-chip-title">1 · Template</div><div class="mech-chip-sub">from stored motion samples</div></div>
<div class="mech-arrow">→</div>
<div class="mech-chip"><div class="mech-chip-title">2 · Scale</div><div class="mech-chip-sub">random factor</div></div>
<div class="mech-arrow">→</div>
<div class="mech-chip"><div class="mech-chip-title">3 · Noise</div><div class="mech-chip-sub">added stochastically</div></div>
<div class="mech-arrow">→</div>
<div class="mech-chip"><div class="mech-chip-title">4 · Timing</div><div class="mech-chip-sub">randomized interval</div></div>
</div>

<div class="paper-fig-container"><img src="/slide07-fig5-amplitude-traces.png" alt="Figure 5 from the WiShield paper: (a) amplitude fluctuation caused by real motion; (b) amplitude fluctuation caused by WiShield — visually indistinguishable." class="paper-fig-image" /><div class="paper-fig-attrib">WiShield, Figure 5 — (a) real motion · (b) WiShield template, visually indistinguishable</div></div>

<div style="max-width: 50rem; margin: 0.8rem auto 0 auto; text-align: center; font-size: 0.85rem; color: var(--sapienza-ink); font-style: italic; line-height: 1.45;">In (b), <strong style="color: var(--sapienza-red); font-style: normal;">no human is in the room</strong> — yet the attacker's variance-based detector (σ̄<sub>CSI<sub>a</sub></sub>) reads the same signature as real motion.</div>
