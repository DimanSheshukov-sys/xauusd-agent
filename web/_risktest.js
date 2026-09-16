const P = require("./paper.js");
let pass=0, fail=0;
const chk=(n,c)=>{ c? (pass++,console.log("  PASS",n)) : (fail++,console.log("  FAIL",n)); };
const day = new Date().toISOString().slice(0,10);
// circuit: три стока по -1R в один день → новые входы запрещены
let st={pending:null,open:null,closed:[],log:[]};
for(let i=0;i<3;i++) st.closed.push({net_r:-1,exit_time:day+"T12:00:00Z",reason:"SL",mfe_r:0.1,error:"x"});
chk("dayLoss = -3", Math.abs(P.dayLoss(st, Date.now())+3)<1e-9);
chk("circuit open", P.circuitOpen(st, Date.now())===true);
let st2={pending:null,open:null,closed:[{net_r:-1,exit_time:day+"T12:00:00Z",reason:"SL",mfe_r:0.1}],log:[]};
chk("при -1R circuit закрыт", P.circuitOpen(st2, Date.now())===false);
// always-valid p: сильная выборка → мало, пустая → 1
const win=Array.from({length:300},(_,i)=> i%100<65 ? 1.35 : -1.05);
const p1=P.alwaysValidP(win);
chk("always-valid p сильной выборки < 0.05 ("+p1.toFixed(4)+")", p1<0.05);
chk("always-valid p пустой = 1", P.alwaysValidP([])===1);
const weak=Array.from({length:10},(_,i)=> i<6?0.95:-1.05);
chk("always-valid p слабой выборки > 0.05 ("+P.alwaysValidP(weak).toFixed(3)+")", P.alwaysValidP(weak)>0.05);
console.log("\nитог:",pass,"PASS /",fail,"FAIL");
process.exit(fail?1:0);
