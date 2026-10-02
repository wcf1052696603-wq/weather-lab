# -*- coding: utf-8 -*-
"""抓取各城市 2015-2024 逐日气候数据，聚合为月度/年度常年值。

数据源: Open-Meteo Historical Weather API (ERA5 再分析)
输出:   data/climate.json
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
UA = {"User-Agent": "weather-lab/1.0"}
START, END = "2015-01-01", "2024-12-31"
# 接口限额是按「请求次数/小时」计的，因此单次请求尽量多带城市，把总请求数压到最低
BATCH = 24
SLEEP_BETWEEN = 6
BACKOFF = [30, 60, 120, 300, 600]

DAILY = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "relative_humidity_2m_mean", "precipitation_sum", "sunshine_duration",
    "wind_speed_10m_max", "shortwave_radiation_sum",
]
MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def fetch(lats, lons):
    q = {
        "latitude": ",".join(str(x) for x in lats),
        "longitude": ",".join(str(x) for x in lons),
        "start_date": START, "end_date": END,
        "daily": ",".join(DAILY),
        "timezone": "auto",
    }
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(q)
    last = None
    for i, wait in enumerate([0] + BACKOFF):
        if wait:
            print(f"  backoff {wait}s ...", flush=True)
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode("utf-8"))
            return d if isinstance(d, list) else [d]
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"  attempt {i + 1} failed: {exc}", flush=True)
    raise RuntimeError(f"fetch failed: {last}")


def agg(daily):
    """把逐日序列聚合成月度常年值。缺失的变量会被跳过（便于兼容不同数据源）。"""
    t = daily["time"]
    nn = [None] * len(t)
    tmax = daily.get("temperature_2m_max") or nn
    tmin = daily.get("temperature_2m_min") or nn
    tmean = daily.get("temperature_2m_mean") or nn
    rh = daily.get("relative_humidity_2m_mean") or nn
    pr = daily.get("precipitation_sum") or [0.0] * len(t)
    wind = daily.get("wind_speed_10m_max") or nn
    rad = daily.get("shortwave_radiation_sum") or nn

    # 按 (月, 年) 分桶，以免 2 月因天数不同被稀释
    buckets = [{} for _ in range(12)]
    for i, ds in enumerate(t):
        y, m, _ = ds.split("-")
        buckets[int(m) - 1].setdefault(y, []).append(i)

    nyear = len({s[:4] for s in t})
    monthly = []
    for mi in range(12):
        vals = {k: [] for k in
                ("tMax", "tMin", "tMean", "rh", "precip", "rad", "wind",
                 "rainDays", "hot30", "hot35", "frost", "comfort",
                 "heavy", "storm", "dryDays")}
        # 先算每年的月均，再对年取平均 —— 消除月份长度差异
        for ys in buckets[mi].values():
            idx = ys
            g = lambda a: [a[i] for i in idx if a[i] is not None]  # noqa: E731
            v_max, v_min, v_mean = g(tmax), g(tmin), g(tmean)
            v_rh, v_pr, v_wind = g(rh), g(pr), g(wind)
            v_rad = g(rad)
            if v_mean:
                vals["tMean"].append(sum(v_mean) / len(v_mean))
            if v_max:
                vals["tMax"].append(sum(v_max) / len(v_max))
            if v_min:
                vals["tMin"].append(sum(v_min) / len(v_min))
            if v_rh:
                vals["rh"].append(sum(v_rh) / len(v_rh))
            vals["precip"].append(sum(v_pr))
            if v_rad:
                vals["rad"].append(sum(v_rad) / len(v_rad))   # MJ/m²/日
            if v_wind:
                vals["wind"].append(sum(v_wind) / len(v_wind))
            vals["rainDays"].append(sum(1 for x in v_pr if x >= 1.0))
            vals["heavy"].append(sum(1 for x in v_pr if x >= 25.0))
            vals["storm"].append(sum(1 for x in v_pr if x >= 50.0))
            vals["dryDays"].append(sum(1 for x in v_pr if x < 1.0))
            vals["hot30"].append(sum(1 for x in v_max if x >= 30))
            vals["hot35"].append(sum(1 for x in v_max if x >= 35))
            vals["frost"].append(sum(1 for x in v_min if x < 0))
            vals["comfort"].append(sum(
                1 for a, b in zip(v_mean, v_rh) if 15 <= a <= 25 and b <= 75))
        r = {}
        for k, v in vals.items():
            r[k] = round(sum(v) / len(v), 1) if v else 0.0
        monthly.append(r)

    def s(key):
        return round(sum(m[key] for m in monthly), 1)

    hi = max(range(12), key=lambda i: monthly[i]["tMean"])
    lo = min(range(12), key=lambda i: monthly[i]["tMean"])
    wet = max(range(12), key=lambda i: monthly[i]["precip"])
    annual = {
        "tMean": round(sum(m["tMean"] for m in monthly) / 12, 1),
        "tMaxAvg": round(sum(m["tMax"] for m in monthly) / 12, 1),
        "tMinAvg": round(sum(m["tMin"] for m in monthly) / 12, 1),
        "rh": round(sum(m["rh"] for m in monthly) / 12, 1),
        "precip": s("precip"),
        "rainDays": round(s("rainDays"), 1),
        "rad": round(sum(m["rad"] for m in monthly) / 12, 2),
        "wind": round(sum(m["wind"] for m in monthly) / 12, 1),
        "hot30": round(s("hot30"), 1),
        "hot35": round(s("hot35"), 1),
        "frost": round(s("frost"), 1),
        "comfort": round(s("comfort"), 0),
        "heavy": round(s("heavy"), 1),
        "storm": round(s("storm"), 1),
        "dryDays": round(s("dryDays"), 0),
        "maxDaily": round(max(x for x in pr if x is not None), 1),
        "warmestMonth": hi + 1, "warmestT": monthly[hi]["tMean"],
        "coldestMonth": lo + 1, "coldestT": monthly[lo]["tMean"],
        "wetMonth": wet + 1, "wetMonthP": monthly[wet]["precip"],
        "range": round(monthly[hi]["tMean"] - monthly[lo]["tMean"], 1),
        "absMax": round(max(x for x in tmax if x is not None), 1),
        "absMin": round(min(x for x in tmin if x is not None), 1),
        "years": nyear,
    }
    return monthly, annual


def main():
    with open(os.path.join(DATA, "cities.json"), encoding="utf-8") as f:
        cities = json.load(f)

    # 关键城市优先抓取，避免额度用尽时缺核心数据
    PRIORITY = ["huizhou", "wuhu", "guangzhou", "shenzhen", "hefei", "nanjing",
                "hangzhou", "shanghai", "beijing", "chengdu", "harbin", "sanya"]
    cities.sort(key=lambda c: PRIORITY.index(c["id"]) if c["id"] in PRIORITY else len(PRIORITY))

    # 断点续传：已抓取的城市直接复用
    part = os.path.join(DATA, "climate.partial.json")
    out = {}
    if os.path.exists(part):
        with open(part, encoding="utf-8") as f:
            out = json.load(f)
        print("resume from partial:", len(out), flush=True)

    todo = [c for c in cities if c["id"] not in out]
    total = len(todo)
    print(f"todo {total}/{len(cities)}", flush=True)

    for rnd in range(6):
        if not todo:
            break
        if rnd:
            print(f"--- round {rnd + 1}: {len(todo)} left ---", flush=True)
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            try:
                res = fetch([c["lat"] for c in chunk], [c["lon"] for c in chunk])
            except Exception as exc:  # noqa: BLE001
                print("batch giving up this round:", exc, flush=True)
                time.sleep(60)
                break
            for c, r in zip(chunk, res):
                try:
                    monthly, annual = agg(r["daily"])
                except Exception as exc:  # noqa: BLE001
                    print("AGG FAIL", c["id"], exc, flush=True)
                    continue
                out[c["id"]] = {
                    "id": c["id"], "name": c["name"], "admin": c["admin"],
                    "country": c["country"], "region": c["region"],
                    "lat": c["lat"], "lon": c["lon"], "elev": c["elev"],
                    "tz": r.get("timezone"), "srcElev": r.get("elevation"),
                    "monthly": monthly, "annual": annual,
                }
            # 每批落盘，随时可续
            with open(part, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
            print(f"progress ok={len(out)}/{len(cities)}", flush=True)
            time.sleep(SLEEP_BETWEEN)
        todo = [c for c in cities if c["id"] not in out]

    payload = {
        "meta": {
            "source": "Open-Meteo Historical Weather API (ERA5)",
            "start": START, "end": END,
            "generated": date.today().isoformat(),
            "cityCount": len(out),
        },
        "cities": out,
    }
    with open(os.path.join(DATA, "climate.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("done cities=", len(out))


if __name__ == "__main__":
    main()
