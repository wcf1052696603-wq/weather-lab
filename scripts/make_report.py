# -*- coding: utf-8 -*-
"""生成两城气候对比报告（自包含 HTML，含内联 SVG 图表）。

用法: python make_report.py 惠州 芜湖
输出: 全年气候对比_惠州_vs_芜湖.html
"""
import html
import json
import os
import sys

from climate_core import (DIMS, advise, avg, band_of, derive, score_city, similar)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

C_A, C_B = '#2563eb', '#e11d48'
MONTHS = [f'{i}月' for i in range(1, 13)]


# --------------------------------------------------------------------------
# SVG 基础
# --------------------------------------------------------------------------
class Chart:
    def __init__(self, w=960, h=400, pl=58, pr=64, pt=22, pb=48):
        self.w, self.h, self.pl, self.pr, self.pt, self.pb = w, h, pl, pr, pt, pb
        self.body = []

    def sx(self, i, n=11):
        return self.pl + i * (self.w - self.pl - self.pr) / n

    def sy(self, v, lo, hi):
        return self.pt + (hi - v) / (hi - lo) * (self.h - self.pt - self.pb)

    def add(self, s):
        self.body.append(s)

    def frame(self, lo, hi, ticks, unit, step=1):
        for t in ticks:
            y = self.sy(t, lo, hi)
            self.add(f'<line x1="{self.pl}" y1="{y:.1f}" x2="{self.w-self.pr}" '
                     f'y2="{y:.1f}" stroke="#eef2f7" stroke-width="1"/>')
            self.add(f'<text x="{self.pl-9}" y="{y+4:.1f}" text-anchor="end" '
                     f'font-size="11.5" fill="#94a3b8">{t:g}</text>')
        self.add(f'<text x="{self.pl-9}" y="{self.pt-6}" text-anchor="end" '
                 f'font-size="11" fill="#b6c2cf">{unit}</text>')
        for i in range(12):
            x = self.sx(i)
            self.add(f'<text x="{x:.1f}" y="{self.h-self.pb+20}" text-anchor="middle" '
                     f'font-size="11.5" fill="#94a3b8">{MONTHS[i]}</text>')

    def legend(self, items, x=None):
        x = self.pl if x is None else x
        for name, color, dash in items:
            self.add(f'<rect x="{x}" y="{self.pt-16}" width="16" height="3" rx="1.5" fill="{color}"'
                     + (f' stroke-dasharray="{dash}"' if dash else '') + '/>')
            self.add(f'<text x="{x+21}" y="{self.pt-11}" font-size="12" fill="#5b6b7c">{name}</text>')
            x += 24 + len(name) * 12.5

    def render(self):
        return (f'<svg viewBox="0 0 {self.w} {self.h}" width="100%" '
                f'style="display:block" xmlns="http://www.w3.org/2000/svg">'
                + ''.join(self.body) + '</svg>')

    def path(self, vals, lo, hi, close_to=None):
        pts = [f'{"M" if i == 0 else "L"}{self.sx(i):.1f},{self.sy(v, lo, hi):.1f}'
               for i, v in enumerate(vals)]
        return ' '.join(pts)


