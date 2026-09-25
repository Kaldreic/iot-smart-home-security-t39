# Bug Identification

<div class="slide-tagline">Group similar bugs together, even when log traces differ.</div>

<div class="split-label centered" style="margin-top: 0.3rem;">Failure types</div>

<div class="failure-grid">

<div class="testcase-card">
<svg viewBox="0 0 50 50" width="30" height="30" xmlns="http://www.w3.org/2000/svg">
<path d="M 25 6 L 46 42 L 4 42 Z" fill="#ffffff" stroke="#822433" stroke-width="2.2" stroke-linejoin="round"/>
<line x1="25" y1="19" x2="25" y2="31" stroke="#822433" stroke-width="3" stroke-linecap="round"/>
<circle cx="25" cy="37" r="1.8" fill="#822433"/>
</svg>
<div class="testcase-title">Crash</div>
<div class="testcase-body">Directly seen in logs or packet traces.</div>
</div>

<div class="testcase-card">
<svg viewBox="0 0 50 50" width="30" height="30" xmlns="http://www.w3.org/2000/svg">
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

<div class="decision-tree">

<div class="decision-root">
<div class="decision">Log available?</div>
</div>

<svg viewBox="0 0 400 28" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
<line x1="200" y1="0" x2="200" y2="10" stroke="#822433" stroke-width="2"/>
<line x1="100" y1="10" x2="300" y2="10" stroke="#822433" stroke-width="2"/>
<line x1="100" y1="10" x2="100" y2="24" stroke="#822433" stroke-width="2"/>
<line x1="300" y1="10" x2="300" y2="24" stroke="#822433" stroke-width="2"/>
<polygon points="100,27 95,21 105,21" fill="#822433"/>
<polygon points="300,27 295,21 305,21" fill="#822433"/>
</svg>

<div class="branches">
<div class="branch">
<div class="kicker">Yes · with log</div>
<div class="text">Source-code line + memory trace</div>
</div>
<div class="branch fallback">
<div class="kicker">No · fallback</div>
<div class="text">Packet state before crash</div>
</div>
</div>

</div>

<div class="log-box">
<div class="kicker"><span class="prompt">›_</span>Example log trace</div>
<pre class="log">BugID1=<span class="hl">0x40101311</span>:0x3ffcc170
       <span class="hl">0x4001a637</span>:0x3ffcc190...
BugID2=<span class="hl">0x40101311</span>:0x3ffcc580
       <span class="hl">0x4001a637</span>:0x3ffcc5a0...</pre>
</div>

<div class="note log-note">Highlighted addresses match across different offsets — <strong>same root cause, one group</strong>.</div>
