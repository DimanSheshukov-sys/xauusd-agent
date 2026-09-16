/* live_engine.js — браузерный порт причинного движка (engine/swings.py + elliott.py + analyze.py).
 * Работает и в браузере, и в node (для кросс-валидации с Python).
 * Параметры заморожены: PARAMETER_FREEZE_v2 (K=2.0*ATR14, min_bars=1, G_BASE47: SL 2.5 ATR / TP 1.0R,
 * приоритет веток B04 -> B01 -> B02, regime D1 EMA200, trigger Donchian(8), SETUP_MAX_AGE=200).
 */
(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) module.exports = factory();
  else root.LiveEngine = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var CFG = {
    K: 2.0, ATR_N: 14, MIN_BARS: 1, SETUP_MAX_AGE: 200, DONCHIAN_N: 8,
    SL_ATR: 2.5, TP_R: 1.0, RSI_N: 14, EMA_D1: 200,
    SPREAD_USD: 0.40, COMM_USD: 0.06,
    COST_LIMIT_R: 0.05
  };

  function atr(h, l, c, n) {
    var out = new Array(h.length).fill(NaN);
    if (h.length < n + 1) return out;
    var tr = new Array(h.length).fill(NaN);
    for (var i = 1; i < h.length; i++) {
      var pc = c[i - 1];
      tr[i] = Math.max(h[i] - l[i], Math.abs(h[i] - pc), Math.abs(l[i] - pc));
    }
    var s = 0;
    for (i = 1; i <= n; i++) s += tr[i];
    var prev = s / n;
    out[n] = prev;
    for (i = n + 1; i < h.length; i++) { prev = (prev * (n - 1) + tr[i]) / n; out[i] = prev; }
    return out;
  }

  function ema(x, n) {
    var out = new Array(x.length).fill(NaN);
    if (x.length < n) return out;
    var s = 0;
    for (var i = 0; i < n; i++) s += x[i];
    var prev = s / n;
    out[n - 1] = prev;
    var a = 2 / (n + 1);
    for (i = n; i < x.length; i++) { prev = a * x[i] + (1 - a) * prev; out[i] = prev; }
    return out;
  }

  function rsi(c, n) {
    var out = new Array(c.length).fill(NaN);
    if (c.length < n + 1) return out;
    var g = 0, l = 0, i, d;
    for (i = 1; i <= n; i++) { d = c[i] - c[i - 1]; if (d > 0) g += d; else l -= d; }
    var ag = g / n, al = l / n;
    out[n] = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
    for (i = n + 1; i < c.length; i++) {
      d = c[i] - c[i - 1];
      ag = (ag * (n - 1) + (d > 0 ? d : 0)) / n;
      al = (al * (n - 1) + (d < 0 ? -d : 0)) / n;
      out[i] = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
    }
    return out;
  }

  function donchian(h, l, n) {
    var hi = new Array(h.length).fill(NaN), lo = new Array(h.length).fill(NaN);
    for (var i = n; i < h.length; i++) {
      var mh = -Infinity, ml = Infinity;
      for (var j = i - n; j < i; j++) { if (h[j] > mh) mh = h[j]; if (l[j] < ml) ml = l[j]; }
      hi[i] = mh; lo[i] = ml;
    }
    return { hi: hi, lo: lo };
  }

  /* причинный ZigZag: пивот получает confirm_idx — бар, на котором стал известен */
  function zigzag(h, l, atrArr, k, minBars) {
    k = k || CFG.K; minBars = minBars == null ? CFG.MIN_BARS : minBars;
    var piv = [], trend = 0, hi_i = 0, lo_i = 0, hi_v = h[0], lo_v = l[0], i;
    function thr(idx) { var a = atrArr[idx]; return (isFinite(a) && a > 0) ? k * a : Infinity; }
    for (i = 1; i < h.length; i++) {
      if (trend >= 0 && h[i] > hi_v) { hi_v = h[i]; hi_i = i; }
      if (trend <= 0 && l[i] < lo_v) { lo_v = l[i]; lo_i = i; }
      var last = piv.length ? piv[piv.length - 1].idx : -1e9;
      if (trend >= 0 && hi_i > last && hi_i < i && (hi_i - last) >= minBars && l[i] <= hi_v - thr(hi_i)) {
        piv.push({ idx: hi_i, price: hi_v, kind: "H", confirm: i });
        var mi = hi_i + 1; for (var j = hi_i + 1; j <= i; j++) if (l[j] < l[mi]) mi = j;
        lo_i = mi; lo_v = l[mi]; trend = -1; continue;
      }
      if (trend <= 0 && lo_i > last && lo_i < i && (lo_i - last) >= minBars && h[i] >= lo_v + thr(lo_i)) {
        piv.push({ idx: lo_i, price: lo_v, kind: "L", confirm: i });
        var mx = lo_i + 1; for (j = lo_i + 1; j <= i; j++) if (h[j] > h[mx]) mx = j;
        hi_i = mx; hi_v = h[mx]; trend = 1; continue;
      }
    }
    return piv;
  }

  function w3class(r) { if (!isFinite(r)) return "UNAVAILABLE"; return r < 1 ? "A" : (r < 1.618 ? "B" : "C"); }

  function detectImpulse(p5) {
    if (!p5 || p5.length !== 5) return null;
    var kinds = p5.map(function (p) { return p.kind; }).join("");
    var d = kinds === "LHLHL" ? 1 : (kinds === "HLHLH" ? -1 : 0);
    if (!d) return null;
    var p0 = p5[0], p1 = p5[1], p2 = p5[2], p3 = p5[3], p4 = p5[4], w1, w2, w3, w4;
    if (d > 0) { w1 = p1.price - p0.price; w2 = p1.price - p2.price; w3 = p3.price - p2.price; w4 = p3.price - p4.price; }
    else { w1 = p0.price - p1.price; w2 = p2.price - p1.price; w3 = p2.price - p3.price; w4 = p4.price - p3.price; }
    var rules = d > 0
      ? { R1: p2.price > p0.price, R2: p4.price > p1.price, R3: w4 < w3 }
      : { R1: p2.price < p0.price, R2: p4.price < p1.price, R3: w4 < w3 };
    if (!(rules.R1 && rules.R2 && rules.R3 && w1 > 0 && w3 > 0)) return null;
    var ratio = w3 / w1, ret2 = w2 / w1, ret4 = w4 / w3;
    return {
      direction: d, kind: "IMPULSE_W5", piv: p5,
      w1: w1, w2: w2, w3: w3, w4: w4, ret2: ret2, ret4: ret4, ratio: ratio,
      w3_class: w3class(ratio),
      fib_ok: (ret2 >= 0.382 && ret2 <= 0.786 && ret4 >= 0.236 && ret4 <= 0.5),
      invalidation: p4.price, as_of: p4.confirm,
      w5_target: d > 0 ? p3.price + 0.618 * w3 : p3.price - 0.618 * w3
    };
  }

  function detectAbc(p3) {
    if (!p3 || p3.length !== 3) return null;
    var kinds = p3.map(function (p) { return p.kind; }).join("");
    var d = kinds === "HLH" ? -1 : (kinds === "LHL" ? 1 : 0);
    if (!d) return null;
    return { direction: d, kind: "ABC", piv: p3, invalidation: p3[2].price, as_of: p3[2].confirm, fib_ok: false, w3_class: "UNAVAILABLE" };
  }

  /* структуры по барам: новая структура появляется на confirm-баре последнего пивота */
  function structures(piv) {
    var out = [];
    for (var i = 4; i <= piv.length; i++) {
      var st = detectImpulse(piv.slice(i - 5, i));
      if (!st && i >= 3) st = detectAbc(piv.slice(i - 3, i));
      if (st) out.push(st);
    }
    return out;
  }

  function activeStructure(sts, bar, close) {
    var active = null;
    for (var i = 0; i < sts.length; i++) {
      var st = sts[i];
      if (st.as_of > bar) break;
      if (active && active.as_of >= st.as_of) { /* более поздняя заменяет */ }
      var dead = (bar - st.as_of > CFG.SETUP_MAX_AGE) ||
        (st.direction > 0 ? close < st.invalidation : close > st.invalidation);
      active = dead ? null : st;
    }
    return active;
  }

  /* полный gate-конвейер + решение + сценарии (§10, §37, §72) */
  function decide(bars, d1bars, h1bars, costs) {
    var SPREAD = (costs && isFinite(costs.spread)) ? costs.spread : CFG.SPREAD_USD;
    var COMM = (costs && isFinite(costs.comm)) ? costs.comm : CFG.COMM_USD;
    var h = bars.map(function (b) { return b.h; }), l = bars.map(function (b) { return b.l; }),
      c = bars.map(function (b) { return b.c; });
    var i = c.length - 2;                      // последний ЗАКРЫТЫЙ бар
    var atrArr = atr(h, l, c, CFG.ATR_N);
    var dc = donchian(h, l, CFG.DONCHIAN_N);
    var piv = zigzag(h, l, atrArr);
    var sts = structures(piv);
    var st = activeStructure(sts, i, c[i]);

    var dc1 = d1bars.map(function (b) { return b.c; });
    var e200 = ema(dc1, CFG.EMA_D1);
    var d1i = dc1.length - 2;                  // закрытый дневной бар
    var bull = dc1[d1i] > e200[d1i];

    var r1 = rsi(h1bars.map(function (b) { return b.c; }), CFG.RSI_N);
    var rsiH1 = r1[r1.length - 2];

    var gates = {
      G00: true, G01: true,
      G02: isFinite(dc1[d1i]) && isFinite(e200[d1i]),
      G03: !!st, G04: !!st && st.kind === "IMPULSE_W5",
      G05: !!st && st.kind === "IMPULSE_W5" ? true : null,
      G07: bull, G10: null, G11: !!st, G12: null, G14: null, G14a: null, G15: null
    };
    var reasons = [], decision = "WAIT", state = "S91 WAIT_STRUCTURE", branch = null;

    if (!st) {
      reasons.push("нет валидной causal Elliott структуры (G03): ни один пивот-паттерн не подтверждён или структура мертва");
    } else if (st.kind !== "IMPULSE_W5") {
      state = "S91 WAIT_STRUCTURE";
      reasons.push("структура " + st.kind + " — не IMPULSE_W5; ABC/Failed Fifth не торгуются (§6/§10)");
      if (!bull) reasons.push("дополнительно G07 REGIME fail для LONG: D1 close ниже EMA200 (§7)");
    } else {
      if (st.direction > 0 && !bull) reasons.push("G07 REGIME fail: D1 close ниже EMA200 → production LONG запрещён (§7)");
      var trig = st.direction > 0 ? c[i] > dc.hi[i] : c[i] < dc.lo[i];
      gates.G10 = trig;
      var cands = st.direction > 0
        ? [{ id: "B04_LONG_EXTW3_RSI", need: st.w3_class === "C" && rsiH1 > 50 },
           { id: "B01_LONG_CORE", need: st.fib_ok },
           { id: "B02_LONG_EMA200_FIBOFF", need: true }]
        : [];
      branch = null;
      for (var q = 0; q < cands.length; q++) if (cands[q].need) { branch = cands[q].id; break; }
      if (st.direction < 0) reasons.push("медвежий импульс: SHORT-ветки отключены в v2 (P0, §58) → NO TRADE по реестру (G06)");
      if (st.direction > 0 && !branch) {
        if (st.w3_class !== "C") reasons.push("G05/G08: W3 class " + st.w3_class + " и Fib OFF не дают mandatory-ветку с подтверждением");
        if (st.w3_class === "C" && !(rsiH1 > 50)) reasons.push("G08: RSI(H1) " + (isFinite(rsiH1) ? rsiH1.toFixed(1) : "—") + " ≤ 50 — confirmation для B04 не выполнен");
      }
      if (st.direction > 0 && branch && !trig) {
        state = "S94 WAIT_TRIGGER";
        reasons.push("G10 TRIGGER отсутствует: close " + c[i].toFixed(2) + " не выше Donchian(8) " + dc.hi[i].toFixed(2));
      }
      if (st.direction > 0 && branch && trig && bull) {
        var entry = bars[i + 1] ? bars[i + 1].o : c[i];
        var rUsd = CFG.SL_ATR * atrArr[i];
        var costR = (SPREAD + 2 * COMM) / rUsd;
        gates.G12 = true; gates.G14 = true; gates.G14a = costR <= CFG.COST_LIMIT_R;
        if (!gates.G14a) { state = "S95 WAIT_RISK"; reasons.push("G14a: cost/R " + costR.toFixed(3) + " > 0.05"); }
        else { decision = "LONG"; state = "S17 SIGNAL_ISSUED → S18 SIGNAL_FROZEN"; reasons.push("все mandatory gates G00–G15 = TRUE"); }
        gates.G15 = decision === "LONG";
      }
    }

    /* сценарии (§37): primary + alternative + invalidation + target */
    var scen = null;
    if (st) {
      var dir = st.direction;
      var rUsd2 = CFG.SL_ATR * atrArr[i];
      var trigLvl = dir > 0 ? dc.hi[i] : dc.lo[i];
      var entry2 = bars[i + 1] ? bars[i + 1].o : c[i];
      var sl2 = dir > 0 ? entry2 - rUsd2 : entry2 + rUsd2;
      var tp2 = dir > 0 ? entry2 + CFG.TP_R * rUsd2 : entry2 - CFG.TP_R * rUsd2;
      var costR2 = (SPREAD + 2 * COMM) / rUsd2;
      scen = {
        direction: dir,
        primary: {
          text: dir > 0 ? "импульс W1–W4 завершён: продолжение в W5 после триггера" : "медвежий импульс: снижение после триггера (ветки отключены — наблюдение)",
          trigger: trigLvl, entry: entry2, sl: sl2, tp: tp2, r_usd: rUsd2,
          invalidation: st.invalidation, w5_target: st.w5_target || null,
          cost_r: costR2, spread: SPREAD
        },
        alternative: {
          text: dir > 0 ? "пробой invalidation → структура отменена, ожидание новой разметки (S91)" :
            "возврат выше invalidation → структура отменена, ожидание новой разметки (S91)",
          invalidation: st.invalidation
        }
      };
    }

    return {
      bar_index: i, bar_time: bars[i].t, close: c[i], atr: atrArr[i], rsi_h1: rsiH1,
      d1: { close: dc1[d1i], ema200: e200[d1i], bull: bull },
      donchian: { hi: dc.hi[i], lo: dc.lo[i] },
      pivots: piv.filter(function (p) { return p.confirm <= i; }),
      structure: st, gates: gates, decision: decision, state: state, reasons: reasons,
      branch: branch, scenario: scen,
      costs: { spread: SPREAD, comm: COMM },
      priors: { wr: 63.1, exp: 0.2204, pf: 1.573, note: "research priors v2 на PROXY-данных (PAXG), не обещание win rate" }
    };
  }

  return { CFG: CFG, atr: atr, ema: ema, rsi: rsi, donchian: donchian, zigzag: zigzag,
           detectImpulse: detectImpulse, detectAbc: detectAbc, structures: structures,
           activeStructure: activeStructure, decide: decide };
});
