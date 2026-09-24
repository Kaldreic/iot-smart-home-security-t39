# AirBugCatcher reproduces 75% of expected bugs across 5 devices

<div class="slide-tagline">5 devices · 3 protocols · 14 h 38 m total</div>

<div class="callout"><strong>5G NR</strong> leads at 93% expected reproduction, <strong>Bluetooth</strong> follows, and <strong>Wi-Fi</strong> is the hardest target (50%) — the paper attributes the gap to Wi-Fi's complex stateful protocol.</div>

<div class="results">
  <div>
    <div class="kicker">Table 4 — per-target results</div>
    <table class="tbl">
      <thead><tr><th>Target</th><th>Proto</th><th>Expected</th><th>Time</th></tr></thead>
      <tbody>
        <tr><td>OnePlus phone</td><td>5G NR</td><td>13 / 14 · <strong>93%</strong></td><td>2h 09</td></tr>
        <tr><td>ESP32-WROOM-32</td><td>BT</td><td>11 / 16 · 69%</td><td>6h 44</td></tr>
        <tr><td>Cypress Board</td><td>BT</td><td>4 / 6 · 67%</td><td>1h 26</td></tr>
        <tr><td>SIM8202G</td><td>5G NR</td><td>3 / 4 · 75%</td><td>1h 26</td></tr>
        <tr><td>ESP-WROVER-KIT</td><td>Wi-Fi</td><td>2 / 4 · <strong>50%</strong></td><td>2h 53</td></tr>
        <tr class="total"><td>Total</td><td>—</td><td>33 / 44 · 75%</td><td>14h 38</td></tr>
      </tbody>
    </table>
  </div>
  <div class="results-fig">
    <div class="kicker">Figure 6 — reproduction time</div>
    <img src="/slide15-fig6-reproduction-time.png" alt="Figure 6 from the AirBugCatcher paper: grouped bar chart showing distribution of expected bugs by reproduction time bucket (0-2, 2-4, 4-30, 30-60 minutes) across five target devices. OnePlus Phone (5G) dominates the 0-2 minute bucket with 9 bugs reproduced quickly." />
    <div class="subline">Bug count by reproduction time bucket (minutes)</div>
  </div>
</div>
