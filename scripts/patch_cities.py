# -*- coding: utf-8 -*-
"""修正地理编码歧义匹配，并规范化港澳台行政归属。"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "data", "cities.json")

FIX = {
    # 苏州被匹配到安徽宿州
    "suzhou": dict(name="苏州", nameEn="Suzhou", admin="江苏省", lat=31.2994, lon=120.5853),
    # 西安被匹配到贵州西安
    "xian": dict(name="西安", nameEn="Xi'an", admin="陕西省", lat=34.2658, lon=108.9541),
    # 纽约被匹配到内布拉斯加州约克
    "newyork": dict(name="纽约", nameEn="New York", admin="纽约州", lat=40.7143, lon=-74.0060),
    # 班加罗尔被匹配到巴基斯坦信德省
    "bangalore": dict(name="班加罗尔", nameEn="Bengaluru", admin="卡纳塔克邦",
                      lat=12.9719, lon=77.5937),
    # 香港 / 澳门 / 台北：统一归属中国
    "hongkong": dict(country="中国", admin="香港特别行政区"),
    "macau": dict(country="中国", admin="澳门特别行政区"),
    "taipei": dict(country="中国", admin="台湾省"),
}

with open(P, encoding="utf-8") as f:
    cities = json.load(f)

by_id = {c["id"]: c for c in cities}
for cid, patch in FIX.items():
    by_id[cid].update(patch)

with open(P, "w", encoding="utf-8") as f:
    json.dump(cities, f, ensure_ascii=False, indent=1)

for cid in ("suzhou", "xian", "newyork", "bangalore", "hongkong", "taipei"):
    c = by_id[cid]
    print(cid, c["name"], c["admin"], c["lat"], c["lon"])
print("total", len(cities))
