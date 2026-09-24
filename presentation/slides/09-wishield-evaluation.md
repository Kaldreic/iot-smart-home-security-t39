# WiShield defeats both motion detection and AoA estimation attacks

<div class="validation-grid">
<div class="validation-col">
<div class="validation-heading">Amplitude · <span class="math-notation">σ̄<sub>CSI<sub>a</sub></sub></span> motion detector</div>
<img src="/slide09-fig9-motion-validation.png" class="validation-image" alt="Figure 9 from the WiShield paper: (a) without WiShield, the σ̄ CSI-a threshold cleanly separates motion from idle; (b) with WiShield, the threshold jumps to 10.17 and idle/motion curves overlap — no threshold works." />
<div class="paper-fig-attrib">WiShield, Figure 9</div>
<div class="validation-note">
<strong>(a) Without:</strong> σ̄<sub>CSI<sub>a</sub></sub> spikes in motion (red), flat in idle (black); threshold cleanly divides them.<br/>
<strong>(b) With:</strong> idle lifted, threshold jumps to 10.17 — curves overlap, no threshold works.
</div>
</div>
<div class="validation-col">
<div class="validation-heading">Phase · SpotFi AoA estimation</div>
<img src="/slide09-fig13-phase-aoa-validation.png" class="validation-image" alt="Figure 13 from the WiShield paper: phase difference (a) and AoA (b) are stable until t=5s; after WiShield activates, the phase difference scatters uniformly over (−π, π) and the AoA spreads over (−90°, 90°), concentrating around 0°." />
<div class="paper-fig-attrib">WiShield, Figure 13</div>
<div class="validation-note">
<strong>0 – 5 s (off):</strong> static target, phase and AoA clean flat lines.<br/>
<strong>After 5 s (on):</strong> phase scatters (−π, π), AoA scatters (−90°, 90°).
</div>
</div>
</div>

<div class="rule-line"><div class="rule"></div><div class="rule-text">Both state-of-the-art sensing attacks <strong>defeated</strong> · quantitatively and visibly</div><div class="rule"></div></div>
