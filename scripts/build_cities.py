# -*- coding: utf-8 -*-
"""通过 Open-Meteo 地理编码 API 构建城市库。

输出:
  data/cities.json      程序使用的城市库
  data/_review.txt      人工校验用（含 admin1，便于发现歧义匹配）
"""
import json
import os
import time
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)

UA = {"User-Agent": "weather-lab/1.0 (personal climate comparison tool)"}

# (id, 中文名, 检索名, 国家代码, 区域, 别名/备注)
CITIES = [
    # ---- 中国：华南 ----
    ("guangzhou", "广州", "Guangzhou", "CN", "中国", "广东 珠三角"),
    ("shenzhen", "深圳", "Shenzhen", "CN", "中国", "广东 珠三角"),
    ("huizhou", "惠州", "Huizhou", "CN", "中国", "广东 珠三角"),
    ("dongguan", "东莞", "Dongguan", "CN", "中国", "广东 珠三角"),
    ("foshan", "佛山", "Foshan", "CN", "中国", "广东 珠三角"),
    ("zhuhai", "珠海", "Zhuhai", "CN", "中国", "广东 珠三角"),
    ("shantou", "汕头", "Shantou", "CN", "中国", "广东 潮汕"),
    ("zhanjiang", "湛江", "Zhanjiang", "CN", "中国", "广东 粤西"),
    ("nanning", "南宁", "Nanning", "CN", "中国", "广西"),
    ("guilin", "桂林", "Guilin", "CN", "中国", "广西"),
    ("haikou", "海口", "Haikou", "CN", "中国", "海南"),
    ("sanya", "三亚", "Sanya", "CN", "中国", "海南"),
    ("hongkong", "香港", "Hong Kong", "HK", "中国", "中国香港"),
    ("macau", "澳门", "Macau", "MO", "中国", "中国澳门"),
    # ---- 中国：西南 ----
    ("kunming", "昆明", "Kunming", "CN", "中国", "云南 春城"),
    ("dali", "大理", "Dali", "CN", "中国", "云南"),
    ("lijiang", "丽江", "Lijiang", "CN", "中国", "云南 高原"),
    ("guiyang", "贵阳", "Guiyang", "CN", "中国", "贵州"),
    ("chengdu", "成都", "Chengdu", "CN", "中国", "四川"),
    ("chongqing", "重庆", "Chongqing", "CN", "中国", "直辖市 火炉"),
    ("lhasa", "拉萨", "Lhasa", "CN", "中国", "西藏 高原"),
    # ---- 中国：华中 / 华东 ----
    ("changsha", "长沙", "Changsha", "CN", "中国", "湖南 火炉"),
    ("wuhan", "武汉", "Wuhan", "CN", "中国", "湖北 火炉"),
    ("nanchang", "南昌", "Nanchang", "CN", "中国", "江西 火炉"),
    ("hefei", "合肥", "Hefei", "CN", "中国", "安徽"),
    ("wuhu", "芜湖", "Wuhu", "CN", "中国", "安徽 皖南"),
    ("nanjing", "南京", "Nanjing", "CN", "中国", "江苏"),
    ("suzhou", "苏州", "Suzhou", "CN", "中国", "江苏"),
    ("hangzhou", "杭州", "Hangzhou", "CN", "中国", "浙江"),
    ("ningbo", "宁波", "Ningbo", "CN", "中国", "浙江"),
    ("wenzhou", "温州", "Wenzhou", "CN", "中国", "浙江"),
    ("yiwu", "义乌", "Yiwu", "CN", "中国", "浙江 金华"),
    ("fuzhou", "福州", "Fuzhou", "CN", "中国", "福建"),
    ("xiamen", "厦门", "Xiamen", "CN", "中国", "福建"),
    ("quanzhou", "泉州", "Quanzhou", "CN", "中国", "福建"),
    ("taipei", "台北", "Taipei", "TW", "中国", "中国台湾"),
    # ---- 中国：华北 / 东北 / 西北 ----
    ("beijing", "北京", "Beijing", "CN", "中国", "直辖市"),
    ("tianjin", "天津", "Tianjin", "CN", "中国", "直辖市"),
    ("shijiazhuang", "石家庄", "Shijiazhuang", "CN", "中国", "河北"),
    ("taiyuan", "太原", "Taiyuan", "CN", "中国", "山西"),
    ("jinan", "济南", "Jinan", "CN", "中国", "山东 火炉"),
    ("qingdao", "青岛", "Qingdao", "CN", "中国", "山东 海滨"),
    ("yantai", "烟台", "Yantai", "CN", "中国", "山东 海滨"),
    ("zhengzhou", "郑州", "Zhengzhou", "CN", "中国", "河南"),
    ("luoyang", "洛阳", "Luoyang", "CN", "中国", "河南"),
    ("xian", "西安", "Xi'an", "CN", "中国", "陕西"),
    ("lanzhou", "兰州", "Lanzhou", "CN", "中国", "甘肃"),
    ("xining", "西宁", "Xining", "CN", "中国", "青海 高原"),
    ("yinchuan", "银川", "Yinchuan", "CN", "中国", "宁夏"),
    ("hohhot", "呼和浩特", "Hohhot", "CN", "中国", "内蒙古"),
    ("urumqi", "乌鲁木齐", "Urumqi", "CN", "中国", "新疆"),
    ("dalian", "大连", "Dalian", "CN", "中国", "辽宁 海滨"),
    ("shenyang", "沈阳", "Shenyang", "CN", "中国", "辽宁"),
    ("changchun", "长春", "Changchun", "CN", "中国", "吉林"),
    ("harbin", "哈尔滨", "Harbin", "CN", "中国", "黑龙江 冰城"),
    ("zhangjiajie", "张家界", "Zhangjiajie", "CN", "中国", "湖南 山地"),
    # ---- 亚洲其他 ----
    ("tokyo", "东京", "Tokyo", "JP", "亚洲", None),
    ("osaka", "大阪", "Osaka", "JP", "亚洲", None),
    ("sapporo", "札幌", "Sapporo", "JP", "亚洲", None),
    ("seoul", "首尔", "Seoul", "KR", "亚洲", None),
    ("busan", "釜山", "Busan", "KR", "亚洲", None),
    ("singapore", "新加坡", "Singapore", "SG", "亚洲", None),
    ("bangkok", "曼谷", "Bangkok", "TH", "亚洲", None),
    ("chiangmai", "清迈", "Chiang Mai", "TH", "亚洲", None),
    ("kualalumpur", "吉隆坡", "Kuala Lumpur", "MY", "亚洲", None),
    ("jakarta", "雅加达", "Jakarta", "ID", "亚洲", None),
    ("manila", "马尼拉", "Manila", "PH", "亚洲", None),
    ("hanoi", "河内", "Hanoi", "VN", "亚洲", None),
    ("hochiminh", "胡志明市", "Ho Chi Minh City", "VN", "亚洲", None),
    ("mumbai", "孟买", "Mumbai", "IN", "亚洲", None),
    ("newdelhi", "新德里", "New Delhi", "IN", "亚洲", None),
    ("bangalore", "班加罗尔", "Bangalore", "IN", "亚洲", None),
    ("dubai", "迪拜", "Dubai", "AE", "亚洲", None),
    ("istanbul", "伊斯坦布尔", "Istanbul", "TR", "亚洲", None),
    # ---- 欧洲 ----
    ("moscow", "莫斯科", "Moscow", "RU", "欧洲", None),
    ("london", "伦敦", "London", "GB", "欧洲", None),
    ("paris", "巴黎", "Paris", "FR", "欧洲", None),
    ("berlin", "柏林", "Berlin", "DE", "欧洲", None),
    ("munich", "慕尼黑", "Munich", "DE", "欧洲", None),
    ("amsterdam", "阿姆斯特丹", "Amsterdam", "NL", "欧洲", None),
    ("zurich", "苏黎世", "Zurich", "CH", "欧洲", None),
    ("madrid", "马德里", "Madrid", "ES", "欧洲", None),
    ("barcelona", "巴塞罗那", "Barcelona", "ES", "欧洲", None),
    ("rome", "罗马", "Rome", "IT", "欧洲", None),
    ("milan", "米兰", "Milan", "IT", "欧洲", None),
    ("athens", "雅典", "Athens", "GR", "欧洲", None),
    ("stockholm", "斯德哥尔摩", "Stockholm", "SE", "欧洲", None),
    ("helsinki", "赫尔辛基", "Helsinki", "FI", "欧洲", None),
    ("reykjavik", "雷克雅未克", "Reykjavik", "IS", "欧洲", None),
    # ---- 北美 ----
    ("newyork", "纽约", "New York", "US", "北美洲", None),
    ("losangeles", "洛杉矶", "Los Angeles", "US", "北美洲", None),
    ("sanfrancisco", "旧金山", "San Francisco", "US", "北美洲", None),
    ("seattle", "西雅图", "Seattle", "US", "北美洲", None),
    ("chicago", "芝加哥", "Chicago", "US", "北美洲", None),
    ("miami", "迈阿密", "Miami", "US", "北美洲", None),
    ("honolulu", "檀香山", "Honolulu", "US", "北美洲", None),
    ("toronto", "多伦多", "Toronto", "CA", "北美洲", None),
    ("vancouver", "温哥华", "Vancouver", "CA", "北美洲", None),
    ("mexicocity", "墨西哥城", "Mexico City", "MX", "北美洲", None),
    # ---- 南美 / 非洲 / 大洋洲 ----
    ("saopaulo", "圣保罗", "Sao Paulo", "BR", "南美洲", None),
    ("buenosaires", "布宜诺斯艾利斯", "Buenos Aires", "AR", "南美洲", None),
    ("lima", "利马", "Lima", "PE", "南美洲", None),
    ("santiago", "圣地亚哥", "Santiago", "CL", "南美洲", None),
    ("cairo", "开罗", "Cairo", "EG", "非洲", None),
    ("nairobi", "内罗毕", "Nairobi", "KE", "非洲", None),
    ("capetown", "开普敦", "Cape Town", "ZA", "非洲", None),
    ("lagos", "拉各斯", "Lagos", "NG", "非洲", None),
    ("sydney", "悉尼", "Sydney", "AU", "大洋洲", None),
    ("melbourne", "墨尔本", "Melbourne", "AU", "大洋洲", None),
    ("perth", "珀斯", "Perth", "AU", "大洋洲", None),
    ("auckland", "奥克兰", "Auckland", "NZ", "大洋洲", None),
    ("wellington", "惠灵顿", "Wellington", "NZ", "大洋洲", None),
]


