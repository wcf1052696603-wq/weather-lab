# -*- coding: utf-8 -*-
"""把断点文件临时提升为 climate.json（用于在抓取完成前先验证下游流程）。"""
import json
import os
from datetime import date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
part = os.path.join(DATA, "climate-partial-power.json")
if not os.path.exists(part):
    raise SystemExit("no partial")

with open(part, encoding="utf-8") as f:
    cities = json.load(f)

payload = {
    "meta": {
        "source": "NASA POWER Daily API (MERRA-2, community=AG)",
        "start": "2015-01-01", "end": "2024-12-31",
        "generated": date.today().isoformat(),
        "cityCount": len(cities), "partial": True,
    },
    "cities": cities,
}
with open(os.path.join(DATA, "climate.json"), "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
print("promoted partial cities=", len(cities))
