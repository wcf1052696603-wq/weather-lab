# -*- coding: utf-8 -*-
"""用 NASA POWER (MERRA-2) 抓取各城市 2015-2024 逐日气候数据。

选择理由：免密钥、明确支持程序化批量访问、全球覆盖、直接提供太阳辐射与风场；
Open-Meteo 的历史接口对批量下载有严格的按小时请求限额，不适合一次抓 100+ 城市。

输出: data/climate.json （与 Open-Meteo 版本同一 schema）
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_climate import agg  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

START, END = date(2015, 1, 1), date(2024, 12, 31)
PARAMS = ["T2M", "T2M_MAX", "T2M_MIN", "RH2M", "PRECTOTCORR",
          "ALLSKY_SFC_SW_DWN", "WS2M"]
FILL = -999.0
UA = {"User-Agent": "weather-lab/1.0 (personal climate comparison tool)"}
API = "https://power.larc.nasa.gov/api/temporal/daily/point"


def days():
    out, d = [], START
    while d <= END:
        out.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return out


DAYS = days()
ISO = [f"{s[:4]}-{s[4:6]}-{s[6:]}" for s in DAYS]


def fetch_point(lat, lon, tries=4):
    q = {
        "parameters": ",".join(PARAMS), "community": "AG",
        "longitude": lon, "latitude": lat,
        "start": DAYS[0], "end": DAYS[-1], "format": "JSON",
    }
    url = API + "?" + urllib.parse.urlencode(q)
    last = None
    for i in range(tries):
        if i:
            time.sleep(5 * i)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=180) as r:
                j = json.loads(r.read().decode("utf-8"))
            return j["properties"]["parameter"]
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"fetch failed: {last}")


def to_om_shape(p):
    """把 POWER 参数字典转成 Open-Meteo 风格的 daily 结构。"""
    def col(name, scale=1.0, default=None):
        d = p.get(name) or {}
        out = []
        for k in DAYS:
            v = d.get(k, FILL)
            if v is None or v <= FILL + 1:
                out.append(default)
            else:
                out.append(round(v * scale, 4))
        return out

    return {
        "time": ISO,
        "temperature_2m_max": col("T2M_MAX"),
        "temperature_2m_min": col("T2M_MIN"),
        "temperature_2m_mean": col("T2M"),
        "relative_humidity_2m_mean": col("RH2M"),
        "precipitation_sum": col("PRECTOTCORR", 1.0, 0.0),
        # WS2M 为 2m 平均风速(m/s) → km/h；注意这是平均风速而非日最大风速
        "wind_speed_10m_max": col("WS2M", 3.6),
        # ALLSKY_SFC_SW_DWN 在 AG 社区下单位即为 MJ/m²/日（已核对接口 units 字段）
        "shortwave_radiation_sum": col("ALLSKY_SFC_SW_DWN", 1.0),
    }


def main():
    with open(os.path.join(DATA, "cities.json"), encoding="utf-8") as f:
        cities = json.load(f)
    PRIORITY = ["huizhou", "wuhu", "guangzhou", "shenzhen", "hefei", "nanjing",
                "hangzhou", "shanghai", "beijing", "chengdu", "harbin", "sanya"]
    cities.sort(key=lambda c: PRIORITY.index(c["id"]) if c["id"] in PRIORITY else len(PRIORITY))

    part = os.path.join(DATA, "climate-partial-power.json")
    out = {}
    if os.path.exists(part):
        with open(part, encoding="utf-8") as f:
            out = json.load(f)
        print("resume:", len(out), flush=True)

    for i, c in enumerate(cities):
        if c["id"] in out:
            continue
        try:
            params = fetch_point(c["lat"], c["lon"])
            monthly, annual = agg(to_om_shape(params))
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {c['id']}: {exc}", flush=True)
            continue
        out[c["id"]] = {
            "id": c["id"], "name": c["name"], "admin": c["admin"],
            "country": c["country"], "region": c["region"],
            "lat": c["lat"], "lon": c["lon"], "elev": c["elev"],
            "tz": None, "srcElev": None,
            "monthly": monthly, "annual": annual,
        }
        if i % 5 == 0 or i == len(cities) - 1:
            with open(part, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        print(f"[{len(out)}/{len(cities)}] {c['name']} "
              f"均温{annual['tMean']}℃ 降水{annual['precip']:.0f}mm "
              f"湿度{annual['rh']}% 辐射{annual['rad']:.1f}MJ "
              f"雨日{annual['rainDays']:.0f} 高温{annual['hot35']:.0f}", flush=True)
        time.sleep(0.5)

    payload = {
        "meta": {
            "source": "NASA POWER Daily API (MERRA-2, community=AG)",
            "start": START.isoformat(), "end": END.isoformat(),
            "generated": date.today().isoformat(),
            "cityCount": len(out),
            "note": "风速为 2m 平均风速(WS2M)；太阳辐射单位 MJ/m²/日（AG 社区原始单位）",
        },
        "cities": out,
    }
    with open(os.path.join(DATA, "climate.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("DONE cities=", len(out), flush=True)


if __name__ == "__main__":
    main()
