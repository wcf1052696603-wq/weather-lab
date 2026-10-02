# -*- coding: utf-8 -*-
"""气候评分与居住建议引擎（Python 版）。

与前端 app.js 中的算法保持同一套口径，便于静态报告与交互程序结果一致。
"""
import math

MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月',
          '7月', '8月', '9月', '10月', '11月', '12月']
MDAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

COMFORT_BANDS = [
    (32, '酷热', '#a33b2f'), (28, '炎热', '#c2691a'), (25, '偏热', '#c9a227'),
    (20, '舒适', '#0f7b6c'), (15, '较舒适', '#3f9d8f'), (8, '偏凉', '#6b8fa8'),
    (0, '寒冷', '#4f6f92'), (-99, '严寒', '#3b5a86'),
]


def clamp(v, a, b):
    return max(a, min(b, v))


def piece(v, hard_lo, ideal_lo, ideal_hi, hard_hi):
    """分段线性打分：极端值 0 分，理想区间 100 分。"""
    if v <= hard_lo or v >= hard_hi:
        return 0.0
    if ideal_lo <= v <= ideal_hi:
        return 100.0
    if v < ideal_lo:
        return 100.0 * (v - hard_lo) / (ideal_lo - hard_lo)
    return 100.0 * (hard_hi - v) / (hard_hi - ideal_hi)


def apparent(t, rh, wind_ms):
    """Steadman 表观温度（体感温度）。"""
    e = (rh / 100.0) * 6.105 * math.exp((17.27 * t) / (237.7 + t))
    return t + 0.33 * e - 0.70 * wind_ms - 4.0


def band_of(at):
    for lo, label, color in COMFORT_BANDS:
        if at >= lo:
            return label, color
    return '严寒', '#3b5a86'


def avg(seq):
    seq = list(seq)
    return sum(seq) / len(seq) if seq else 0.0


def derive(city):
    m, a = city['monthly'], city['annual']
    m_temp = [x['tMean'] for x in m]
    m_rh = [x['rh'] for x in m]
    m_p = [x['precip'] for x in m]

    humid_months = sum(1 for x in m if x['rh'] >= 80)
    muggy_months = sum(1 for x in m if x['rh'] >= 78 and x['tMean'] >= 24)
    cold_months = sum(1 for x in m if x['rh'] >= 78 and x['tMean'] <= 12)
    summer_rh = avg([m_rh[5], m_rh[6], m_rh[7], m_rh[8]])
    winter_rh = avg([m_rh[11], m_rh[0], m_rh[1]])
    spring_rh = avg([m_rh[2], m_rh[3]])

    top3 = sorted(m_p, reverse=True)[:3]
    conc3 = (sum(top3) / a['precip']) if a['precip'] else 0.0

    hdd = sum(max(0.0, 18 - x['tMean']) * MDAYS[i] for i, x in enumerate(m))
    cdd = sum(max(0.0, x['tMean'] - 24) * MDAYS[i] for i, x in enumerate(m))

    at = [apparent(x['tMean'], x['rh'], x['wind'] / 3.6) for x in m]
    rank = sorted([(i, at[i], m[i]['precip']) for i in range(12)
                   if 14 <= at[i] <= 26],
                  key=lambda t: (t[2], abs(t[1] - 21)))
    best_months = sorted(t[0] + 1 for t in rank[:3])

    # 光照以入射太阳辐射为准
    rad_arr = [x.get('rad', 0) for x in m]
    rad_min = min(rad_arr)
    rad_min_idx = rad_arr.index(rad_min)
    rad_max = max(rad_arr)
    rad_max_idx = rad_arr.index(rad_max)

    return dict(m=m, a=a, m_temp=m_temp, m_rh=m_rh, m_p=m_p, at=at,
                humid_months=humid_months, muggy_months=muggy_months,
                cold_months=cold_months, summer_rh=summer_rh, winter_rh=winter_rh,
                spring_rh=spring_rh, conc3=conc3, hdd=round(hdd), cdd=round(cdd),
                best_months=best_months,
                rad_min=rad_min, rad_min_idx=rad_min_idx,
                rad_max=rad_max, rad_max_idx=rad_max_idx)


DIMS = [
    ('winter', '冬季宜居度'), ('summer', '夏季宜居度'), ('humid', '干湿适宜度'),
    ('sun', '光照条件'), ('rain', '降水适宜度'), ('stable', '气候温和度'),
]


