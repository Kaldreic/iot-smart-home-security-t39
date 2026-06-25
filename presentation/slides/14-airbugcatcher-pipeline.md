# Attack Strategies: Technique of disturbance

<div class="slide-tagline">How does AirBugCatcher trigger a crash?</div>

<div class="testcase-grid">
<div class="testcase-card">
<div class="testcase-num">1</div>
<div class="testcase-title">Malformed packet</div>
<div class="testcase-body">Overwrite target bytes of a captured packet.</div>
</div>
<div class="testcase-card">
<div class="testcase-num">2</div>
<div class="testcase-title">Replay</div>
<div class="testcase-body">Retransmit a captured packet unchanged.</div>
</div>
<div class="testcase-card">
<div class="testcase-num">3</div>
<div class="testcase-title">Flooding</div>
<div class="testcase-body">Continuously repeat the same packet.</div>
</div>
</div>

<div style="max-width: 54rem; margin: 0.9rem auto 0 auto; display: flex; flex-direction: column; gap: 0.45rem;">
<div style="padding: 0.6rem 1rem 0.75rem 1rem; border-left: 3px solid var(--sapienza-red); background: var(--sapienza-red-soft); border-radius: 0 4px 4px 0;">
<div style="font-size: 0.7rem; color: var(--sapienza-red); font-weight: 700; text-transform: uppercase; letter-spacing: 0.16em; margin-bottom: 0.6rem;">Feedback</div>
<div style="display: flex; align-items: center; justify-content: center; gap: 0.4rem; font-size: 0.78rem;"><span style="padding: 0.25rem 0.65rem; border: 1px solid var(--sapienza-red); border-radius: 3px; background: #ffffff; color: var(--sapienza-ink); flex-shrink: 0;">Run</span><svg viewBox="0 0 22 10" width="22" height="10" xmlns="http://www.w3.org/2000/svg" style="flex-shrink: 0;"><line x1="2" y1="5" x2="16" y2="5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="15,2 20,5 15,8" fill="#822433"/></svg><span style="padding: 0.25rem 0.65rem; border: 1px solid var(--sapienza-red); border-radius: 3px; background: #ffffff; color: var(--sapienza-ink); flex-shrink: 0;">Target</span><svg viewBox="0 0 22 10" width="22" height="10" xmlns="http://www.w3.org/2000/svg" style="flex-shrink: 0;"><line x1="2" y1="5" x2="16" y2="5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="15,2 20,5 15,8" fill="#822433"/></svg><span style="padding: 0.25rem 0.65rem; border: 1px solid var(--sapienza-red); border-radius: 3px; background: #ffffff; color: var(--sapienza-ink); flex-shrink: 0;">Logs + behaviour</span><svg viewBox="0 0 22 10" width="22" height="10" xmlns="http://www.w3.org/2000/svg" style="flex-shrink: 0;"><line x1="2" y1="5" x2="16" y2="5" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="15,2 20,5 15,8" fill="#822433"/></svg><span style="padding: 0.25rem 0.75rem; border: 1px solid var(--sapienza-red); border-radius: 3px; background: var(--sapienza-red); color: #ffffff; font-weight: 600; flex-shrink: 0;">Bug ID match?</span><svg viewBox="0 0 40 60" width="40" height="60" xmlns="http://www.w3.org/2000/svg" style="flex-shrink: 0;"><line x1="0" y1="30" x2="16" y2="30" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><line x1="16" y1="14" x2="16" y2="46" stroke="#822433" stroke-width="1.5"/><line x1="16" y1="14" x2="33" y2="14" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="32,11 37,14 32,17" fill="#822433"/><line x1="16" y1="46" x2="33" y2="46" stroke="#822433" stroke-width="1.5" stroke-linecap="round"/><polygon points="32,43 37,46 32,49" fill="#822433"/></svg><div style="display: flex; flex-direction: column; gap: 0.4rem; flex-shrink: 0;"><div style="display: flex; align-items: center; gap: 0.4rem;"><span style="color: var(--sapienza-red); font-weight: 700; letter-spacing: 0.1em; font-size: 0.62rem; width: 1.5rem; text-align: center; flex-shrink: 0;">YES</span><span style="padding: 0.15rem 0.5rem; border: 1px solid var(--sapienza-red); border-radius: 3px; background: #faf5f6; color: var(--sapienza-ink); font-size: 0.74rem; flex-shrink: 0;">Reproduced <strong style="color: var(--sapienza-red); font-weight: 700;">✓</strong></span></div><div style="display: flex; align-items: center; gap: 0.4rem;"><span style="color: var(--sapienza-red); font-weight: 700; letter-spacing: 0.1em; font-size: 0.62rem; width: 1.5rem; text-align: center; flex-shrink: 0;">NO</span><span style="padding: 0.15rem 0.5rem; border: 1px dashed var(--sapienza-red); border-radius: 3px; background: #faf5f6; color: var(--sapienza-ink); font-size: 0.74rem; display: inline-flex; align-items: center; gap: 0.3rem; flex-shrink: 0;">Timeout → retry<svg viewBox="0 0 14 14" width="11" height="11" xmlns="http://www.w3.org/2000/svg" style="flex-shrink: 0;"><circle cx="7" cy="7" r="5.5" fill="none" stroke="#822433" stroke-width="1.3"/><line x1="7" y1="7" x2="7" y2="3.6" stroke="#822433" stroke-width="1.3" stroke-linecap="round"/><line x1="7" y1="7" x2="10" y2="7" stroke="#822433" stroke-width="1.3" stroke-linecap="round"/></svg></span></div></div></div>
</div>
<div style="display: grid; grid-template-columns: 6.5rem 1fr; gap: 0.9rem; align-items: center; padding: 0.5rem 1rem; border-left: 3px solid var(--sapienza-red); background: var(--sapienza-red-soft); border-radius: 0 4px 4px 0;">
<span class="evidence-protocol">Caveat</span>
<div style="display: flex; align-items: center; gap: 0.55rem; font-size: 0.78rem; flex-wrap: wrap;">
<svg viewBox="0 0 18 16" width="18" height="16" xmlns="http://www.w3.org/2000/svg" style="flex-shrink: 0;"><path d="M 9 2 L 17 14 L 1 14 Z" fill="#ffffff" stroke="#822433" stroke-width="1.5" stroke-linejoin="round"/><line x1="9" y1="6" x2="9" y2="10.5" stroke="#822433" stroke-width="1.6" stroke-linecap="round"/><circle cx="9" cy="12.3" r="0.85" fill="#822433"/></svg>
<span style="padding: 0.15rem 0.55rem; border: 1px solid var(--sapienza-red); border-radius: 3px; background: #ffffff; color: var(--sapienza-ink);"><strong style="color: var(--sapienza-red); font-weight: 700; letter-spacing: 0.05em;">FP</strong> · same bug, different IDs</span>
<span style="padding: 0.15rem 0.55rem; border: 1px solid var(--sapienza-red); border-radius: 3px; background: #ffffff; color: var(--sapienza-ink);"><strong style="color: var(--sapienza-red); font-weight: 700; letter-spacing: 0.05em;">FN</strong> · different bugs, same ID</span>
</div>
</div>
</div>
