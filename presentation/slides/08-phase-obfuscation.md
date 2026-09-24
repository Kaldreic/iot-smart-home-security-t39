# Per-antenna phase switching hides multi-antenna correlation

<div class="phase-layout">
<div class="phase-figure">
<img src="/slide08-fig6-phase-shifter.png" alt="Figure 6 from the WiShield paper: Per-antenna Phase Shifter Design. Two 1→2 switches and four 1→4 switches route the signal through one of eight sub-paths of different lengths." class="paper-fig-image" />
<div class="paper-fig-attrib">WiShield, Figure 6 — 8-step per-antenna phase shifter</div>
</div>
<div class="phase-notes">
<div class="phase-note-header">Key properties</div>
<div class="phase-note-item"><span class="phase-note-num">8</span><span class="phase-note-text">sub-path lengths, switched at least every 10 ms</span></div>
<div class="phase-note-item"><span class="phase-note-num">2π</span><span class="phase-note-text">phase shift uniform modulo 2π</span></div>
<div class="phase-note-item"><span class="phase-note-num">×N</span><span class="phase-note-text">independent circuits — one per antenna</span></div>
</div>
</div>

<div class="aoa-why">
  <div class="kicker">Why it defeats AoA</div>
  <div class="text">The phase-difference pattern across antennas is the <strong>only signal AoA estimation has</strong> — per-antenna independence destroys it.</div>
</div>