def score_city(city, prefs=None):
    prefs = prefs or dict(cold=3, heat=3, humid=3, sun=3)
    d = derive(city)
    a = d['a']

    winter = clamp(piece(a['coldestT'], -22, 6, 20, 29) - min(28, a['frost'] * 0.9), 0, 100)
    summer = clamp(piece(a['warmestT'], 12, 19, 27, 36)
                   - min(30, a['hot35'] * 2.0)
                   - max(0, d['summer_rh'] - 78) * 1.3
                   - min(12, a['hot30'] * 0.12), 0, 100)
    humid = clamp(piece(a['rh'], 28, 45, 70, 93)
                  - min(22, d['humid_months'] * 3.2)
                  - max(0, 42 - a['rh']) * 1.4, 0, 100)
    sun = clamp(piece(a.get('rad', 12), 6, 13, 20, 24.5)
                - max(0, 9 - d['rad_min']) * 2.0, 0, 100)
    rain = clamp(piece(a['precip'], 150, 550, 1350, 2600)
                 - max(0, d['conc3'] - 0.42) * 170
                 - min(26, a['storm'] * 3 + a['heavy'] * 0.45), 0, 100)
    stable = clamp(100
                   - max(0, a['range'] - 22) * 2.1
                   - max(0, a['absMax'] - 36) * 3.2
                   - max(0, -a['absMin'] - 4) * 3.0
                   - max(0, a['rainDays'] - 155) * 0.5, 0, 100)

    raw = dict(winter=winter, summer=summer, humid=humid, sun=sun, rain=rain, stable=stable)
    W = dict(winter=0.55 + prefs['cold'] * 0.36, summer=0.55 + prefs['heat'] * 0.36,
             humid=0.45 + prefs['humid'] * 0.32, sun=0.42 + prefs['sun'] * 0.30,
             rain=0.75, stable=0.85)
    total = sum(raw[k] * W[k] for k in raw) / sum(W.values())

    if total >= 82:
        v = ('高度宜居', '气候条件优良，四季较为温和，日常适应的“折腾成本”低。')
    elif total >= 72:
        v = ('宜居', '气候总体舒适，个别季节有明显挑战，属于可轻松适应的水平。')
    elif total >= 62:
        v = ('较为宜居', '气候有明显优缺点，选对住房朝向与设备后体验可大幅改善。')
    elif total >= 52:
        v = ('有挑战', '至少一个季节对多数人构成体感压力，需要设备与心理预期上的准备。')
    else:
        v = ('适应成本较高', '气候较为极端或潮湿/严寒明显，长期居住需要较强适应力与配套设备。')
    return dict(dims=raw, weights=W, total=round(total, 1), verdict=v, d=d)


