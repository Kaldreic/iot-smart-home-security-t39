# AirBugCatcher's limits mark three open research paths

<div class="slide-tagline">Each shortcoming opens a concrete research direction</div>

<div class="three-up">
  <div class="path-card">
    <div class="card-body">
      <div class="hbox">
        <span class="step">1</span>
        <span class="step-title">Manual filter rules</span>
      </div>
      <div class="text">Users must hand-author packet-filter rules that encode the protocol standard — non-trivial and error-prone.</div>
    </div>
    <div class="card-foot">
      <svg class="icon" viewBox="0 0 18 18" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7.5" fill="#ffffff" stroke="#822433" stroke-width="1.4"/><line x1="5" y1="9" x2="11" y2="9" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="10,6.5 13.5,9 10,11.5" fill="#822433"/></svg>
      <div>
        <div class="kicker">Research path</div>
        <div class="text">Automate filter synthesis from protocol specs — grammar-driven or LLM-assisted parsing.</div>
      </div>
    </div>
  </div>
  <div class="path-card">
    <div class="card-body">
      <div class="hbox">
        <span class="step">2</span>
        <span class="step-title">Firmware lock-in</span>
      </div>
      <div class="text">Target firmware must match between fuzzing and reproduction — any version drift breaks the PoC.</div>
    </div>
    <div class="card-foot">
      <svg class="icon" viewBox="0 0 18 18" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7.5" fill="#ffffff" stroke="#822433" stroke-width="1.4"/><line x1="5" y1="9" x2="11" y2="9" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="10,6.5 13.5,9 10,11.5" fill="#822433"/></svg>
      <div>
        <div class="kicker">Research path</div>
        <div class="text">Version-invariant bug descriptors that survive firmware updates and port across devices.</div>
      </div>
    </div>
  </div>
  <div class="path-card">
    <div class="card-body">
      <div class="hbox">
        <span class="step">3</span>
        <span class="step-title">Closed-source grouping</span>
      </div>
      <div class="text">Without source code or target logs, bug identifiers fall back to packet state — FP and FN are unavoidable.</div>
    </div>
    <div class="card-foot">
      <svg class="icon" viewBox="0 0 18 18" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7.5" fill="#ffffff" stroke="#822433" stroke-width="1.4"/><line x1="5" y1="9" x2="11" y2="9" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="10,6.5 13.5,9 10,11.5" fill="#822433"/></svg>
      <div>
        <div class="kicker">Research path</div>
        <div class="text">Differential or side-channel analysis to confirm truly unique bugs without source access.</div>
      </div>
    </div>
  </div>
</div>

<div class="diagram-caption">Three honest limits — <strong>three open research directions, expanded in the companion report</strong>.</div>
