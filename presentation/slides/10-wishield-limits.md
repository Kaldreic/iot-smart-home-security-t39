# Amplitude obfuscation costs PER; phase is free; templates don't last forever

<div class="limits-layout">
<div class="limits-figure">
<img src="/slide10-fig16-per-mcs.png" class="paper-fig-image" alt="Figure 16 from the WiShield paper: Packet Error Rate (PER) vs MCS index across four configurations — antenna baseline, idle WiShield, active WiShield (Run), and Run+Idle intermittent activation — showing Run raises PER, Run+Idle is close to baseline." />
<div class="paper-fig-attrib">WiShield, Figure 16 — PER vs MCS · four configurations (<em>antenna · idle · run · run + idle</em>) on SISO + MIMO</div>
</div>
<div class="limits-cards">
<div class="limit-card">
<div class="limit-title">1 · Communication cost</div>
<div class="limit-body">Amplitude attenuation raises PER (<em>Run</em> line). Intermittent <em>Run + Idle</em> brings it back near baseline. Phase obfuscation: almost free.</div>
</div>
<div class="limit-card">
<div class="limit-title">2 · No forward secrecy</div>
<div class="limit-body">Templates are ROM-stored, finite. Long enough observation lets the adversary tell fake fluctuations from real motion. Paper suggests cGAN.</div>
</div>
<div class="limit-card">
<div class="limit-title">3 · Binary + bolt-on</div>
<div class="limit-body">Sensing vs obfuscation is all-or-nothing — no per-service policy. Needs an RF-port-accessible NIC; not every vendor allows it.</div>
</div>
</div>
</div>

<div class="diagram-caption">Three honest limits — <strong>three open research directions</strong>.</div>