def advise(city, prefs=None):
    s = score_city(city, prefs)
    d = s['d']
    a = d['a']
    out = []

    def add(level, icon, title, text):
        out.append(dict(level=level, icon=icon, title=title, text=text))

    if a['coldestT'] < 12.5 or a['frost'] > 0.5:
        hard = a['coldestT'] < 6 or a['frost'] > 8
        cm = city['monthly'][a['coldestMonth'] - 1]
        add('warn' if hard else 'info', '🔥', '冬季取暖',
            f"最冷月（{a['coldestMonth']}月）平均 {cm['tMean']}℃，"
            f"该月平均日最低 {cm['tMin']}℃、日最高 {cm['tMax']}℃；"
            f"常年霜冻日约 {a['frost']:.0f} 天，十年极端最低 {a['absMin']}℃。"
            + ("建议优先选择带地暖/集中供暖、外墙保温好、主卧朝南的住房；湿冷地区体感低于气温，"
               "除湿＋取暖配合使用更省电。" if hard else "取暖需求不强，备冷暖空调或电暖器即可过冬。"))
    else:
        add('good', '🌤', '冬季无需采暖',
            f"最冷月平均 {a['coldestT']}℃，全年基本无霜冻，冬季以薄外套为主。")

    if a['hot30'] > 25:
        add('warn' if a['hot35'] > 12 else 'info', '❄️', '夏季制冷',
            f"全年约 {a['hot30']:.0f} 天日最高温 ≥30℃，其中 ≥35℃ 约 {a['hot35']:.0f} 天。"
            "空调属刚需；选房避开西晒与无隔热顶层，西墙/屋顶有遮挡的房源夏季电费可省 20%~30%。")
    else:
        add('good', '🍃', '夏季无需长开空调', f"全年 ≥30℃ 天数仅约 {a['hot30']:.0f} 天。")

    if d['summer_rh'] >= 78 or d['muggy_months'] >= 3:
        add('warn', '💧', '夏季湿热',
            f"6~9 月平均湿度 {d['summer_rh']:.1f}%，其中 {d['muggy_months']} 个月高温高湿同时出现。"
            "高湿下体感温度常比实测高 3~5℃，夜间不易降温，建议卧室独立空调并配合除湿模式。")

    if a['rh'] >= 76:
        add('warn', '🧺', '常年潮湿：防霉与晾晒',
            f"年均相对湿度 {a['rh']}%，全年有 {d['humid_months']} 个月 ≥80%。衣物、皮鞋、皮质家具易发霉，"
            "建议配置除湿机＋烘干机，衣柜常备防潮盒，潮湿季节选择晴好午后短时通风。")
    elif a['rh'] < 52:
        add('info', '🌵', '空气偏干', f"年均湿度仅 {a['rh']}%，需加湿器＋润肤，注意鼻腔与呼吸道舒适度。")
    else:
        add('good', '✅', '湿度适宜', f"年均湿度 {a['rh']}%，处于人体较舒适区间，霉变与干燥问题都不突出。")

    if d['spring_rh'] >= 79:
        add('warn', '🌫', '春季返潮（回南天／梅雨）',
            f"3~4 月平均湿度 {d['spring_rh']:.1f}%，为全年最潮时段，墙面地砖易结露返潮。"
            "装修避开该时段刷墙、铺木地板；室内备吸水垫与除湿机，早晚关朝南门窗、午后短时通风。")

    if d['conc3'] >= 0.40 or a['heavy'] > 3:
        add('warn' if a['storm'] >= 1.5 else 'info', '🌧', '雨季与内涝风险',
            f"年降水 {a['precip']:.0f}mm，其中 {d['conc3']*100:.0f}% 集中在最湿的 3 个月；"
            f"暴雨日（≥25mm）约 {a['heavy']:.0f} 天/年，特大暴雨（≥50mm）约 {a['storm']:.0f} 天/年，"
            f"十年最大单日降水 {a['maxDaily']:.0f}mm。选房避开低洼地段与易进水的地下车库，关注市政排水。")
    else:
        add('good', '☂️', '降水分布温和', f"年降水 {a['precip']:.0f}mm，暴雨日少，内涝风险低。")

    if city['lat'] < 27 and a['storm'] >= 0.8:
        add('info', '🌀', '汛期强天气',
            f"位于低纬沿海（{city['lat']:.1f}°N），7~9 月强降水集中，汛期需关注台风与暴雨预警；"
            "阳台物品固定、备应急电源，选房避开临海第一线与老旧外墙。")

    if a.get('rad', 99) < 12.5 or d['rad_min'] < 8.5:
        add('info', '☁️', '光照偏少，晾晒需辅助',
            f"年均入射太阳辐射 {a.get('rad', 0):.1f} MJ/m²·日"
            f"（约 {a.get('rad', 0)/3.6:.1f} kWh/m²·日），"
            f"最弱的 {d['rad_min_idx']+1} 月仅 {d['rad_min']:.1f} MJ/m²·日。"
            "阴雨期衣物难干，烘干机实用度高；选房优先南北通透、带朝南阳台。")
    else:
        add('good', '☀️', '光照充足',
            f"年均入射太阳辐射 {a.get('rad', 0):.1f} MJ/m²·日"
            f"（约 {a.get('rad', 0)/3.6:.1f} kWh/m²·日），"
            f"最强的 {d['rad_max_idx']+1} 月达 {d['rad_max']:.1f} MJ/m²·日；"
            "晾晒与屋顶光伏条件较好。")

    if d['best_months']:
        add('good', '🏃', '最佳户外窗口',
            f"体感最舒适的时段为 {'、'.join(str(x) + '月' for x in d['best_months'])}，"
            f"全年体感舒适（气温 15~25℃ 且湿度 ≤75%）约 {a['comfort']:.0f} 天，"
            "适合安排户外运动与开窗通风。")

    add('info', '🔌', '能源开销参考',
        f"采暖度日 HDD {d['hdd']}、制冷度日 CDD {d['cdd']}（基准 18℃/24℃）。"
        + ("制冷是主要电费来源，隔热与遮阳改造性价比高。" if d['cdd'] > d['hdd'] * 2 else
           "采暖是主要能源支出，保温门窗优先。" if d['hdd'] > d['cdd'] * 2 else
           "采暖与制冷支出相对均衡，全年能源账单较平稳。"))

    health = []
    if a['frost'] > 15:
        health.append('冬季严寒，心脑血管人群需重点保暖')
    if a['range'] > 24:
        health.append(f"年温差达 {a['range']}℃，呼吸道敏感人群换季易不适")
    if a['rh'] >= 80 and d['cold_months'] >= 1:
        health.append('冬春湿冷，关节/风湿人群不适感会放大')
    if a['rh'] < 50:
        health.append('空气干燥，鼻炎与皮肤问题人群需加湿')
    if a.get('rad', 99) < 11.5:
        health.append('日照辐射偏少，注意维生素 D 补充与季节性情绪波动')
    if health:
        add('info', '🩺', '健康提示', '；'.join(health) + '。')

    cloth = []
    if a['coldestT'] < 5:
        cloth.append('厚羽绒服 1~2 件')
    elif a['coldestT'] < 12:
        cloth.append('薄羽绒/厚外套 1 件')
    if a['range'] > 18:
        cloth.append('春秋风衣等过渡装（换季温差大）')
    if a['hot30'] > 40:
        cloth.append('夏季短袖占比高')
    if a['precip'] > 1400:
        cloth.append('防水鞋、速干衣物、常备雨伞')
    add('info', '👕', '衣橱与生活配置', '按当地气候：' + '；'.join(cloth) + '。')

    pros, cons = [], []
    dm = s['dims']
    if dm['winter'] >= 80:
        pros.append('冬季温暖、几乎无取暖负担')
    elif dm['winter'] < 55:
        cons.append('冬季偏冷、取暖成本明显')
    if dm['summer'] >= 75:
        pros.append('夏季不酷热')
    elif dm['summer'] < 55:
        cons.append('夏季炎热漫长、空调依赖强')
    if dm['humid'] >= 75:
        pros.append('湿度舒适')
    elif dm['humid'] < 55:
        cons.append('常年潮湿或干燥明显')
    if dm['sun'] >= 75:
        pros.append('光照条件好')
    if dm['rain'] < 60:
        cons.append('雨季降水集中、暴雨风险偏高')
    if dm['stable'] >= 80:
        pros.append('气候温和、极端天气少')
    elif dm['stable'] < 60:
        cons.append('季节反差大、极端天气较突出')
    add('info', '🏠', '适合与不太适合',
        ('优势：' + '，'.join(pros) + '。' if pros else '')
        + ('需权衡：' + '，'.join(cons) + '。' if cons else '各项指标较均衡，无明显短板。'))

    return dict(score=s, items=out)


def similar(cities, cid, top_n=6):
    """基于 12 个月的均温/湿度/降水向量找气候相似城市。"""
    ids = [k for k, v in cities.items() if v.get('monthly')]
    feats = {}
    for k in ids:
        c = cities[k]
        v = ([x['tMean'] / 10 for x in c['monthly']]
             + [(x['rh'] - 70) / 15 for x in c['monthly']]
             + [math.sqrt(x['precip']) / 6 for x in c['monthly']])
        feats[k] = v
    n = len(feats[ids[0]])
    sd = []
    for j in range(n):
        col = [feats[k][j] for k in ids]
        mu = avg(col)
        sd.append(math.sqrt(avg([(x - mu) ** 2 for x in col])) or 1.0)
    z = {k: [feats[k][j] / sd[j] for j in range(n)] for k in ids}
    res = []
    for k in ids:
        if k == cid:
            continue
        dist = math.sqrt(sum((z[cid][j] - z[k][j]) ** 2 for j in range(n)))
        res.append((k, dist, clamp(100 * math.exp(-dist / 9), 0, 99)))
    res.sort(key=lambda t: t[1])
    return res[:top_n]
