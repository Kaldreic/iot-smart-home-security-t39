# Introducing AirBugCatcher

<div class="slide-tagline">A systematic process to reproduce wireless anomalies on IoT devices.</div>

<div class="split-label" style="text-align: center; margin-top: 0.6rem;">Workflow</div>

<div class="mechanism-row" style="margin-top: 0.3rem;">
<div class="mech-chip"><div class="mech-chip-title">1 · Data gathering</div></div>
<div class="mech-arrow">→</div>
<div class="mech-chip"><div class="mech-chip-title">2 · Packet analysis</div></div>
<div class="mech-arrow">→</div>
<div class="mech-chip"><div class="mech-chip-title">3 · Code generation (PoC)</div></div>
<div class="mech-arrow">→</div>
<div class="mech-chip"><div class="mech-chip-title">4 · Final report</div></div>
</div>

<div class="split-label" style="text-align: center; margin-top: 0.8rem;">Methodology</div>

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.9rem; max-width: 28rem; margin: 0.3rem auto 0 auto;">
<div class="direction-row" style="padding: 0.5rem 0.9rem; justify-content: center;">
<div class="direction-label" style="margin-bottom: 0;">Offline analysis</div>
</div>
<div class="direction-row" style="padding: 0.5rem 0.9rem; justify-content: center;">
<div class="direction-label" style="margin-bottom: 0;">OTA reproduction</div>
</div>
</div>

<div class="paper-fig-container" style="max-width: 36rem; margin-top: 0.7rem;"><img src="/slide12-fig5-test-cases.png" alt="Figure 5 from the AirBugCatcher paper: test case generation for (a) mutated packets and (b) replayed packets. Each row shows three panels — packet filtering rule (JSON), packet trace with byte offsets highlighted, and the generated test case in C++." class="paper-fig-image" style="max-width: 100%;" /><div class="paper-fig-attrib">AirBugCatcher, Figure 5 — test case generation · (a) Mutated packet · (b) Replayed packet</div></div>
