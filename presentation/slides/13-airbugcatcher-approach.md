# Bug Identification

<div class="slide-tagline">Group similar bugs together, even when log traces differ.</div>

<div class="split-label" style="text-align: center; margin-top: 0.3rem;">Failure types</div>

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; max-width: 36rem; margin: 0.2rem auto 0 auto;">

<div class="testcase-card" style="padding: 0.55rem 0.8rem;">
<svg viewBox="0 0 50 50" width="30" height="30" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 0.15rem;">
<path d="M 25 6 L 46 42 L 4 42 Z" fill="#ffffff" stroke="#822433" stroke-width="2.2" stroke-linejoin="round"/>
<line x1="25" y1="19" x2="25" y2="31" stroke="#822433" stroke-width="3" stroke-linecap="round"/>
<circle cx="25" cy="37" r="1.8" fill="#822433"/>
</svg>
<div class="testcase-title">Crash</div>
<div class="testcase-body">Directly seen in logs or packet traces.</div>
</div>

<div class="testcase-card" style="padding: 0.55rem 0.8rem;">
<svg viewBox="0 0 50 50" width="30" height="30" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 0.15rem;">
<circle cx="25" cy="25" r="17" fill="#faf5f6" stroke="#822433" stroke-width="1.8"/>
<line x1="25" y1="9" x2="25" y2="12" stroke="#822433" stroke-width="1.5"/>
<line x1="25" y1="38" x2="25" y2="41" stroke="#822433" stroke-width="1.5"/>
<line x1="9" y1="25" x2="12" y2="25" stroke="#822433" stroke-width="1.5"/>
<line x1="38" y1="25" x2="41" y2="25" stroke="#822433" stroke-width="1.5"/>
<path d="M 25 42 A 17 17 0 0 0 42 25" fill="none" stroke="#822433" stroke-width="1.5" stroke-dasharray="2 2" opacity="0.55"/>
<line x1="25" y1="25" x2="18" y2="20" stroke="#822433" stroke-width="2.2"/>
<line x1="25" y1="25" x2="25" y2="14" stroke="#822433" stroke-width="1.8"/>
<circle cx="25" cy="25" r="2" fill="#822433"/>
</svg>
<div class="testcase-title">Hang</div>
<div class="testcase-body">Detected via timeout on missing response.</div>
</div>

</div>

<div style="max-width: 38rem; margin: 0.5rem auto 0 auto;">

<div style="display: flex; justify-content: center;">
<div style="padding: 0.35rem 1rem; background: var(--sapienza-red); color: #ffffff; border-radius: 999px; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.04em;">Log available?</div>
</div>

<svg viewBox="0 0 400 28" preserveAspectRatio="none" style="width: 100%; height: 24px; display: block;" xmlns="http://www.w3.org/2000/svg">
<line x1="200" y1="0" x2="200" y2="10" stroke="#822433" stroke-width="2"/>
<line x1="100" y1="10" x2="300" y2="10" stroke="#822433" stroke-width="2"/>
<line x1="100" y1="10" x2="100" y2="24" stroke="#822433" stroke-width="2"/>
<line x1="300" y1="10" x2="300" y2="24" stroke="#822433" stroke-width="2"/>
<polygon points="100,27 95,21 105,21" fill="#822433"/>
<polygon points="300,27 295,21 305,21" fill="#822433"/>
</svg>

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 3rem;">
<div style="text-align: center; padding: 0.45rem 0.8rem; border: 2px solid var(--sapienza-red); border-radius: 6px; background: #ffffff; box-shadow: 0 1px 3px rgba(130, 36, 51, 0.1);">
<div style="font-size: 0.66rem; color: var(--sapienza-red); font-weight: 700; text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 0.15rem;">Yes · with log</div>
<div style="font-size: 0.78rem; color: var(--sapienza-ink); line-height: 1.3;">Source-code line + memory trace</div>
</div>
<div style="text-align: center; padding: 0.45rem 0.8rem; border: 2px dashed var(--sapienza-red); border-radius: 6px; background: #faf5f6; box-shadow: 0 1px 3px rgba(130, 36, 51, 0.08);">
<div style="font-size: 0.66rem; color: var(--sapienza-red); font-weight: 700; text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 0.15rem;">No · fallback</div>
<div style="font-size: 0.78rem; color: var(--sapienza-ink); line-height: 1.3;">Packet state before crash</div>
</div>
</div>

</div>

<div style="max-width: 26rem; margin: 0.55rem auto 0 auto; background: var(--sapienza-red-soft); border: 1px solid rgba(130, 36, 51, 0.35); border-radius: 6px; padding: 0.5rem 0.8rem; box-shadow: 0 1px 3px rgba(130, 36, 51, 0.08);">
<div style="font-size: 0.64rem; color: var(--sapienza-red); font-weight: 700; text-transform: uppercase; letter-spacing: 0.16em; margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.4rem;"><span style="font-family: 'Menlo', 'Monaco', monospace; font-weight: 500; letter-spacing: 0;">›_</span>Example log trace</div>
<pre style="margin: 0; font-size: 0.72rem; color: var(--sapienza-ink); line-height: 1.45; font-family: 'Menlo', 'Monaco', 'Courier New', monospace; white-space: pre;">BugID1=<span style="background: rgba(130, 36, 51, 0.18); padding: 0 0.15em; border-radius: 2px;">0x40101311</span>:0x3ffcc170
       <span style="background: rgba(130, 36, 51, 0.18); padding: 0 0.15em; border-radius: 2px;">0x4001a637</span>:0x3ffcc190...
BugID2=<span style="background: rgba(130, 36, 51, 0.18); padding: 0 0.15em; border-radius: 2px;">0x40101311</span>:0x3ffcc580
       <span style="background: rgba(130, 36, 51, 0.18); padding: 0 0.15em; border-radius: 2px;">0x4001a637</span>:0x3ffcc5a0...</pre>
</div>

<div style="max-width: 30rem; margin: 0.4rem auto 0 auto; text-align: center; font-size: 0.73rem; color: var(--sapienza-muted); font-style: italic; line-height: 1.4;">Highlighted addresses match across different offsets — <strong style="color: var(--sapienza-red); font-style: normal;">same root cause, one group</strong>.</div>
