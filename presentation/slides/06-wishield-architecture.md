# WiShield hooks between WNIC and antenna to rewrite the signal

<div class="wishield-arch">
<div class="arch-row">
<div class="arch-block arch-endpoint">
<svg class="antenna-icon" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg"><path d="M 8 12 Q 20 2 32 12" fill="none" stroke="#822433" stroke-width="2"/><path d="M 12 18 Q 20 12 28 18" fill="none" stroke="#822433" stroke-width="2"/><line x1="20" y1="18" x2="20" y2="32" stroke="#822433" stroke-width="2"/><polygon points="15,32 25,32 22,36 18,36" fill="#822433"/></svg>
<div class="arch-label">Antenna</div>
</div>
<div class="arch-arrow"></div>
<div class="arch-block">
<div class="arch-title">Amplitude Obfuscator</div>
<div class="arch-inside arch-pills">
<span class="arch-pill">Variable<br/>Attenuator</span>
<span class="arch-pill">Amplifier</span>
</div>
<div class="arch-hw">PE43713 · SBB5089</div>
</div>
<div class="arch-arrow"></div>
<div class="arch-block">
<div class="arch-title">Phase Obfuscator</div>
<div class="arch-inside">
<svg class="phase-paths" viewBox="0 0 160 80" xmlns="http://www.w3.org/2000/svg"><rect x="4" y="6" width="3.5" height="66" fill="#822433" rx="1.5"/><rect x="152.5" y="6" width="3.5" height="66" fill="#822433" rx="1.5"/><path d="M 10 15 L 152 15" stroke="#822433" stroke-width="1.4" fill="none"/><path d="M 10 32 Q 55 22 80 32 Q 105 42 152 32" stroke="#822433" stroke-width="1.4" fill="none"/><path d="M 10 48 Q 40 32 60 48 Q 80 64 100 48 Q 120 32 152 48" stroke="#822433" stroke-width="1.4" fill="none"/><path d="M 10 65 Q 22 55 34 65 Q 46 75 58 65 Q 70 55 82 65 Q 94 75 106 65 Q 118 55 130 65 Q 142 75 152 65" stroke="#822433" stroke-width="1.4" fill="none"/></svg>
</div>
<div class="arch-hw">HMC849 · HMC7992</div>
</div>
<div class="arch-arrow"></div>
<div class="arch-block arch-endpoint">
<svg class="antenna-icon" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg"><rect x="10" y="12" width="20" height="16" fill="#ffffff" stroke="#822433" stroke-width="2" rx="1"/><line x1="10" y1="16" x2="6" y2="16" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="10" y1="20" x2="6" y2="20" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="10" y1="24" x2="6" y2="24" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="30" y1="16" x2="34" y2="16" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="30" y1="20" x2="34" y2="20" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="30" y1="24" x2="34" y2="24" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><circle cx="13.5" cy="15.5" r="0.9" fill="#822433"/></svg>
<div class="arch-label arch-label-big">WNIC</div>
<div class="arch-sub">Intel 5300</div>
</div>
</div>
<div class="arch-controller">
<div class="ctrl-box">Controller + user policy</div>
<div class="ctrl-hint"><span class="ctrl-arrow-glyph">↑</span> GPIO control signals to both obfuscators</div>
</div>
</div>

<div class="callout" style="max-width: 58rem; margin-top: 1rem;">Signal flow <strong>antenna → amplitude → phase → WNIC</strong>. The phase obfuscator routes the signal through one of eight switched sub-paths, switching at least every 10 ms when the channel is free (two 1→2 and four 1→4 switches) — different lengths produce different propagation delays.</div>
