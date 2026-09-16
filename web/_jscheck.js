// кросс-валидация JS-движка против Python на одних и тех же данных (/tmp/px.json)
const E = require("./live_engine.js");
const fs = require("fs");
const d = JSON.parse(fs.readFileSync("/tmp/px.json", "utf8"));
const mk = a => a.map(x => ({ t: x[0], o: x[1], h: x[2], l: x[3], c: x[4] }));
const r = E.decide(mk(d.m15), mk(d.d1), mk(d.h1));
console.log("JS pivots_confirmed:", r.pivots.length, "| active:",
  r.structure ? [r.structure.kind, r.structure.direction, +r.structure.invalidation.toFixed(2), r.structure.as_of] : null);
console.log("JS donchian_hi:", +r.donchian.hi.toFixed(2), "| d1 close:", +r.d1.close.toFixed(2),
  "ema200:", +r.d1.ema200.toFixed(2), "bull:", r.d1.bull);
console.log("JS close:", +r.close.toFixed(2), "atr:", +r.atr.toFixed(3));
console.log("JS decision:", r.decision, "| state:", r.state, "| branch:", r.branch);
console.log("JS reasons:", r.reasons.join(" | "));
if (r.scenario) console.log("JS scenario primary:", JSON.stringify({
  trigger: +r.scenario.primary.trigger.toFixed(2), sl: +r.scenario.primary.sl.toFixed(2),
  tp: +r.scenario.primary.tp.toFixed(2), inv: +r.scenario.primary.invalidation.toFixed(2),
  w5: r.scenario.primary.w5_target ? +r.scenario.primary.w5_target.toFixed(2) : null,
  cost_r: +r.scenario.primary.cost_r.toFixed(4) }));
