# Introduction to fuzzing and the IoT challenge

<div class="split-cards">
<div class="split-card">
<div class="split-label">What is fuzzing?</div>
<div class="split-text">An automated security technique that injects malformed input to trigger crashes, memory leaks, or hangs.</div>
</div>
<div class="split-card">
<div class="split-label">What is a PoC?</div>
<div class="split-text">A minimal packet sequence that reliably reproduces a bug — packaged as ready-to-run code for the vendor.</div>
</div>
</div>

<div class="slide-tagline">OTA fuzzing has already uncovered anomalies on commercial IoT radios:</div>

<div class="devices" style="margin: 0.4rem auto 0.9rem auto;">
<div class="device"><svg viewBox="0 0 32 32" width="18" height="18" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 0.2rem;"><path d="M 8 10 L 24 22 L 16 28 L 16 4 L 24 10 L 8 22" fill="none" stroke="#822433" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>Bluetooth</div>
<div class="device"><svg viewBox="0 0 32 32" width="18" height="18" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 0.2rem;"><rect x="4" y="20" width="4" height="8" fill="#822433" rx="0.5"/><rect x="11" y="15" width="4" height="13" fill="#822433" rx="0.5"/><rect x="18" y="10" width="4" height="18" fill="#822433" rx="0.5"/><rect x="25" y="5" width="4" height="23" fill="#822433" rx="0.5"/></svg>5G NR</div>
<div class="device"><svg viewBox="0 0 32 32" width="18" height="18" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 0.2rem;"><path d="M 4 12 A 14 14 0 0 1 28 12" fill="none" stroke="#822433" stroke-width="2" stroke-linecap="round"/><path d="M 8 17 A 10 10 0 0 1 24 17" fill="none" stroke="#822433" stroke-width="2" stroke-linecap="round"/><path d="M 12 22 A 6 6 0 0 1 20 22" fill="none" stroke="#822433" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="27" r="2" fill="#822433"/></svg>Wi-Fi</div>
</div>

<div class="paper-fig-container" style="max-width: 44rem;"><img src="/slide11-fig3-overview.png" alt="Figure 3 from the AirBugCatcher paper: four-step horizontal overview — (1) Initial Setup with Over-the-Air Fuzzer and target; (2) Attack Vector Selection with log and packet analysis driven by filtering rules; (3) Minimal Bug Reproduction with test case generation and target log; (4) Root Cause Report with bug artefacts (hang, crash, flooding) and logs/code outputs." class="paper-fig-image" style="max-width: 100%;" /><div class="paper-fig-attrib">AirBugCatcher, Figure 3 — 4-step pipeline · Setup → Analysis → Reproduction → Report</div></div>
