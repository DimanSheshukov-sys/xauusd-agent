const E = require("./live_engine.js");
const TFS = [["4h",500],["15m",600],["5m",600],["1m",600]];
(async () => {
  const chain = [];
  for (const [tf, lim] of TFS) {
    const r = await fetch(`https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=${tf}&limit=${lim}`).then(x=>x.json());
    const bars = r.map(k=>({t:k[0],o:+k[1],h:+k[2],l:+k[3],c:+k[4]}));
    const st = E.decide(bars, bars, bars);
    const piv = st.pivots;
    const legs = [];
    for (let i=1;i<piv.length;i++) legs.push(piv[i].idx - piv[i-1].idx);
    const avgBars = legs.length ? legs.reduce((a,b)=>a+b,0)/legs.length : 0;
    const avgUsd = piv.length>1 ? piv.slice(1).reduce((a,p,i)=>a+Math.abs(p.price-piv[i].price),0)/(piv.length-1) : 0;
    const legsArr = st.structure ? st.structure.piv.map(p=>p.idx) : [];
    const legsN = []; for(let i=1;i<legsArr.length;i++) legsN.push(legsArr[i]-legsArr[i-1]);
    const cur = st.structure ? (st.structure.kind==="IMPULSE_W5"?["W1","W2","W3","W4","W5"]:["A","B","C"])[Math.min(st.structure.piv.length-1,2===0?0:st.structure.piv.length-1,4)] : "—";
    const label = st.structure ? (st.structure.kind==="IMPULSE_W5"?["W1","W2","W3","W4","W5"]:["A","B","C"])[Math.min(st.structure.piv.length-1,4)] : "—";
    chain.push(`${tf}:${label}${st.structure? (st.structure.direction>0?"↑":"↓") :"·"}`);
    console.log(`${tf.padEnd(4)} пивотов=${String(piv.length).padStart(3)} | волн. ног=${String(legsN.length).padStart(2)} | `+
      `ср. длина ноги: ${avgBars.toFixed(0)} баров / ${avgUsd.toFixed(1)} USD | ATR=${st.atr.toFixed(2)} | `+
      `структура=${st.structure?st.structure.kind:"—"} | сейчас ${label} | W3class=${st.structure?st.structure.w3_class:"—"}`);
  }
  console.log("\nцепочка вложенности:", chain.join(" ⊃ "));
})();
