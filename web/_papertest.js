// тест paper.js: открытие, закрытие по TP/SL/SL-first/invalidation/time/manual, классификация, статистика
const P = require("./paper.js");
let pass = 0, fail = 0;
function chk(name, cond) { if (cond) { pass++; console.log("  PASS", name); } else { fail++; console.log("  FAIL", name); } }
function bar(t, o, h, l, c) { return { t, o, h, l, c, v: 1 }; }
const R = 25;
function sig(entry) {
  return { decision: "LONG", branch: "B02", structure: { w3_class: "B" },
    scenario: { primary: { sl: entry - R, tp: entry + R, r_usd: R, invalidation: entry - 30, cost_r: 0.52 / R } } };
}
const WAIT = { decision: "WAIT" };

// A) сигнал → pending → open на open следующего ЗАКРЫТОГО бара
let st = { pending: null, open: null, closed: [], log: [] };
let bars = [bar(1, 100, 101, 99, 100), bar(2, 100, 102, 99, 101), bar(3, 101, 102, 100, 101.5), bar(4, 101.5, 102, 101, 101.8)];
P.onTick(st, bars, sig(101.5), 1000);
chk("A1 signal → pending", !!st.pending && !st.open);
bars.push(bar(5, 101.8, 102.2, 101.5, 102));
P.onTick(st, bars, WAIT, 2000);
chk("A2 open = open бара signal+1", st.open && Math.abs(st.open.entry - bars[3].o) < 1e-9);

// B) TP: бар с high ≥ tp становится закрытым → выход по tp
const tp = st.open.tp;
bars.push(bar(6, 102, tp + 1, 101.9, tp + 0.5));   // TP-бар (пока формирующийся)
P.onTick(st, bars, WAIT, 3000);
chk("B1 формирующийся TP-бар не закрывает сделку", st.open !== null);
bars.push(bar(7, tp + 0.5, tp + 0.6, tp, tp + 0.2)); // теперь TP-бар закрыт
P.onTick(st, bars, WAIT, 4000);
chk("B2 закрытие по TP", st.closed.length === 1 && st.closed[0].reason === "TP" && Math.abs(st.closed[0].exit - tp) < 1e-9);
chk("B3 net = +1R − cost/R (консервативный fallback 0.72)", Math.abs(st.closed[0].net_r - (1 - P.COST_USD / R)) < 1e-6);

// C) SL FIRST: в одном закрытом баре и tp и sl
st = { pending: null, open: null, closed: [], log: [] };
st.open = { branch: "B02", direction: 1, entry: 100, sl: 75, tp: 125, r_usd: 25, invalidation: 60,
            open_bar: 1, mae: 0, mfe: 0, hold: 0, signal_time: 0, entry_time: 1, w3: "B" };
bars = [bar(0, 100, 101, 99, 100), bar(1, 100, 101, 99, 100), bar(2, 100, 130, 70, 100)];
P.onTick(st, bars, WAIT, 1);          // бар 2 ещё формирующийся
chk("C1 оба уровня в формирующемся баре → не закрыта", st.open !== null);
bars.push(bar(3, 100, 101, 99, 100));
P.onTick(st, bars, WAIT, 2);
chk("C2 SL FIRST при TP+SL в одном закрытом баре", st.closed.length === 1 && st.closed[0].reason === "SL_FIRST" && st.closed[0].exit === 75);

// D) structural invalidation: close закрытого бара за уровнем
st = { pending: null, open: null, closed: [], log: [] };
st.open = { branch: "B02", direction: 1, entry: 100, sl: 75, tp: 125, r_usd: 25, invalidation: 90,
            open_bar: 0, mae: 0, mfe: 0, hold: 0, signal_time: 0, entry_time: 0, w3: "B" };
