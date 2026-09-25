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

<div class="paper-fig-container">
  <img src="/slide07-fig5-amplitude-traces.png" alt="Figure 5 from the WiShield paper: (a) amplitude fluctuation caused by real motion; (b) amplitude fluctuation caused by WiShield, similar to the real case." class="paper-fig-image" />
  <div class="paper-fig-attrib">WiShield, Figure 5 — (a) real motion · (b) WiShield template, similar to the real case</div>
</div>

<div class="note fig-note">In (b), <strong>no human is in the room</strong> — yet the attacker's variance-based detector (σ̄<sub>CSI<sub>a</sub></sub>) reads the same signature as real motion.</div>
