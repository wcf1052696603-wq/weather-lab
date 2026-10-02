# -*- coding: utf-8 -*-
"""把 climate.json 打包成浏览器可直接 <script> 引入的 JS，避免 file:// 下的跨域限制。
输出: data/climate-data.js
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

src = sys.argv[1] if len(sys.argv) > 1 else "climate.json"
path = os.path.join(DATA, src)
if not os.path.exists(path):
    alt = os.path.join(DATA, "climate.partial.json")
    print(f"{src} 不存在，改用 {alt}")
    path = alt

with open(path, encoding="utf-8") as f:
    payload = json.load(f)

if "cities" not in payload:            # 兼容抓取中的断点文件（只有城市字典）
    from datetime import date
    payload = {
        "meta": {"source": "Open-Meteo Historical Weather API (ERA5)",
                 "start": "2015-01-01", "end": "2024-12-31",
                 "generated": date.today().isoformat(),
                 "cityCount": len(payload), "partial": True},
        "cities": payload,
    }

js = ("/* 自动生成，请勿手工修改。来源: Open-Meteo ERA5, "
      + payload["meta"]["start"] + " ~ " + payload["meta"]["end"] + " */\n"
      + "window.WEATHER_DATA = "
      + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
      + ";\n")

out = os.path.join(DATA, "climate-data.js")
with open(out, "w", encoding="utf-8") as f:
    f.write(js)
print("wrote", out, round(os.path.getsize(out) / 1024, 1), "KB",
      "cities=", payload["meta"]["cityCount"])