bars = [bar(0, 100, 101, 99, 100), bar(1, 100, 101, 99, 95), bar(2, 95, 96, 89, 89.5)];
P.onTick(st, bars, WAIT, 3);
bars.push(bar(3, 89.5, 90, 89, 89.2));
P.onTick(st, bars, WAIT, 4);
chk("D закрытие по structural invalidation", st.closed.length === 1 && st.closed[0].reason === "STRUCT" && st.closed[0].exit === 89.5);

// E) max hold 96
st = { pending: null, open: null, closed: [], log: [] };
st.open = { branch: "B02", direction: 1, entry: 100, sl: 75, tp: 125, r_usd: 25, invalidation: 60,
            open_bar: 0, mae: 0, mfe: 0, hold: 0, signal_time: 0, entry_time: 0, w3: "B" };
bars = []; for (let i = 0; i <= 99; i++) bars.push(bar(i, 100, 101, 99, 100));
P.onTick(st, bars, WAIT, 5);
chk("E закрытие по max hold 96", st.closed.length === 1 && st.closed[0].reason === "TIME" && st.closed[0].hold_bars >= 96);

// F) manual close
st = { pending: null, open: null, closed: [], log: [] };
st.open = { branch: "B02", direction: 1, entry: 100, sl: 75, tp: 125, r_usd: 25, invalidation: 60,
            open_bar: 0, mae: 0, mfe: 0, hold: 2, signal_time: 0, entry_time: 0, w3: "B" };
P.closeManual(st, 110, 6);
chk("F MANUAL закрытие", st.closed[0].reason === "MANUAL" && st.closed[0].exit === 110 && Math.abs(st.closed[0].gross_r - 0.4) < 1e-9);

// G) классификация §66
chk("G1 EXECUTION (TP недосягаем)", P.classify({ reason: "SL", mfe_r: 1.2, net_r: -1 }).startsWith("EXECUTION"));
chk("G2 TRIGGER (вход против движения)", P.classify({ reason: "SL", mfe_r: 0.1, net_r: -1 }).startsWith("TRIGGER"));
chk("G3 RUNNER candidate", P.classify({ reason: "TP", mfe_r: 1.8, net_r: 1 }) === "WIN-RUNNER-CANDIDATE");
chk("G4 HOLD", P.classify({ reason: "TIME", mfe_r: 0.3, net_r: -0.1 }).startsWith("HOLD"));
chk("G5 STRUCTURE", P.classify({ reason: "STRUCT", mfe_r: 0.2, net_r: -1 }).startsWith("STRUCTURE"));

// H) статистика + tiers §63 + кандидаты не применяются
st = { pending: null, open: null, closed: [
  { net_r: 1, mae_r: -0.2, mfe_r: 1, reason: "TP", error: "WIN" },
  { net_r: -1, mae_r: -1, mfe_r: 0.1, reason: "SL", error: "TRIGGER ERROR: вход против движения" },
  { net_r: 0.9, mae_r: -0.3, mfe_r: 0.9, reason: "TP", error: "WIN" }], log: [] };
let s = P.stats(st);
chk("H1 stats", s.n === 3 && Math.abs(s.wr - 66.666) < 0.01 && Math.abs(s.net - 0.9) < 1e-9);
chk("H2 tier <10 = NO PARAMETER CHANGES", P.calibrationTier(5).allowed.indexOf("NO PARAMETER CHANGES") === 0);
chk("H3 tier 30–49", P.calibrationTier(40).tier === "30–49");
chk("H4 tier 50+", P.calibrationTier(60).tier === "50+");
let c = P.candidates({ closed: st.closed });
chk("H5 кандидаты только pre-registered", c.candidates.every(x => x.status.indexOf("НЕ применено") === 0));

// I) append-only: закрытая сделка не меняется повторным onTick
const before = JSON.stringify(st.closed);
P.onTick(st, [bar(1, 1, 1, 1, 1), bar(2, 1, 1, 1, 1)], WAIT, 99);
chk("I журнал append-only", JSON.stringify(st.closed) === before);

console.log("\nитог:", pass, "PASS /", fail, "FAIL");
process.exit(fail ? 1 : 0);
