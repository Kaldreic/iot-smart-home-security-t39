# Introducing AirBugCatcher

<div class="slide-tagline">A systematic process to reproduce wireless anomalies on IoT devices.</div>

<div class="split-label centered" style="margin-top: 0.6rem;">Workflow</div>

<div class="mechanism-row" style="margin-top: 0.3rem;">
<div class="mech-chip"><div class="mech-chip-title">1 · Data gathering</div></div>
<div class="mech-arrow">→</div>
<div class="mech-chip"><div class="mech-chip-title">2 · Packet analysis</div></div>
<div class="mech-arrow">→</div>
<div class="mech-chip"><div class="mech-chip-title">3 · Code generation (PoC)</div></div>
<div class="mech-arrow">→</div>
<div class="mech-chip"><div class="mech-chip-title">4 · Final report</div></div>
</div>

<div class="split-label centered" style="margin-top: 0.8rem;">Methodology</div>

<div class="methods">
<div class="direction-row compact">
<div class="direction-label">Offline analysis</div>
</div>
<div class="direction-row compact">
<div class="direction-label">OTA reproduction</div>
</div>
</div>

<div class="paper-fig-container fig-fill" style="margin-top: 0.7rem;">
  <img src="/slide12-fig5-test-cases.png" alt="Figure 5 from the AirBugCatcher paper: test case generation for (a) mutated packets and (b) replayed packets. Each row shows three panels — packet filtering rule (JSON), packet trace with byte offsets highlighted, and the generated test case in C++." class="paper-fig-image" />
  <div class="paper-fig-attrib">AirBugCatcher, Figure 5 — test case generation · (a) Mutated packet · (b) Replayed packet</div>
</div>
