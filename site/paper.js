/* paper.js — live paper-трейдинг и обучение в браузере (localStorage, append-only журнал).
 * Правила заморожены (PARAMETER_FREEZE_v2, addendum LIVE PAPER v1):
 *   entry   = open первого M15-бара ПОСЛЕ сигнального бара (конвенция §47);
 *   SL/TP   = геометрия G_BASE47: SL 2.5×ATR(14,M15), TP 1.0R; TP+SL в одном баре → SL FIRST (§28);
 *   закрытие: SL | TP | structural invalidation (close закрытого бара за уровнем, §11) |
 *             max hold 96 баров | ручное закрытие (логируется как MANUAL);
 *   costs   = 0.52 USD round-trip (0.40 спред + 2×0.06);
 *   журнал  = append-only: закрытые сделки НЕ изменяются никогда (RULE 13);
 *   обучение = только классификация ошибок (§66) + pre-registered кандидаты; параметры НЕ меняются (§64).
 */
(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) module.exports = factory();
  else root.Paper = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  var KEY = "xauusd_paper_v1";
  var MAX_HOLD = 96, COST_USD = 0.72;          // консервативный fallback: спред 0.60 + 2×0.06
  var DAY_LOSS_LIMIT = -3.0;                   // circuit breaker: −3R за UTC-день (freeze v2.3)

  function dayKey(ms) { return new Date(ms).toISOString().slice(0, 10); }
  function dayLoss(st, ms) {
    var k = dayKey(ms), sum = 0;
    (st.closed || []).forEach(function (t) { if ((t.exit_time || "").slice(0, 10) === k) sum += t.net_r; });
    return sum;
  }
  function circuitOpen(st, ms) {
    return dayLoss(st, ms) <= DAY_LOSS_LIMIT;
  }
  /* Расширенный circuit breaker (P0 ТЗ): список причин → SYSTEM STATUS = HALTED.
     Не меняет историю, блокирует только новые сигналы. */
  function haltReasons(st, ms, opts) {
    opts = opts || {};
    var r = [];
    if (dayLoss(st, ms) <= DAY_LOSS_LIMIT) r.push("дневной лимит −3R исчерпан");
    var cl = (st.closed || []).filter(function (t) { return t.reason !== "MANUAL"; });
    var consec = 0;
    for (var i = cl.length - 1; i >= 0; i--) { if (cl[i].net_r < 0) consec++; else break; }
    if (consec >= 5) r.push("5 убытков подряд");
    if (cl.length >= 30) {
      var last30 = cl.slice(-30).map(function (t) { return t.net_r; });
      var e30 = last30.reduce(function (a, b) { return a + b; }, 0) / 30;
      if (e30 < 0) r.push("rolling 30-trade expectancy < 0 (" + e30.toFixed(3) + "R)");
    }
    if (opts.spread && opts.spread > 0.9) r.push("аномальный спред " + opts.spread.toFixed(2) + " USD (> 0.9)");
    if (opts.stale) r.push("устаревшие рыночные данные (> 60 c)");
    if (opts.missing) r.push("пропуски баров в последовательности");
    if (opts.jump) r.push("невозможный скачок цены (> 8 ATR за бар)");
    return r;
  }
  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) {}
    return { pending: null, open: null, closed: [], log: [] };
  }
  function save(st) { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }

  function push(st, msg) {
    st.log.push({ t: Date.now(), msg: msg });
    if (st.log.length > 400) st.log = st.log.slice(-400);
  }

  /* вызывается каждый тик: bars = M15 (последний — формирующийся), sig = результат LiveEngine.decide */
  function onTick(st, bars, sig, nowMs, costUsd, opts) {
    var ev = [];
    if (isFinite(costUsd) && costUsd > 0) COST_USD = costUsd;
    var hr = haltReasons(st, nowMs, opts);
    st.circuit = { day: dayKey(nowMs), loss: +dayLoss(st, nowMs).toFixed(2),
                   open: hr.length > 0, halted: hr.length > 0, reasons: hr };
    var i = bars.length - 2;                 // последний ЗАКРЫТЫЙ бар
    var closedBar = bars[i], forming = bars[bars.length - 1];

    // 1) сигнал → pending (вход по open следующего бара); circuit breaker блокирует новые входы
    if (!st.open && !st.pending && sig.decision === "LONG" && sig.scenario && !st.circuit.open) {
      st.pending = { signal_bar: i, signal_time: closedBar.t, branch: sig.branch,
                     direction: 1, sl: sig.scenario.primary.sl, tp: sig.scenario.primary.tp,
                     r_usd: sig.scenario.primary.r_usd, invalidation: sig.scenario.primary.invalidation,
                     w3: sig.structure ? sig.structure.w3_class : null, created: nowMs };
      push(st, "SIGNAL LONG " + sig.branch + " @bar " + i + " → entry по open следующего бара");
      ev.push({ type: "signal", at: nowMs });
    }
    // 2) pending → open на open следующего бара
    if (st.pending && i > st.pending.signal_bar) {
      var entry = bars[st.pending.signal_bar + 1].o;
      st.open = Object.assign({}, st.pending, { entry: entry, entry_time: bars[st.pending.signal_bar + 1].t,
                open_bar: st.pending.signal_bar + 1, mae: 0, mfe: 0, hold: 0 });
      st.pending = null;
      push(st, "OPEN LONG entry=" + entry.toFixed(2) + " SL=" + st.open.sl.toFixed(2) + " TP=" + st.open.tp.toFixed(2));
      ev.push({ type: "open", price: entry, at: nowMs });
    }
    // 3) сопровождение по ЗАКРЫТЫМ барам (SL-first при совпадении)
    if (st.open) {
      var o = st.open, exit = null;
      for (var b = Math.max(o.open_bar, i - 3); b <= i; b++) {
        if (b < o.open_bar) continue;
        var bar = bars[b];
        var hitSL = bar.l <= o.sl, hitTP = bar.h >= o.tp;
        if (hitSL && hitTP) { exit = { reason: "SL_FIRST", price: o.sl, bar: b }; break; }
        if (hitSL) { exit = { reason: "SL", price: o.sl, bar: b }; break; }
        if (hitTP) { exit = { reason: "TP", price: o.tp, bar: b }; break; }
        if (bar.c < o.invalidation) { exit = { reason: "STRUCT", price: bar.c, bar: b }; break; }
        o.hold = b - o.open_bar;
        o.mae = Math.min(o.mae, (bar.l - o.entry) / o.r_usd);
        o.mfe = Math.max(o.mfe, (bar.h - o.entry) / o.r_usd);
        if (o.hold >= MAX_HOLD) { exit = { reason: "TIME", price: bar.c, bar: b }; break; }
      }
      // live-стоп по текущей цене (защита между барами)
      if (!exit && forming.c <= o.sl) exit = { reason: "SL", price: o.sl, bar: i + 1 };
      if (exit) { close(st, exit.price, exit.reason, nowMs); ev.push({ type: "close", reason: exit.reason, at: nowMs }); }
    }
    save(st);
    return ev;
  }

  function close(st, price, reason, nowMs) {
    var o = st.open; if (!o) return null;
    var gross = (price - o.entry) / o.r_usd;
    var costR = COST_USD / o.r_usd;
    /* после закрытия пересчитаем circuit: если день достиг лимита — новые входы сегодня закрыты */
    var t = { branch: o.branch, direction: o.direction, w3: o.w3,
              signal_time: o.signal_time, entry_time: o.entry_time, entry: o.entry,
              market_price: price, source: o.source || "PROXY_PAXG", timeframe: "M15",
              sl: o.sl, tp: o.tp, r_usd: o.r_usd, invalidation: o.invalidation,
              expected_r: 1.0, actual_r: +gross.toFixed(4),
              spread: o.spread || 0.60, slippage: o.slippage || 0.0, commission: 0.12,
              total_cost_usd: +((o.spread || 0.60) + 0.12).toFixed(3),
              event_state: o.event_state || "none",
              model_version: "3.0", parameter_version: o.parameter_version || "v2.3",
              data_version: o.data_version || "",
              exit_time: nowMs, exit: price, reason: reason,
              gross_r: +gross.toFixed(4), cost_r: +costR.toFixed(4), net_r: +(gross - costR).toFixed(4),
              mae_r: +o.mae.toFixed(3), mfe_r: +o.mfe.toFixed(3), hold_bars: o.hold,
              snapshot: o.snapshot || null };
    t.error = classify(t);
    st.closed.push(t);                      // append-only: дальше не изменяется
    st.open = null;
    push(st, "CLOSE " + reason + " price=" + price.toFixed(2) + " net=" + t.net_r.toFixed(2) + "R class=" + t.error);
    save(st);
    return t;
  }

  function closeManual(st, price, nowMs) {
    if (!st.open) return null;
    return close(st, price, "MANUAL", nowMs);
  }

  /* классификация ошибок §66 (эвристики заморожены; это ДИАГНОСТИКА, не изменение правил) */
  function classify(t) {
    if (t.net_r > 0) return t.mfe_r >= 1.5 ? "WIN-RUNNER-CANDIDATE" : "WIN";
    switch (t.reason) {
      case "SL": case "SL_FIRST":
        if (t.mfe_r >= 1.0) return "EXECUTION ERROR: TP недосягаем / вход поздний";
        if (t.mfe_r < 0.2) return "TRIGGER ERROR: вход против движения";
        return "REGIME ERROR: шум против позиции";
      case "STRUCT": return "STRUCTURE ERROR: invalidation сработал";
      case "TIME": return "HOLD ERROR: сделка не реализовалась за 96 баров";
      case "MANUAL": return "MANUAL EXIT: вне правил (исключить из статистики правил)";
      default: return "UNKNOWN";
    }
  }

  function stats(st) {
    var tr = st.closed.filter(function (t) { return t.reason !== "MANUAL"; });
    if (!tr.length) return { n: 0 };
    var net = tr.map(function (t) { return t.net_r; });
    var win = net.filter(function (x) { return x > 0; });
    var loss = net.filter(function (x) { return x <= 0; });
    var gw = win.reduce(function (a, b) { return a + b; }, 0);
    var gl = -loss.reduce(function (a, b) { return a + b; }, 0);
    var eq = 0, peak = 0, mdd = 0;
    net.forEach(function (x) { eq += x; peak = Math.max(peak, eq - 0); mdd = Math.min(mdd, eq - peak); });
    var exp = net.reduce(function (a, b) { return a + b; }, 0) / net.length;
    var sd = Math.sqrt(net.reduce(function (a, b) { return a + (b - exp) * (b - exp); }, 0) / Math.max(1, net.length - 1));
    return { n: net.length, wr: win.length / net.length * 100, pf: gl > 0 ? gw / gl : (gw > 0 ? Infinity : NaN),
             exp: exp, net: net.reduce(function (a, b) { return a + b; }, 0), mdd: mdd, sd: sd,
             t: sd > 0 ? exp / (sd / Math.sqrt(net.length)) : NaN,
             mae: tr.reduce(function (a, t) { return a + t.mae_r; }, 0) / tr.length,
             mfe: tr.reduce(function (a, t) { return a + t.mfe_r; }, 0) / tr.length };
  }

  /* §63 calibration policy: что ДОЗВОЛЕНО при текущем объёме выборки */
  function calibrationTier(n) {
    if (n < 10) return { tier: "<10 сделок", allowed: "NO PARAMETER CHANGES — только наблюдение" };
    if (n < 30) return { tier: "10–29", allowed: "SOFT RESEARCH — гипотезы без изменения правил" };
    if (n < 50) return { tier: "30–49", allowed: "NORMAL CALIBRATION — после нового validation cycle" };
    return { tier: "50+", allowed: "FULL CALIBRATION — после нового validation cycle" };
  }

  /* pre-registered кандидаты (формируются, НЕ применяются; §64–65) */
  function candidates(st) {
    var tr = st.closed.filter(function (t) { return t.reason !== "MANUAL"; });
    var out = [];
    var cnt = {};
    tr.forEach(function (t) { cnt[t.error] = (cnt[t.error] || 0) + 1; });
    if ((cnt["EXECUTION ERROR: TP недосягаем / вход поздний"] || 0) >= 3)
      out.push({ id: "H-TP", text: "уменьшить TP до 0.8R ИЛИ ужесточить trigger (Donchian 6)", status: "НЕ применено: требует walk-forward на новом окне (§65)" });
    if ((cnt["TRIGGER ERROR: вход против движения"] || 0) >= 3)
      out.push({ id: "H-TRIG", text: "добавить подтверждение: close > EMA20(M15) на сигнальном баре", status: "НЕ применено: pre-registration + OOS" });
    if ((cnt["HOLD ERROR: сделка не реализовалась за 96 баров"] || 0) >= 3)
      out.push({ id: "H-HOLD", text: "max hold 96 → 144 баров", status: "НЕ применено: требует валидации" });
    if ((cnt["WIN-RUNNER-CANDIDATE"] || 0) >= 3)
      out.push({ id: "H-RUN", text: "исследовать runner-ветку: trailed stop после +1R", status: "НЕ применено: отдельная frozen branch" });
    return { counts: cnt, candidates: out, tier: calibrationTier(tr.length) };
  }

  function exportCSV(st) {
    var head = "branch,direction,w3,signal_time,entry_time,entry,sl,tp,r_usd,invalidation,exit_time,exit,reason,gross_r,cost_r,net_r,mae_r,mfe_r,hold_bars,error_class";
    var rows = st.closed.map(function (t) {
      return [t.branch, t.direction, t.w3, new Date(t.signal_time).toISOString(), new Date(t.entry_time).toISOString(),
        t.entry, t.sl, t.tp, t.r_usd, t.invalidation, new Date(t.exit_time).toISOString(), t.exit, t.reason,
        t.gross_r, t.cost_r, t.net_r, t.mae_r, t.mfe_r, t.hold_bars, '"' + t.error + '"'].join(",");
    });
    return head + "\n" + rows.join("\n");
  }

  function reset(st) { var f = load(); f.closed = []; f.open = null; f.pending = null; f.log = []; save(f); return f; }

  function alwaysValidP(net, tau) {
    /* mSPRT (Howard et al.): всегда-валидное p-значение — смотреть можно в любой момент без peeking-bias.
       sigma оценивается по выборке (fallback 1.24R), tau = 0.15R — практически значимый эффект.
       Значение заведомо консервативнее классического p — это плата за возможность смотреть всегда. */
    tau = tau || 0.15;
    var n = net.length; if (!n) return 1;
    var m = net.reduce(function (a, b) { return a + b; }, 0) / n;
    var sd = n > 1 ? Math.sqrt(net.reduce(function (a, b) { return a + (b - m) * (b - m); }, 0) / (n - 1)) : 1.24;
    var sigma = Math.max(0.6, sd || 1.24);
    var S = m * n, v = sigma * sigma;
    var logL = -0.5 * Math.log(1 + n * tau * tau / v) + (S * S / 2) * (tau * tau / (v * (v + n * tau * tau)));
    return Math.min(1, Math.exp(-logL));
  }
  return { load: load, save: save, onTick: onTick, close: close, closeManual: closeManual,
           classify: classify, stats: stats, calibrationTier: calibrationTier,
           candidates: candidates, exportCSV: exportCSV, reset: reset,
           dayLoss: dayLoss, circuitOpen: circuitOpen, alwaysValidP: alwaysValidP,
           MAX_HOLD: MAX_HOLD, COST_USD: COST_USD, DAY_LOSS_LIMIT: DAY_LOSS_LIMIT };
});