def nice_range(vals, pad=4, step=5):
    lo = min(vals) - pad
    hi = max(vals) + pad
    lo = int(lo // step * step)
    hi = int(-(-hi // step) * step)
    return lo, hi


def ticks_between(lo, hi, n=5):
    return [lo + (hi - lo) * i / n for i in range(n + 1)]


# --------------------------------------------------------------------------
# 图表：全年气温对比
# --------------------------------------------------------------------------
def chart_temperature(city_a, city_b, name_a, name_b):
    allv = []
    for c in (city_a, city_b):
        allv += [x['tMax'] for x in c['monthly']] + [x['tMin'] for x in c['monthly']]
    lo, hi = nice_range(allv, 5, 5)
    ch = Chart()
    ch.frame(lo, hi, ticks_between(lo, hi), '℃')
    for city, name, color in ((city_a, name_a, C_A), (city_b, name_b, C_B)):
        tmax = [x['tMax'] for x in city['monthly']]
        tmin = [x['tMin'] for x in city['monthly']]
        tmean = [x['tMean'] for x in city['monthly']]
        band = ch.path(tmax, lo, hi) + ' L' + ','.join(
            f'{ch.sx(i):.1f},{ch.sy(tmin[i], lo, hi):.1f}' for i in range(11, -1, -1)) + ' Z'
        ch.add(f'<path d="{band}" fill="{color}" opacity=".13"/>')
        ch.add(f'<path d="{ch.path(tmax, lo, hi)}" fill="none" stroke="{color}" '
               f'stroke-width="1.8" stroke-dasharray="5 4" opacity=".85"/>')
        ch.add(f'<path d="{ch.path(tmin, lo, hi)}" fill="none" stroke="{color}" '
               f'stroke-width="1.8" stroke-dasharray="5 4" opacity=".85"/>')
        ch.add(f'<path d="{ch.path(tmean, lo, hi)}" fill="none" stroke="{color}" stroke-width="3"/>')
        for i, v in enumerate(tmean):
            ch.add(f'<circle cx="{ch.sx(i):.1f}" cy="{ch.sy(v, lo, hi):.1f}" r="3.4" '
                   f'fill="#fff" stroke="{color}" stroke-width="2.2">'
                   f'<title>{name} {MONTHS[i]} 月均温 {v}℃</title></circle>')
    ch.legend([(f'{name_a} 月均温', C_A, None), (f'{name_b} 月均温', C_B, None),
               ('虚线=平均最高/最低', '#94a3b8', '4 3')], x=ch.pl)
    return ch.render()


# --------------------------------------------------------------------------
# 图表：降水量分组柱状
# --------------------------------------------------------------------------
def chart_bars(city_a, city_b, name_a, name_b, field, unit, label):
    """分组柱状图（降水 / 太阳辐射等月度对比）。"""
    ch = Chart(h=380)
    vals = [x[field] for x in city_a['monthly']] + [x[field] for x in city_b['monthly']]
    hi = max(vals) * 1.18
    step = 50 if hi > 200 else (5 if hi > 20 else (2 if hi > 6 else 1))
    hi = int(hi // step * step + step)
    ch.frame(0, hi, ticks_between(0, hi), unit)
    bw = (ch.w - ch.pl - ch.pr) / 12 * 0.36
    gap = (ch.w - ch.pl - ch.pr) / 12
    for series, city, name, color in ((0, city_a, name_a, C_A), (1, city_b, name_b, C_B)):
        for i, x in enumerate(city['monthly']):
            x0 = ch.sx(i) - gap * 0.42 + series * (bw + 2)
            top = ch.sy(x[field], 0, hi)
            hgt = ch.sy(0, 0, hi) - top
            ch.add(f'<rect x="{x0:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(hgt,0):.1f}" '
                   f'rx="3" fill="{color}" opacity="{0.92 if series==0 else 0.85}">'
                   f'<title>{name} {MONTHS[i]} {x[field]:.1f}{unit}</title></rect>')
    ch.legend([(f'{name_a} {label}', C_A, None), (f'{name_b} {label}', C_B, None)], x=ch.pl)
    return ch.render()


# --------------------------------------------------------------------------
# 图表：湿度折线
# --------------------------------------------------------------------------
def chart_humidity(city_a, city_b, name_a, name_b):
    ch = Chart(h=340)
    ch.frame(30, 100, [30, 45, 60, 75, 90, 100], '%')
    ch.add(f'<line x1="{ch.pl}" y1="{ch.sy(80,30,100):.1f}" x2="{ch.w-ch.pr}" '
           f'y2="{ch.sy(80,30,100):.1f}" stroke="#c9a227" stroke-width="1.4" stroke-dasharray="5 4"/>')
    ch.add(f'<text x="{ch.w-ch.pr-4}" y="{ch.sy(80,30,100)-6:.1f}" text-anchor="end" '
           f'font-size="11" fill="#c9a227">80% 高湿线</text>')
    for city, name, color in ((city_a, name_a, C_A), (city_b, name_b, C_B)):
        vals = [x['rh'] for x in city['monthly']]
        ch.add(f'<path d="{ch.path(vals,30,100)}" fill="none" stroke="{color}" stroke-width="3"/>')
        for i, v in enumerate(vals):
            ch.add(f'<circle cx="{ch.sx(i):.1f}" cy="{ch.sy(v,30,100):.1f}" r="3.4" fill="#fff" '
                   f'stroke="{color}" stroke-width="2.2"><title>{name} {MONTHS[i]} 湿度 {v}%</title></circle>')
    ch.legend([(f'{name_a} 相对湿度', C_A, None), (f'{name_b} 相对湿度', C_B, None)], x=ch.pl)
    return ch.render()


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def esc(s):
    return html.escape(str(s))


def metric_row(city):
    d = derive(city)
    a = d['a']
    return {
        'tMean': a['tMean'], 'tMax': a['tMaxAvg'], 'tMin': a['tMinAvg'],
        'warmest': a['warmestT'], 'warmest_m': a['warmestMonth'],
        'coldest': a['coldestT'], 'coldest_m': a['coldestMonth'],
        'range': a['range'], 'precip': a['precip'], 'rainDays': a['rainDays'],
        'heavy': a['heavy'], 'storm': a['storm'], 'maxDaily': a['maxDaily'],
        'rh': a['rh'], 'humidMonths': d['humid_months'],
        'rad': a.get('rad', 0), 'wind': a['wind'],
        'comfort': a['comfort'], 'hot30': a['hot30'], 'hot35': a['hot35'],
        'frost': a['frost'], 'absMax': a['absMax'], 'absMin': a['absMin'],
        'hdd': d['hdd'], 'cdd': d['cdd'], 'conc3': d['conc3'] * 100,
    }


def delta_txt(v, dig=1, unit=''):
    return ('+' if v > 0 else '') + f'{v:.{dig}f}' + unit


def main():
    with open(os.path.join(DATA, 'climate.json'), encoding='utf-8') as f:
        payload = json.load(f)
    cities = payload['cities']
    meta = payload['meta']

    name_a = sys.argv[1] if len(sys.argv) > 1 else '惠州'
    name_b = sys.argv[2] if len(sys.argv) > 2 else '芜湖'
    id_a = next(k for k, v in cities.items() if v['name'] == name_a)
    id_b = next(k for k, v in cities.items() if v['name'] == name_b)
    ca, cb = cities[id_a], cities[id_b]

    sa, sb = score_city(ca), score_city(cb)
    ra, rb = advise(ca), advise(cb)
    ma, mb = metric_row(ca), metric_row(cb)
    sim_a = similar(cities, id_a, 5)
    sim_b = similar(cities, id_b, 5)

    # ---------------- 结论：不同诉求下的优选 ----------------
    def pick(higher_better, va, vb, label, unit='', dig=1, note='', tol=0.0):
        if abs(va - vb) <= tol:
            return dict(label=label, winner='基本持平', dif=abs(va - vb),
                        unit=unit, dig=dig, note=note, tie=True)
        winner, loser = (name_a, name_b) if ((va > vb) == higher_better) else (name_b, name_a)
        vi, vl = (va, vb) if winner == name_a else (vb, va)
        return dict(label=label, winner=winner, dif=abs(vi - vl), unit=unit, dig=dig,
                    note=note, tie=False)

    picks = [
        pick(True, ma['coldest'], mb['coldest'], '冬天更暖（最冷月均温）', '℃', 1,
             f"最冷月 {name_a} {ma['coldest']}℃ / {name_b} {mb['coldest']}℃", 0.5),
        pick(False, ma['frost'], mb['frost'], '冬季霜冻更少', ' 天', 1,
             f"{name_a} {ma['frost']:.0f} 天 / {name_b} {mb['frost']:.0f} 天", 3),
        pick(False, ma['warmest'], mb['warmest'], '夏天更凉（最热月均温）', '℃', 1,
             f"{name_a} {ma['warmest']}℃ / {name_b} {mb['warmest']}℃", 0.5),
        pick(False, ma['hot35'], mb['hot35'], '酷热日（≥35℃）更少', ' 天', 1,
             f"{name_a} {ma['hot35']:.0f} 天 / {name_b} {mb['hot35']:.0f} 天", 2),
        pick(False, ma['rh'], mb['rh'], '空气更干爽（年均湿度）', '%', 1,
             f"{name_a} {ma['rh']}% / {name_b} {mb['rh']}%", 1.5),
        pick(False, ma['humidMonths'], mb['humidMonths'], '高湿月份（≥80%）更少', ' 个', 0,
             f"{name_a} {ma['humidMonths']:.0f} 个 / {name_b} {mb['humidMonths']:.0f} 个", 1),
        pick(False, ma['storm'], mb['storm'], '特大暴雨日更少', ' 天', 1,
             f"{name_a} {ma['storm']:.0f} 天 / {name_b} {mb['storm']:.0f} 天", 0.5),
        pick(True, ma['rad'], mb['rad'], '光照更充足（年均辐射）', ' MJ/m²·日', 1,
             f"{name_a} {ma['rad']:.1f} / {name_b} {mb['rad']:.1f}", 0.5),
        pick(True, ma['comfort'], mb['comfort'], '体感舒适天数更多', ' 天', 0,
             f"{name_a} {ma['comfort']:.0f} 天 / {name_b} {mb['comfort']:.0f} 天", 10),
        pick(True, ma['range'], mb['range'], '四季更分明（年温差大）', '℃', 1,
             f"{name_a} {ma['range']}℃ / {name_b} {mb['range']}℃", 1),
    ]

    # ---------------- 指标对比表 ----------------
    rows = [
        ('年均气温', '℃', ma['tMean'], mb['tMean'], 1, None),
        ('平均日最高温', '℃', ma['tMax'], mb['tMax'], 1, None),
        ('平均日最低温', '℃', ma['tMin'], mb['tMin'], 1, None),
        (f"最热月均温（{ma['warmest_m']}月 / {mb['warmest_m']}月）", '℃', ma['warmest'], mb['warmest'], 1, None),
        (f"最冷月均温（{ma['coldest_m']}月 / {mb['coldest_m']}月）", '℃', ma['coldest'], mb['coldest'], 1, 1),
        ('年温差（最热月−最冷月）', '℃', ma['range'], mb['range'], 1, None),
        ('年降水量', 'mm', ma['precip'], mb['precip'], 0, None),
        ('年降水日数（≥1mm）', '天', ma['rainDays'], mb['rainDays'], 0, None),
        ('暴雨日（≥25mm）', '天', ma['heavy'], mb['heavy'], 1, -1),
        ('特大暴雨日（≥50mm）', '天', ma['storm'], mb['storm'], 1, -1),
        ('十年最大单日降水', 'mm', ma['maxDaily'], mb['maxDaily'], 0, -1),
        ('降水集中度（最湿3月占比）', '%', ma['conc3'], mb['conc3'], 0, None),
        ('年均相对湿度', '%', ma['rh'], mb['rh'], 1, None),
        ('高湿月份（≥80%）', '个', ma['humidMonths'], mb['humidMonths'], 0, -1),
        ('年均太阳辐射', 'MJ/m²·日', ma['rad'], mb['rad'], 1, 1),
        ('年平均风速(WS2M)', 'km/h', ma['wind'], mb['wind'], 1, 0),
        ('体感舒适天数', '天', ma['comfort'], mb['comfort'], 0, 1),
        ('≥30℃ 天数', '天', ma['hot30'], mb['hot30'], 0, -1),
        ('≥35℃ 天数', '天', ma['hot35'], mb['hot35'], 1, -1),
        ('霜冻天数', '天', ma['frost'], mb['frost'], 1, -1),
        ('十年极端最高 / 最低', '℃', f"{ma['absMax']:.1f} / {ma['absMin']:.1f}",
         f"{mb['absMax']:.1f} / {mb['absMin']:.1f}", None, None),
        ('采暖度日 HDD（基准18℃）', '', ma['hdd'], mb['hdd'], 0, -1),
        ('制冷度日 CDD（基准24℃）', '', ma['cdd'], mb['cdd'], 0, -1),
        ('宜居参考分（默认权重）', '分', sa['total'], sb['total'], 0, 1),
    ]

    def row_html(label, unit, va, vb, dig, direction):
        cells = []
        for v in (va, vb):
            cells.append(f'<td>{v:.{dig}f}</td>' if dig is not None else f'<td>{v}</td>')
        if dig is not None:
            dv = vb - va
            cls = 'pos' if dv > 0 else ('neg' if dv < 0 else '')
            cells.append(f'<td class="{cls}">{delta_txt(dv, dig)}</td>')
        else:
            cells.append('<td class="muted">—</td>')
        if direction is None:
            best = '<span class="muted">中性</span>'
        else:
            score_a, score_b = (va, vb) if direction == 1 else (-va, -vb)
            try:
                score_a, score_b = float(score_a), float(score_b)
                if abs(score_a - score_b) < 1e-9:
                    best = '<span class="muted">持平</span>'
                elif score_a > score_b:
                    best = f'<b>{esc(name_a)}</b>'
                else:
                    best = f'<b>{esc(name_b)}</b>'
            except (TypeError, ValueError):
                best = '<span class="muted">—</span>'
        unit_html = f' <span class="unit">{esc(unit)}</span>' if unit else ''
        return (f'<tr><td class="lbl">{esc(label)}{unit_html}</td>' + ''.join(cells)
                + f'<td>{best}</td></tr>')

    table_html = ''.join(row_html(*r) for r in rows)

    # ---------------- 舒适度色带 ----------------
    def strip(city, name):
        d = derive(city)
        cells = []
        for i, x in enumerate(city['monthly']):
            label, color = band_of(d['at'][i])
            cells.append(
                f'<div class="sc" style="background:{color}" '
                f'title="{MONTHS[i]} 月均温 {x["tMean"]}℃／湿度 {x["rh"]:.0f}%／体感 {d["at"][i]:.1f}℃">'
                f'<b>{i+1}月</b><span>{label}</span><em>{d["at"][i]:.0f}℃</em></div>')
        return (f'<div class="strip-row"><span class="strip-name">{esc(name)}</span>'
                f'<div class="strip">{"".join(cells)}</div></div>')

    # ---------------- 建议 ----------------
    def advice_html(res, city, name, color):
        items = ''
        for it in res['items']:
            items += (f'<div class="adv lv-{it["level"]}"><div class="ico">{it["icon"]}</div>'
                      f'<div><div class="t">{esc(it["title"])}</div>'
                      f'<div class="x">{esc(it["text"])}</div></div></div>')
        dm = res['score']['dims']
        bars = ''
        for key, label in DIMS:
            v = dm[key]
            col = '#0f7b6c' if v >= 75 else '#3f9d8f' if v >= 60 else '#c9a227' if v >= 45 else '#c2691a'
            bars += (f'<div class="dim"><div class="dt"><span>{label}</span>'
                     f'<span>{v:.0f} 分</span></div>'
                     f'<div class="db"><i style="width:{v:.0f}%;background:{col}"></i></div></div>')
        return (f'<div class="card city-card" style="--c:{color}">'
                f'<div class="cc-head"><div class="cc-name">{esc(name)}</div>'
                f'<div class="cc-score"><b style="color:{color}">{res["score"]["total"]:.0f}</b>'
                f'<span>宜居参考分 · {esc(res["score"]["verdict"][0])}</span></div></div>'
                f'<p class="verdict">{esc(res["score"]["verdict"][1])}</p>'
                f'<div class="dims">{bars}</div>'
                f'<div class="adv-list">{items}</div></div>')

    def sim_html(sim, color, name):
        out = []
        for cid, dist, simv in sim:
            c = cities[cid]
            out.append(f'<span class="sim"><b>{esc(c["name"])}</b>'
                       f'<span class="m">{esc(c["admin"] or c["country"])}</span>'
                       f'<span class="p" style="color:{color}">{simv:.0f}%</span></span>')
        return ''.join(out)

    picks_html = ''
    for p in picks:
        cls = 'pw tie' if p.get('tie') else 'pw'
        picks_html += (f'<li><span class="pk">{esc(p["label"])}</span>'
                       f'<span class="{cls}">{esc(p["winner"])}</span>'
                       f'<span class="pd">{p["note"]}</span></li>')

    css = """
    *{box-sizing:border-box}
    body{margin:0;background:#eef2f7;color:#0f172a;font:14px/1.65 "Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif}
    .wrap{max-width:1060px;margin:0 auto;padding:26px 20px 60px}
    h1{font-size:25px;margin:0 0 6px;letter-spacing:-.3px}
    h2{font-size:17px;margin:30px 0 12px;padding-left:11px;border-left:4px solid #0b7285}
    .sub{color:#64748b;font-size:13px;margin-bottom:20px}
    .card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 20px;margin-bottom:14px;
          box-shadow:0 1px 2px rgba(15,23,42,.05)}
    .hero{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .hero .card{margin:0;border-top:3px solid var(--c)}
    .cc-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
    .cc-name{font-size:19px;font-weight:650}
    .cc-score{text-align:right}
    .cc-score b{font-size:26px;letter-spacing:-.5px}
    .cc-score span{display:block;font-size:11.5px;color:#64748b}
    .verdict{margin:8px 0 14px;font-size:13px;color:#334155}
    .metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:9px;margin-top:4px}
    .metric{background:#f7f9fc;border:1px solid #e9eef4;border-radius:9px;padding:9px 11px}
    .metric .l{font-size:11.5px;color:#64748b}
    .metric .v{font-size:17px;font-weight:650;font-variant-numeric:tabular-nums}
    .metric .v small{font-size:11.5px;font-weight:500;color:#94a3b8;margin-left:2px}
    .dims{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px 20px;margin:12px 0 4px}
    .dt{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:3px}
    .dt span:last-child{color:#64748b}
    .db{height:7px;background:#eef2f7;border-radius:4px;overflow:hidden}
    .db i{display:block;height:100%;border-radius:4px}
    .adv-list{display:flex;flex-direction:column;gap:8px;margin-top:14px}
    .adv{display:flex;gap:10px;padding:10px 12px;border-radius:10px;border:1px solid #e2e8f0;background:#f7f9fc}
    .adv .ico{flex:0 0 auto;width:22px;height:22px;border-radius:7px;display:grid;place-items:center;
              background:#e4f3f5;font-size:12px}
    .adv .t{font-weight:600;font-size:13px}
    .adv .x{font-size:12.5px;color:#334155}
    .adv.lv-warn{background:#fef6e7;border-color:#f3dfae}.adv.lv-warn .ico{background:#fdedcd;color:#b45309}
    .adv.lv-good{background:#e8f6ef;border-color:#c6e8d6}.adv.lv-good .ico{background:#d6f0e1;color:#067647}
    .adv.lv-info .ico{background:#e4f3f5;color:#0b7285}
    .chart{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px 14px 8px;margin-bottom:16px}
    .chart h3{margin:0 0 10px 6px;font-size:14px;font-weight:650}
    .chart p.desc{margin:0 0 8px 6px;font-size:12.5px;color:#64748b}
    table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:8px 10px;border-bottom:1px solid #eef2f7;text-align:right;font-variant-numeric:tabular-nums}
    th{background:#f7f9fc;font-size:12.5px;color:#334155;font-weight:600;white-space:nowrap}
    td.lbl{text-align:left}
    td .unit{color:#94a3b8;font-size:11.5px}
    .tbl{border:1px solid #e2e8f0;border-radius:11px;overflow:hidden}
    td.pos{color:#b42318}td.neg{color:#067647}
    .muted{color:#94a3b8}
    .strip-row{display:flex;align-items:center;gap:10px;margin-bottom:7px}
    .strip-name{flex:0 0 52px;font-size:12.5px;color:#334155;font-weight:600}
    .strip{display:grid;grid-template-columns:repeat(12,1fr);gap:3px;flex:1}
    .sc{border-radius:5px;padding:5px 2px;text-align:center;color:#fff;line-height:1.25}
    .sc b{display:block;font-size:10.5px;opacity:.92}
    .sc span{font-size:11px}
    .sc em{display:block;font-size:10px;font-style:normal;opacity:.85}
    .legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:12px;color:#64748b}
    .legend i{width:10px;height:10px;border-radius:3px;display:inline-block;margin-right:5px}
    ul.picks{list-style:none;padding:0;margin:0}
    ul.picks li{display:grid;grid-template-columns:minmax(180px,1fr) 74px 1.4fr;gap:10px;
                align-items:center;padding:9px 4px;border-bottom:1px dashed #e6ecf2}
    ul.picks li:last-child{border-bottom:none}
    .pk{font-size:13px;color:#334155}
    .pw{font-weight:700;color:#0b7285}
    .pw.tie{color:#94a3b8;font-weight:600}
    .pd{font-size:12.5px;color:#64748b}
    .sim{display:inline-flex;align-items:center;gap:8px;padding:6px 11px;border:1px solid #e2e8f0;
         border-radius:9px;background:#f7f9fc;font-size:12.5px;margin:0 8px 8px 0}
    .sim .m{color:#94a3b8}
    .sim .p{font-weight:600}
    .note{font-size:12px;color:#7b8896;line-height:1.8}
    .two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    @media (max-width:860px){.two,.hero{grid-template-columns:1fr}}
    @media print{body{background:#fff}.wrap{max-width:none;padding:0}
      .card,.chart{box-shadow:none;break-inside:avoid}}
    """

    def metrics_block(city, m):
        d = derive(city)
        items = [
            ('年均气温', f"{m['tMean']}", '℃', f"最高 {m['tMax']} / 最低 {m['tMin']}"),
            ('年降水量', f"{m['precip']:.0f}", 'mm', f"雨日 {m['rainDays']:.0f} 天"),
            ('年均湿度', f"{m['rh']}", '%', f"≥80% 月份 {m['humidMonths']:.0f} 个"),
            ('年均太阳辐射', f"{m['rad']:.1f}", 'MJ/m²·日', f"最弱 {d['rad_min_idx']+1}月 {d['rad_min']:.1f} MJ"),
            ('体感舒适天数', f"{m['comfort']:.0f}", '天', '气温 15~25℃ 且湿度 ≤75%'),
            ('年温差', f"{m['range']}", '℃', f"{m['coldest_m']}月↔{m['warmest_m']}月"),
        ]
        return ''.join(f'<div class="metric"><div class="l">{l}</div>'
                       f'<div class="v">{v}<small>{u}</small></div>'
                       f'<div class="l">{s}</div></div>' for l, v, u, s in items)

    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全年气候对比 · {esc(name_a)} vs {esc(name_b)}</title>
<style>{css}</style></head><body><div class="wrap">

<h1>全年气候对比：{esc(name_a)} vs {esc(name_b)}</h1>
<div class="sub">
  数据来源 NASA POWER Daily API（MERRA-2 再分析）·
  统计期 {esc(meta['start'])} ~ {esc(meta['end'])}（10 年逐日 → 月度常年值）·
  生成日期 {esc(meta['generated'])} ·
  {esc(ca['admin'] or ca['country'])} {ca['lat']}°N {ca['lon']}°E 海拔 {ca['elev']:.0f}m ／
  {esc(cb['admin'] or cb['country'])} {cb['lat']}°N {cb['lon']}°E 海拔 {cb['elev']:.0f}m
</div>

<div class="hero">
  <div class="card city-card" style="--c:{C_A}">
    <div class="cc-head"><div class="cc-name">{esc(name_a)}</div>
      <div class="cc-score"><b style="color:{C_A}">{sa['total']:.0f}</b>
      <span>宜居参考分 · {esc(sa['verdict'][0])}</span></div></div>
    <div class="metrics">{metrics_block(ca, ma)}</div>
  </div>
  <div class="card city-card" style="--c:{C_B}">
    <div class="cc-head"><div class="cc-name">{esc(name_b)}</div>
      <div class="cc-score"><b style="color:{C_B}">{sb['total']:.0f}</b>
      <span>宜居参考分 · {esc(sb['verdict'][0])}</span></div></div>
    <div class="metrics">{metrics_block(cb, mb)}</div>
  </div>
</div>

<h2>一、全年气温对比</h2>
<div class="chart"><h3>月平均气温｜阴影为平均最低～最高区间</h3>
<p class="desc">{esc(name_a)} 月均温区间 {min(x['tMean'] for x in ca['monthly']):.1f}~
{max(x['tMean'] for x in ca['monthly']):.1f}℃；{esc(name_b)} 为
{min(x['tMean'] for x in cb['monthly']):.1f}~{max(x['tMean'] for x in cb['monthly']):.1f}℃。
年温差 {esc(name_a)} {ma['range']}℃、{esc(name_b)} {mb['range']}℃。</p>
{chart_temperature(ca, cb, name_a, name_b)}</div>

<h2>二、降水、湿度与光照</h2>
<div class="chart"><h3>月降水量</h3>
<p class="desc">年降水 {esc(name_a)} {ma['precip']:.0f}mm、{esc(name_b)} {mb['precip']:.0f}mm；
最湿 3 个月占全年 {ma['conc3']:.0f}% vs {mb['conc3']:.0f}%；雨日 {ma['rainDays']:.0f} 天 vs {mb['rainDays']:.0f} 天。</p>
{chart_bars(ca, cb, name_a, name_b, 'precip', 'mm', '月降水')}</div>
<div class="chart"><h3>月平均相对湿度</h3>
<p class="desc">年均湿度 {ma['rh']}% vs {mb['rh']}%；≥80% 的高湿月份
{ma['humidMonths']:.0f} 个 vs {mb['humidMonths']:.0f} 个。</p>
{chart_humidity(ca, cb, name_a, name_b)}</div>
<div class="chart"><h3>月均太阳辐射</h3>
<p class="desc">年均辐射 {ma['rad']:.1f} MJ/m²·日 vs {mb['rad']:.1f} MJ/m²·日；
辐射最弱的月份 {esc(name_a)} 为 {derive(ca)['rad_min_idx']+1} 月、{esc(name_b)} 为 {derive(cb)['rad_min_idx']+1} 月。</p>
{chart_bars(ca, cb, name_a, name_b, 'rad', ' MJ/m²·日', '月均辐射')}</div>

<h2>三、体感舒适度日历</h2>
<div class="card">
  <p class="desc" style="margin-top:0">按 Steadman 表观温度（综合气温、湿度、风速）分档，数字为该月体感温度。</p>
  {strip(ca, name_a)}
  {strip(cb, name_b)}
  <div class="legend">
    <span><i style="background:#0f7b6c"></i>舒适 20~25℃</span>
    <span><i style="background:#3f9d8f"></i>较舒适 15~20℃</span>
    <span><i style="background:#c9a227"></i>偏热 25~28℃</span>
    <span><i style="background:#c2691a"></i>炎热 28~32℃</span>
    <span><i style="background:#a33b2f"></i>酷热 ≥32℃</span>
    <span><i style="background:#6b8fa8"></i>偏凉 8~15℃</span>
    <span><i style="background:#4f6f92"></i>寒冷 0~8℃</span>
    <span><i style="background:#3b5a86"></i>严寒 &lt;0℃</span>
  </div>
  <p class="desc" style="margin:12px 0 0">
    体感最舒适时段：{esc(name_a)} {'、'.join(str(x)+'月' for x in derive(ca)['best_months'])}；
    {esc(name_b)} {'、'.join(str(x)+'月' for x in derive(cb)['best_months'])}。
  </p>
</div>

<h2>四、关键指标逐项对比</h2>
<div class="tbl"><table>
<thead><tr><th style="text-align:left">指标</th><th>{esc(name_a)}</th><th>{esc(name_b)}</th>
<th>差值<br><span style="font-weight:400;color:#94a3b8">{esc(name_b)} − {esc(name_a)}</span></th>
<th>更优</th></tr></thead>
<tbody>{table_html}</tbody></table></div>
<p class="note">差值列红=数值更高、绿=数值更低；「更优」列已按各项“好坏方向”单独判断（中性项不做排序）。</p>

<h2>五、按不同诉求怎么选</h2>
<div class="card"><ul class="picks">{picks_html}</ul></div>

<h2>六、居住建议</h2>
<div class="two">
{advice_html(ra, ca, name_a, C_A)}
{advice_html(rb, cb, name_b, C_B)}
</div>

<h2>七、气候相似城市参考</h2>
<div class="card">
  <p class="desc" style="margin-top:0">与 {esc(name_a)} 气候最接近：</p>
  {sim_html(sim_a, C_A, name_a)}
  <p class="desc">与 {esc(name_b)} 气候最接近：</p>
  {sim_html(sim_b, C_B, name_b)}
</div>

<h2>八、方法与口径</h2>
<div class="card note">
  <b>数据来源</b>：NASA POWER Daily API（MERRA-2 再分析；源分辨率 0.5°×0.625°，约 50km；
  NASA 官方对 POWER 的 SYN1DEG 产品做过多源偏差订正）。统计期 {esc(meta['start'])} 至 {esc(meta['end'])}，
  共 10 个完整年份。取值为该网格点的日均/日累计值。<br>
  <b>聚合方式</b>：月度值 = 先计算每年该月的日均值，再对 10 年取平均，避免各月天数不同带来的偏差；
  年度值中的降水、雨日、暴雨日、高温日、霜冻日等为 12 个月之和，即年平均的年总量。<br>
  <b>光照口径</b>：采用<b>入射太阳辐射</b>（MJ/m²·日），即地表短波下行辐射，
  比日照时数更稳定可比，也不依赖各国的日照阈值定义。<br>
  <b>风速</b>：为 2m 平均风速（WS2M），不是日最大风速，仅用于体感与通风参考。<br>
  <b>指标定义</b>：雨日 ≥1mm；暴雨日 ≥25mm；特大暴雨日 ≥50mm；
  采暖度日 HDD = Σ(18℃ − 月均温)×月天数；制冷度日 CDD = Σ(月均温 − 24℃)×月天数（负值取 0）；
  体感温度 = Steadman 表观温度 T + 0.33e − 0.70v − 4.00。<br>
  <b>宜居参考分</b>：由冬季宜居度、夏季宜居度、干湿适宜度、光照条件、降水适宜度、气候温和度六项
  加权（默认权重 0.55+偏好×0.36 等，见程序内可调），满分为 100。<br>
  <b>偏差提示</b>：ERA5 为格点再分析数据，代表城市所在网格的平均状态，与市区自动气象站实测
  可能存在 ±1℃ 量级差异；山地城市（如海拔、地形起伏大者）偏差会更大。
  降水的格点化误差通常大于气温。<br>
  <b>免责声明</b>：本报告为气候数据横向比较工具，评分与建议均由公开数据推导，
  不构成任何购房、投资或医疗建议。
</div>

</div></body></html>
"""

    out = os.path.join(BASE, f'全年气候对比_{name_a}_vs_{name_b}.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html_out)
    print('WROTE', out)

    # 控制台摘要（供后续引用）
    print('\n=== 摘要 ===')
    for nm, m, s in ((name_a, ma, sa), (name_b, mb, sb)):
        print(f"{nm}: 年均{m['tMean']}℃ 最高均{m['tMax']} 最低均{m['tMin']} "
              f"最热{m['warmest']}℃({m['warmest_m']}月) 最冷{m['coldest']}℃({m['coldest_m']}月) "
              f"温差{m['range']} 降水{m['precip']:.0f}mm 雨日{m['rainDays']:.0f} "
              f"暴雨{m['heavy']:.1f} 特大暴雨{m['storm']:.1f} 最大单日{m['maxDaily']:.0f} "
              f"湿度{m['rh']}% 高湿月{m['humidMonths']:.0f} 辐射{m['rad']:.1f}MJ "
              f"舒适{m['comfort']:.0f}天 ≥30℃{m['hot30']:.0f}天 ≥35℃{m['hot35']:.1f}天 "
              f"霜冻{m['frost']:.1f}天 极值{m['absMax']}/{m['absMin']} "
              f"HDD{m['hdd']} CDD{m['cdd']} 评分{s['total']:.1f}({s['verdict'][0]})")
        print('   分项: ' + ', '.join(f'{k}={v:.0f}' for k, v in s['dims'].items()))
    print('\n=== 各诉求优选 ===')
    for p in picks:
        print(f"  {p['label']}: {p['winner']}  ({p['note']})")


if __name__ == '__main__':
    main()
