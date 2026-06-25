# Per-antenna phase switching hides multi-antenna correlation

<div class="phase-layout">
<div class="phase-figure">
<img src="/slide08-fig6-phase-shifter.png" alt="Figure 6 from the WiShield paper: Per-antenna Phase Shifter Design. Two 1→2 switches and four 1→4 switches route the signal through one of eight sub-paths of different lengths." class="paper-fig-image" />
<div class="paper-fig-attrib">WiShield, Figure 6 — 8-step per-antenna phase shifter</div>
</div>
<div class="phase-notes">
<div class="phase-note-header">Key properties</div>
<div class="phase-note-item"><span class="phase-note-num">8</span><span class="phase-note-text">sub-path lengths, selectable per packet</span></div>
<div class="phase-note-item"><span class="phase-note-num">2π</span><span class="phase-note-text">phase shift uniform, modulo</span></div>
<div class="phase-note-item"><span class="phase-note-num">×N</span><span class="phase-note-text">independent circuits — one per antenna</span></div>
</div>
</div>

<div style="text-align: center; margin: 1rem auto 0 auto; max-width: 54rem;"><div style="font-size: 0.62rem; color: var(--sapienza-red); font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase; margin-bottom: 0.35rem;">Why it defeats AoA</div><div style="font-size: 0.88rem; color: var(--sapienza-ink); line-height: 1.5;">The phase-difference pattern across antennas is the <strong style="color: var(--sapienza-red);">only signal AoA estimation has</strong> — per-antenna independence destroys it.</div></div>