def geocode(name):
    url = ("https://geocoding-api.open-meteo.com/v1/search?"
           + urllib.parse.urlencode({"name": name, "count": 8,
                                     "language": "zh", "format": "json"}))
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("results") or []


def main():
    out = []
    review = []
    for cid, zh, query, cc, region, note in CITIES:
        try:
            results = geocode(query)
        except Exception as exc:  # noqa: BLE001
            review.append(f"[FAIL] {cid} {zh} :: {exc}")
            continue
        pool = [r for r in results if (r.get("country_code") or "") == cc]
        if not pool:
            pool = results
        best = pool[0]
        rec = {
            "id": cid,
            "name": zh,
            "nameEn": best.get("name") or query,
            "country": best.get("country") or "",
            "countryCode": cc,
            "admin": best.get("admin1") or "",
            "region": region,
            "note": note or "",
            "lat": round(best["latitude"], 4),
            "lon": round(best["longitude"], 4),
            "elev": round(best.get("elevation") or 0, 1),
            "pop": best.get("population") or 0,
        }
        out.append(rec)
        alts = " | ".join(
            f"{r.get('name')}/{r.get('country_code')}/{r.get('admin1')}/{r.get('population')}"
            for r in results[:4])
        review.append(f"{cid:14s} {zh:6s} -> {rec['name']:16s} {rec['countryCode']:3s} "
                      f"{rec['admin']:14s} ({rec['lat']},{rec['lon']}) elev={rec['elev']}\n"
                      f"{'':20s}  候选: {alts}")
        time.sleep(0.25)

    with open(os.path.join(DATA, "cities.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "_review.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(review))
    print(f"cities={len(out)}")


if __name__ == "__main__":
    main()
