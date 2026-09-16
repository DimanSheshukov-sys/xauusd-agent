# кросс-валидация: те же данные, что и у JS (/tmp/px.json), прогнаны через Python-движок
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
import backtest as bt            # noqa: E402
import indicators as ind         # noqa: E402

COLS = ["t", "o", "h", "l", "c"]


def kl(sym, iv, lim):
    u = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={iv}&limit={lim}"
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read())


def main():
    m15, d1, h1 = kl("PAXGUSDT", "15m", 600), kl("PAXGUSDT", "1d", 300), kl("PAXGUSDT", "1h", 500)
    data = {k: [[x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in v]
            for k, v in {"m15": m15, "d1": d1, "h1": h1}.items()}
    Path("/tmp/px.json").write_text(json.dumps(data))

    df = pd.DataFrame(data["m15"], columns=COLS).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})
    df["time"] = pd.to_datetime(df.t, unit="ms", utc=True)
    d = bt.prepare(df, k=2.0)
    i = len(df) - 2
    piv = [p for p in d["pivots"] if p.confirm_idx <= i]
    act = None
    for b in sorted(d["structs"]):
        st = d["structs"][b]
        if b <= i and not st.dead(i, df["close"].iloc[i]):
            act = st
    dh, dl = ind.donchian(df["high"].to_numpy(float), df["low"].to_numpy(float), 8)
    d1df = pd.DataFrame(data["d1"], columns=COLS).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})
    e = ind.ema(d1df["close"].to_numpy(float), 200)
    d1c = d1df["close"].to_numpy(float)
    print("PY pivots_confirmed:", len(piv), "| active:",
          (act.kind, act.direction, round(act.invalidation, 2), act.as_of) if act else None)
    print("PY donchian_hi:", round(float(dh[i]), 2), "| d1 close:", round(float(d1c[-2]), 2),
          "ema200:", round(float(e[-2]), 2), "bull:", bool(d1c[-2] > e[-2]))
    print("PY close:", round(float(df["close"].iloc[i]), 2), "atr:", round(float(d["atr"][i]), 3))
    r_usd = 2.5 * float(d["atr"][i])
    entry = float(df["open"].iloc[i + 1])
    print("PY scenario:", json.dumps({"trigger": round(float(dh[i]), 2),
                                      "sl": round(entry - r_usd, 2), "tp": round(entry + 1.0 * r_usd, 2),
                                      "inv": round(float(act.invalidation), 2) if act else None,
                                      "w5": round(float(act.w5_target_fib), 2) if act and act.kind == "IMPULSE_W5" else None,
                                      "cost_r": round(0.52 / r_usd, 4)}))


if __name__ == "__main__":
    main()
