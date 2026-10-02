/* =======================================================================
   全年天气对比 · Weather Lab
   数据源：Open-Meteo Historical Weather API (ERA5 再分析)
   预设数据：data/climate-data.js（112 城 / 2015-2024 常年值）
   任意城市：浏览器端实时抓取 + 本地缓存
   ======================================================================= */
(function () {
  'use strict';

  /* ------------------------- 常量 ------------------------- */
  const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月',
                  '7月', '8月', '9月', '10月', '11月', '12月'];
  const MDAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const SERIES = ['#2563eb', '#e11d48', '#b45309', '#059669', '#7c3aed', '#0891b2'];
  const MAX_SEL = 6;
  const PRESET = (window.WEATHER_DATA && window.WEATHER_DATA.cities) || {};
  const META = (window.WEATHER_DATA && window.WEATHER_DATA.meta) || {};
  const LS_KEY = 'weatherlab.custom.v1';

  const state = {
    selected: [],
    primary: null,
    region: '中国',
    tab: 'overview',
    custom: {},                     // 用户在线加入的城市
    charts: {},
    prefs: { cold: 3, heat: 3, humid: 3, sun: 3 },
    simCache: null
  };

  /* ------------------------- 工具 ------------------------- */
  const $ = (s) => document.querySelector(s);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const r1 = (v) => Math.round(v * 10) / 10;
  const fmt = (v, d) => (v === null || v === undefined || !isFinite(v)) ? '—' : v.toFixed(d === undefined ? 1 : d);
  const sum = (a) => a.reduce((s, x) => s + x, 0);
  const avg = (a) => a.length ? sum(a) / a.length : 0;
  const esc = (s) => String(s === undefined || s === null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  /* 分段线性打分：hardLo~idealLo 递增，idealLo~idealHi 满分，idealHi~hardHi 递减 */
  function piece(v, hardLo, idealLo, idealHi, hardHi) {
    if (v <= hardLo || v >= hardHi) return 0;
    if (v >= idealLo && v <= idealHi) return 100;
    if (v < idealLo) return 100 * (v - hardLo) / (idealLo - hardLo);
    return 100 * (hardHi - v) / (hardHi - idealHi);
  }

  /* 露点 / 体感温度（Steadman 表观温度） */
  function dewPoint(t, rh) {
    const g = Math.log(Math.max(rh, 1) / 100) + (17.27 * t) / (237.7 + t);
    return (237.7 * g) / (17.27 - g);
  }
  function apparent(t, rh, windMs) {
    const e = (rh / 100) * 6.105 * Math.exp((17.27 * t) / (237.7 + t)); // hPa
    return t + 0.33 * e - 0.70 * (windMs || 1.5) - 4.0;
  }

  const COMFORT_BANDS = [
    { min: 32, label: '酷热', color: '#a33b2f' },
    { min: 28, label: '炎热', color: '#c2691a' },
    { min: 25, label: '偏热', color: '#c9a227' },
    { min: 20, label: '舒适', color: '#0f7b6c' },
    { min: 15, label: '较舒适', color: '#3f9d8f' },
    { min: 8, label: '偏凉', color: '#6b8fa8' },
    { min: 0, label: '寒冷', color: '#4f6f92' },
    { min: -99, label: '严寒', color: '#3b5a86' }
  ];
  const bandOf = (at) => COMFORT_BANDS.find((b) => at >= b.min);

  function toast(msg) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.add('on');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('on'), 2200);
  }
  function loading(on, text) {
    if (text) $('#loadingText').textContent = text;
    $('#loading').classList.toggle('on', !!on);
  }

  /* ------------------------- 数据集 ------------------------- */
  function allCities() {
    return Object.assign({}, PRESET, state.custom);
  }
  function getCity(id) {
    return allCities()[id] || null;
  }
  function colorOf(id) {
    const i = state.selected.indexOf(id);
    return i < 0 ? '#94a3b8' : SERIES[i % SERIES.length];
  }

  /* ------------------------- 派生指标 ------------------------- */
  function derive(city) {
    const m = city.monthly, a = city.annual;
    const idx = (arr, keys) => keys.map((k) => arr[(k + 12) % 12]);
    const mTemp = m.map((x) => x.tMean);
    const mRh = m.map((x) => x.rh);
    const mP = m.map((x) => x.precip);

    const humidMonths = m.filter((x) => x.rh >= 80).length;
    const dryAirMonths = m.filter((x) => x.rh < 55).length;
    const muggyMonths = m.filter((x) => x.rh >= 78 && x.tMean >= 24).length;
    const coldMonths = m.filter((x) => x.rh >= 78 && x.tMean <= 12).length;
    const summerRh = avg([mRh[5], mRh[6], mRh[7], mRh[8]]);
    const winterRh = avg([mRh[11], mRh[0], mRh[1]]);
    const springRh = avg([mRh[2], mRh[3]]);

    const sorted = mP.slice().sort((x, y) => y - x);
    const conc3 = a.precip > 0 ? (sorted[0] + sorted[1] + sorted[2]) / a.precip : 0;

    // 采暖度日 / 制冷度日（基准 18℃ / 24℃）
    let hdd = 0, cdd = 0;
    m.forEach((x, i) => {
      hdd += Math.max(0, 18 - x.tMean) * MDAYS[i];
      cdd += Math.max(0, x.tMean - 24) * MDAYS[i];
    });

    // 体感日历
    const at = m.map((x, i) => apparent(x.tMean, x.rh, x.wind / 3.6));
    // 最佳户外月：体感 15~25 且降水少
    const rank = m.map((x, i) => ({ i, at: at[i], p: x.precip }))
      .filter((x) => x.at >= 14 && x.at <= 26)
      .sort((x, y) => (x.p - y.p) || (Math.abs(x.at - 21) - Math.abs(y.at - 21)));
    const bestMonths = rank.slice(0, 3).map((x) => x.i + 1).sort((a2, b2) => a2 - b2);

    /* 光照：以入射太阳辐射为准（比日照时数更稳定可比） */
    const radArr = m.map((x) => x.rad || 0);
    const radMin = Math.min.apply(null, radArr);
    const radMinIdx = radArr.indexOf(radMin);
    const radMax = Math.max.apply(null, radArr);
    const radMaxIdx = radArr.indexOf(radMax);

    return {
      m, a, mTemp, mRh, mP, at, humidMonths, dryAirMonths, muggyMonths, coldMonths,
      summerRh, winterRh, springRh, conc3, hdd: Math.round(hdd), cdd: Math.round(cdd),
      bestMonths, radMin, radMinIdx, radMax, radMaxIdx, idx
    };
  }

  /* ------------------------- 宜居评分 ------------------------- */
  const DIMS = [
    { key: 'winter', label: '冬季宜居度', w: 1 },
    { key: 'summer', label: '夏季宜居度', w: 1 },
    { key: 'humid', label: '干湿适宜度', w: 1 },
    { key: 'sun', label: '光照条件', w: 1 },
    { key: 'rain', label: '降水适宜度', w: 1 },
    { key: 'stable', label: '气候温和度', w: 1 }
  ];

  function scoreCity(city, prefs) {
    const d = derive(city), a = d.a;
    const p = prefs;

    const winter = clamp(piece(a.coldestT, -22, 6, 20, 29) - Math.min(28, a.frost * 0.9), 0, 100);
    const summer = clamp(
      piece(a.warmestT, 12, 19, 27, 36)
      - Math.min(30, a.hot35 * 2.0)
      - Math.max(0, (d.summerRh - 78)) * 1.3
      - Math.min(12, a.hot30 * 0.12), 0, 100);
    const humid = clamp(piece(a.rh, 28, 45, 70, 93)
      - Math.min(22, d.humidMonths * 3.2)
      - Math.max(0, 42 - a.rh) * 1.4, 0, 100);
    const sun = clamp(piece(a.rad || 12, 6, 13, 20, 24.5)
      - Math.max(0, 9 - d.radMin) * 2.0, 0, 100);
    const rain = clamp(piece(a.precip, 150, 550, 1350, 2600)
      - Math.max(0, d.conc3 - 0.42) * 170
      - Math.min(26, a.storm * 3 + a.heavy * 0.45), 0, 100);
    const stable = clamp(100
      - Math.max(0, a.range - 22) * 2.1
      - Math.max(0, a.absMax - 36) * 3.2
      - Math.max(0, -a.absMin - 4) * 3.0
      - Math.max(0, a.rainDays - 155) * 0.5, 0, 100);

    const raw = { winter, summer, humid, sun, rain, stable };
    const W = {
      winter: 0.55 + p.cold * 0.36,
      summer: 0.55 + p.heat * 0.36,
      humid: 0.45 + p.humid * 0.32,
      sun: 0.42 + p.sun * 0.30,
      rain: 0.75,
      stable: 0.85
    };
    const wsum = sum(Object.values(W));
    let total = 0;
    Object.keys(raw).forEach((k) => { total += raw[k] * W[k]; });
    total = total / wsum;

    const verdict =
      total >= 82 ? { tag: '高度宜居', text: '气候条件优良，四季较为温和，日常适应的“折腾成本”低。' } :
      total >= 72 ? { tag: '宜居', text: '气候总体舒适，个别季节有明显的冷/热/湿挑战，属于可轻松适应的水平。' } :
      total >= 62 ? { tag: '较为宜居', text: '气候有明显优缺点，选对住房朝向与设备后体验可大幅改善。' } :
      total >= 52 ? { tag: '有挑战', text: '至少一个季节对多数人构成体感压力，需要设备与心理预期上的准备。' } :
                    { tag: '适应成本较高', text: '气候较为极端或潮湿/严寒明显，长期居住需要较强适应力与配套设备。' };

    return { dims: raw, weights: W, total: r1(total), verdict, d };
  }

  /* ------------------------- 居住建议引擎 ------------------------- */
  function advise(city, prefs) {
    const s = scoreCity(city, prefs);
    const d = s.d, a = d.a, out = [];
    const add = (level, icon, title, text) => out.push({ level, icon, title, text });

    /* 1. 采暖 */
    if (a.coldestT < 12.5 || a.frost > 0.5) {
      const hard = a.coldestT < 6 || a.frost > 8;
      const cm = d.m[a.coldestMonth - 1];
      add(hard ? 'warn' : 'info', '🔥', '冬季取暖',
        `最冷月（${a.coldestMonth} 月）平均 ${fmt(cm.tMean)}℃，该月平均日最低 ${fmt(cm.tMin)}℃、` +
        `日最高 ${fmt(cm.tMax)}℃；常年霜冻日约 ${fmt(a.frost, 0)} 天，十年极端最低 ${fmt(a.absMin)}℃。` +
        (hard ? '建议优先选带地暖/集中供暖、外墙保温好、主卧朝南的住房；湿冷地区体感低于气温，除湿＋取暖配合使用更省电。'
              : '取暖需求不强，备一台冷暖空调或电暖器即可过冬。'));
    } else {
      add('good', '🌤', '冬季无需采暖', `最冷月平均 ${fmt(a.coldestT)}℃，全年无霜冻，冬季以薄外套为主。`);
    }

    /* 2. 制冷 */
    if (a.hot30 > 25) {
      add(a.hot35 > 12 ? 'warn' : 'info', '❄️', '夏季制冷',
        `全年约 ${fmt(a.hot30, 0)} 天日最高温 ≥30℃，其中 ≥35℃ 约 ${fmt(a.hot35, 0)} 天。` +
        `空调属刚需，建议按面积选变频机并做好隔热；选房时避开西晒顶层，屋顶/西墙有遮挡的房源夏季电费可省 20%~30%。`);
    } else {
      add('good', '🍃', '夏季无需长开空调', `全年 ≥30℃ 天数仅约 ${fmt(a.hot30, 0)} 天，主要靠通风降温。`);
    }

    /* 3. 湿热体感 */
    if (d.summerRh >= 78 || d.muggyMonths >= 3) {
      add('warn', '💧', '夏季湿热',
        `6~9 月平均湿度 ${fmt(d.summerRh)}%，其中 ${d.muggyMonths} 个月“高温高湿”同时出现。` +
        `高湿下体感温度常比实测高 3~5℃，夜里不易降温，建议卧室独立空调＋除湿模式，慎选不通风的地下/半地下房源。`);
    }

    /* 4. 常年潮湿与防霉 */
    if (a.rh >= 76) {
      add('warn', '🧺', '常湿地区：防霉与晾晒',
        `年均相对湿度 ${fmt(a.rh)}%，全年有 ${d.humidMonths} 个月 ≥80%。衣物、皮鞋、皮质家具易发霉，` +
        `建议配置除湿机＋烘干机，衣柜常备防潮盒，梅雨期每周至少开窗通风 2~3 次（选晴好午后）。`);
    } else if (a.rh < 52) {
      add('info', '🌵', '空气偏干',
        `年均湿度仅 ${fmt(a.rh)}%，建议加湿器＋润肤，注意鼻腔与呼吸道舒适度，冬季静电明显。`);
    } else {
      add('good', '✅', '湿度适宜', `年均湿度 ${fmt(a.rh)}%，处在人体较舒适的区间，霉变与干燥问题都不突出。`);
    }

    /* 5. 回南天 / 梅雨 */
    if (d.springRh >= 79) {
      add('warn', '🌫', '春季返潮（回南天/梅雨）',
        `3~4 月平均湿度 ${fmt(d.springRh)}%，是全年最潮时段，墙面、地砖易结露返潮。` +
        `装修建议避开该时段做刷墙、铺木地板；室内备吸水垫、除湿机；早晚关闭朝南门窗、午后短时通风。`);
    }

    /* 6. 雨季与内涝 */
    if (d.conc3 >= 0.40 || a.heavy > 3) {
      add(a.storm >= 1.5 ? 'warn' : 'info', '🌧', '雨季与内涝风险',
        `年降水 ${fmt(a.precip, 0)}mm，其中 ${(d.conc3 * 100).toFixed(0)}% 集中在最湿的 3 个月；` +
        `暴雨日（≥25mm）约 ${fmt(a.heavy, 0)} 天／年，特大暴雨（≥50mm）约 ${fmt(a.storm, 0)} 天／年，` +
        `十年最大单日降水 ${fmt(a.maxDaily, 0)}mm。选房避开地势低洼、地下车库易进水的小区，关注市政排水。`);
    } else {
      add('good', '☂️', '降水分布温和', `年降水 ${fmt(a.precip, 0)}mm，暴雨日少，内涝风险低。`);
    }

    /* 7. 台风 / 沿海强降水 */
    if (city.lat < 27 && a.storm >= 0.8) {
      add('info', '🌀', '汛期强天气',
        `位于低纬沿海（${fmt(city.lat, 1)}°N），7~9 月强降水集中，汛期需关注台风与暴雨预警；` +
        `阳台物品固定、备应急电源与饮用水，选房避开临海第一线与老旧小区外墙。`);
    }

    /* 8. 光照与晾晒 */
    if ((a.rad || 0) < 12.5 || d.radMin < 8.5) {
      add('info', '☁️', '光照偏少，晾晒需辅助',
        `年均入射太阳辐射 ${fmt(a.rad, 1)} MJ/m²·日（约 ${fmt((a.rad || 0) / 3.6, 1)} kWh/m²·日），` +
        `最弱的 ${d.radMinIdx + 1} 月只有 ${fmt(d.radMin, 1)} MJ/m²·日。` +
        `阴雨期衣物难晾干，烘干机实用度高；选房优先南北通透、带朝南阳台。`);
    } else {
      add('good', '☀️', '光照充足',
        `年均入射太阳辐射 ${fmt(a.rad, 1)} MJ/m²·日（约 ${fmt((a.rad || 0) / 3.6, 1)} kWh/m²·日），` +
        `最强的 ${d.radMaxIdx + 1} 月达 ${fmt(d.radMax, 1)} MJ/m²·日；晾晒与屋顶光伏条件较好。`);
    }

    /* 9. 舒适窗口期 */
    if (d.bestMonths.length) {
      add('good', '🏃', '最佳户外窗口',
        `体感最舒适的时段为 ${d.bestMonths.map((x) => x + '月').join('、')}，` +
        `全年体感舒适（气温 15~25℃ 且湿度 ≤75%）约 ${fmt(a.comfort, 0)} 天，适合安排户外运动与开窗通风。`);
    }

    /* 10. 能耗参考 */
    add('info', '🔌', '能源开销参考',
      `采暖度日 HDD ${d.hdd}、制冷度日 CDD ${d.cdd}（基准 18℃/24℃）。` +
      (d.cdd > d.hdd * 2 ? '制冷是主要电费来源，夏季电费可达冬季的 2 倍以上，隔热与遮阳改造性价比高。'
       : d.hdd > d.cdd * 2 ? '采暖是主要能源支出，冬季燃气/电费占比高，保温门窗优先。'
       : '采暖与制冷支出相对均衡，全年能源账单比较平稳。'));

    /* 11. 健康提示 */
    const health = [];
    if (a.frost > 15) health.push('冬季严寒，心脑血管人群需重点保暖');
    if (a.range > 24) health.push(`年温差达 ${fmt(a.range)}℃，呼吸道敏感人群换季易不适`);
    if (a.rh >= 80 && d.coldMonths >= 1) health.push('冬春湿冷，关节/风湿人群不适感会放大');
    if (a.rh < 50) health.push('空气干燥，鼻炎与皮肤问题人群需加湿');
    if (a.rad && a.rad < 11.5) health.push('日照辐射偏少，注意维生素 D 补充与季节性情绪波动');
    if (health.length) add('info', '🩺', '健康提示', health.join('；') + '。');

    /* 12. 衣橱配置 */
    const cloth = [];
    if (a.coldestT < 5) cloth.push('厚羽绒服 1~2 件');
    else if (a.coldestT < 12) cloth.push('薄羽绒/厚外套 1 件');
    if (a.range > 18) cloth.push('春秋风衣、长袖过渡装（换季温差大）');
    if (a.hot30 > 40) cloth.push('夏季短袖占比高（5~9 月）');
    if (a.precip > 1400) cloth.push('防水鞋、速干衣物、常备雨伞');
    add('info', '👕', '衣橱与生活配置', `按当地气候：${cloth.join('；')}。`);

    /* 13. 住房与人群建议 */
    const pros = [], cons = [];
    if (s.dims.winter >= 80) pros.push('冬季温暖、几乎无取暖负担');
    else if (s.dims.winter < 55) cons.push('冬季偏冷、取暖成本明显');
    if (s.dims.summer >= 75) pros.push('夏季不酷热');
    else if (s.dims.summer < 55) cons.push('夏季炎热漫长、空调依赖强');
    if (s.dims.humid >= 75) pros.push('湿度舒适');
    else if (s.dims.humid < 55) cons.push('常年潮湿/干燥明显');
    if (s.dims.sun >= 75) pros.push('光照条件好');
    if (s.dims.rain < 60) cons.push('雨季降水集中、暴雨风险偏高');
    if (s.dims.stable >= 80) pros.push('气候温和、极端天气少');
    else if (s.dims.stable < 60) cons.push('季节反差大、极端天气较突出');
    add('info', '🏠', '适合与不太适合',
      (pros.length ? `优势：${pros.join('，')}。` : '') +
      (cons.length ? `需权衡：${cons.join('，')}。` : '各项指标较为均衡，没有明显短板。'));

    return { score: s, items: out };
  }

  /* ------------------------- 相似气候城市 ------------------------- */
  function featureVec(c) {
    const v = [];
    c.monthly.forEach((x) => v.push(x.tMean / 10));       // 温度权重高
    c.monthly.forEach((x) => v.push((x.rh - 70) / 15));
    c.monthly.forEach((x) => v.push(Math.sqrt(x.precip) / 6));
    return v;
  }
  function similarCities(id, topN) {
    const all = allCities();
    if (!state.simCache) {
      const ids = Object.keys(all).filter((k) => all[k].monthly);
      const vecs = ids.map((k) => featureVec(all[k]));
      const n = vecs[0].length;
      const sd = [];
      for (let j = 0; j < n; j++) {
        const col = vecs.map((v) => v[j]);
        const mu = avg(col);
        sd.push(Math.sqrt(avg(col.map((x) => (x - mu) * (x - mu)))) || 1);
      }
      state.simCache = { ids: ids, z: vecs.map((v) => v.map((x, j) => x / sd[j])) };
    }
    const { ids, z } = state.simCache;
    const i = ids.indexOf(id);
    if (i < 0) return [];
    return ids.map((k, j) => {
      if (j === i) return null;
      let s = 0;
      for (let t = 0; t < z[i].length; t++) { const dd = z[i][t] - z[j][t]; s += dd * dd; }
      const dist = Math.sqrt(s);
      return { id: k, dist: dist, sim: clamp(100 * Math.exp(-dist / 9), 0, 99) };
    }).filter(Boolean).sort((a, b) => a.dist - b.dist).slice(0, topN || 6);
  }

  /* ------------------------- 侧栏渲染 ------------------------- */
  const REGIONS = ['中国', '亚洲', '欧洲', '北美洲', '南美洲', '非洲', '大洋洲', '我的城市'];

  function renderRegions() {
    $('#regionTabs').innerHTML = REGIONS.map((r) =>
      `<button data-r="${esc(r)}" class="${r === state.region ? 'active' : ''}">${esc(r)}</button>`).join('');
    $('#regionTabs').querySelectorAll('button').forEach((b) => {
      b.onclick = () => { state.region = b.dataset.r; renderRegions(); renderCityList(); };
    });
  }

  function renderCityList() {
    const all = allCities();
    let ids = Object.keys(all).filter((k) => all[k].monthly);
    if (state.region === '我的城市') ids = ids.filter((k) => state.custom[k]);
    else ids = ids.filter((k) => !state.custom[k] && all[k].region === state.region);
    ids.sort((a, b) => (all[a].annual.tMean - all[b].annual.tMean));

    if (!ids.length) {
      $('#cityList').innerHTML = `<div class="chips-empty" style="padding:10px">
        该分类下暂无城市。可在上方搜索框输入任意城市名（支持全球城市），回车后自动抓取气候数据。</div>`;
      return;
    }
    $('#cityList').innerHTML = ids.map((k) => {
      const c = all[k], on = state.selected.indexOf(k) >= 0;
      return `<button class="city-item ${on ? 'on' : ''}" data-id="${esc(k)}">
        <span>
          <span class="ci-name">${on ? `<i class="ci-dot" style="background:${colorOf(k)}"></i>` : ''}${esc(c.name)}</span>
          <span class="ci-sub">${esc(c.admin || c.country)}</span>
        </span>
        <span class="ci-t">${fmt(c.annual.tMean)}℃ · ${fmt(c.annual.precip, 0)}mm</span>
      </button>`;
    }).join('');
    $('#cityList').querySelectorAll('.city-item').forEach((el) => {
      el.onclick = () => toggleCity(el.dataset.id);
    });
  }

  function renderChips() {
    const box = $('#chips');
    $('#selCount').textContent = state.selected.length + '/' + MAX_SEL;
    $('#primaryHint').style.display = state.selected.length ? 'block' : 'none';
    if (!state.selected.length) {
      box.innerHTML = '<span class="chips-empty">从下方城市库中选择，或搜索任意城市</span>';
      return;
    }
    box.innerHTML = state.selected.map((id) => {
      const c = getCity(id);
      const prim = id === state.primary;
      return `<span class="chip ${prim ? 'is-primary' : ''}" data-id="${esc(id)}">
        <i class="dot" style="background:${colorOf(id)}"></i>
        <span class="star" data-act="primary" title="设为主城市">${prim ? '★' : '☆'}</span>
        <span data-act="primary" style="cursor:pointer">${esc(c ? c.name : id)}</span>
        <span class="x" data-act="remove" title="移除">✕</span>
      </span>`;
    }).join('');
    box.querySelectorAll('.chip').forEach((chip) => {
      chip.querySelectorAll('[data-act]').forEach((el) => {
        el.onclick = (e) => {
          e.stopPropagation();
          const id = chip.dataset.id;
          if (el.dataset.act === 'remove') removeCity(id);
          else { state.primary = id; renderChips(); renderAll(); }
        };
      });
    });
  }

  /* ------------------------- 城市增删 ------------------------- */
  function toggleCity(id) {
    const i = state.selected.indexOf(id);
    if (i >= 0) removeCity(id);
    else addCity(id);
  }
  function addCity(id) {
    if (state.selected.indexOf(id) >= 0) return;
    if (state.selected.length >= MAX_SEL) { toast('最多同时对比 ' + MAX_SEL + ' 个城市'); return; }
    state.selected.push(id);
    if (!state.primary) state.primary = id;
    renderChips(); renderCityList(); renderAll();
  }
  function removeCity(id) {
    state.selected = state.selected.filter((x) => x !== id);
    if (state.primary === id) state.primary = state.selected[0] || null;
    renderChips(); renderCityList(); renderAll();
  }

  /* ------------------------- 主渲染 ------------------------- */
  function renderAll() {
    const n = state.selected.length;
    $('#ovEmpty').style.display = n ? 'none' : 'block';
    $('#ovBody').style.display = n ? 'block' : 'none';
    $('#cmpEmpty').style.display = n >= 2 ? 'none' : 'block';
    $('#cmpBody').style.display = n >= 2 ? 'block' : 'none';
    $('#livEmpty').style.display = n ? 'none' : 'block';
    $('#livBody').style.display = n ? 'block' : 'none';
    $('#tbEmpty').style.display = n ? 'none' : 'block';
    $('#tbBody').style.display = n ? 'block' : 'none';
    if (!n) { destroyCharts(); return; }

    renderOverview();
    if (n >= 2) renderCompare();
    renderLive();
    renderTable();
  }

  function destroyCharts() {
    Object.keys(state.charts).forEach((k) => {
      try { state.charts[k].destroy(); } catch (e) { /* noop */ }
    });
    state.charts = {};
  }
  function mkChart(elId, cfg) {
    if (state.charts[elId]) { state.charts[elId].destroy(); }
    const el = document.getElementById(elId);
    if (!el) return;
    state.charts[elId] = new Chart(el.getContext('2d'), cfg);
  }

  /* ------------------------- 全年概览 ------------------------- */
  let metricRow = null;
  function renderOverview() {
    const c = getCity(state.primary) || getCity(state.selected[0]);
    if (!c) return;
    const s = scoreCity(c, state.prefs);
    const d = s.d, a = d.a;

    $('#ovTitle').textContent = `★ ${c.name}`;
    $('#ovSub').textContent =
      `${c.admin || c.country} · ${fmt(c.lat, 2)}°N ${fmt(c.lon, 2)}°E · 海拔 ${fmt(c.elev, 0)}m · ` +
      `${a.years || 10} 年（${META.start || '2015'}–${META.end || '2024'}）常年值`;

    const cards = [
      ['年均气温', fmt(a.tMean), '℃', `平均日最高 ${fmt(a.tMaxAvg)}℃ / 最低 ${fmt(a.tMinAvg)}℃`],
      ['最热月', fmt(a.warmestT) + '℃', a.warmestMonth + '月', `最冷月 ${a.coldestMonth}月 ${fmt(a.coldestT)}℃`],
      ['年温差', fmt(a.range), '℃', '最热月 − 最冷月'],
      ['年降水量', fmt(a.precip, 0), 'mm', `雨日 ${fmt(a.rainDays, 0)} 天 / 年`],
      ['年均湿度', fmt(a.rh), '%', `≥80% 月份 ${d.humidMonths} 个`],
      ['年均太阳辐射', fmt((a.rad || 0) / 3.6, 1), 'kWh/m²·日', `最弱 ${d.radMinIdx + 1}月 ${fmt(d.radMin / 3.6, 1)} kWh`],
      ['体感舒适天数', fmt(a.comfort, 0), '天', '气温 15~25℃ 且湿度 ≤75%'],
      ['宜居参考分', fmt(s.total), '分', s.verdict.tag]
    ];
    metricRow = cards;
    $('#ovMetrics').innerHTML = cards.map((k) => `<div class="metric">
      <div class="m-label">${esc(k[0])}</div>
      <div class="m-value">${esc(k[1])}<small>${esc(k[2])}</small></div>
      <div class="m-sub">${esc(k[3])}</div></div>`).join('');

    const risk = [
      ['≥30℃ 天数', fmt(a.hot30, 0), '天', '炎热日'],
      ['≥35℃ 天数', fmt(a.hot35, 0), '天', '酷热日'],
      ['霜冻天数', fmt(a.frost, 0), '天', '日最低 <0℃'],
      ['暴雨日 ≥25mm', fmt(a.heavy, 0), '天', `特大暴雨 ≥50mm：${fmt(a.storm, 0)} 天`],
      ['十年最大单日降水', fmt(a.maxDaily, 0), 'mm', '极端降水强度'],
      ['极端最高 / 最低', fmt(a.absMax, 1) + ' / ' + fmt(a.absMin, 1), '℃', '十年极值'],
      ['采暖度日 HDD', d.hdd, '', '基准 18℃'],
      ['制冷度日 CDD', d.cdd, '', '基准 24℃']
    ];
    $('#ovRisk').innerHTML = risk.map((k) => `<div class="metric">
      <div class="m-label">${esc(k[0])}</div>
      <div class="m-value">${esc(k[1])}<small>${esc(k[2])}</small></div>
      <div class="m-sub">${esc(k[3])}</div></div>`).join('');

    /* 图表 1：气温 */
    const tmax = d.m.map((x) => x.tMax), tmin = d.m.map((x) => x.tMin), tmean = d.m.map((x) => x.tMean);
    mkChart('chartTemp', {
      type: 'line',
      data: {
        labels: MONTHS,
        datasets: [
          { label: '平均最高', data: tmax, borderColor: '#d94f3d', backgroundColor: 'rgba(217,79,61,.13)',
            borderWidth: 2, pointRadius: 3, tension: .35, fill: '+1' },
          { label: '平均气温', data: tmean, borderColor: '#b8860b', backgroundColor: 'transparent',
            borderWidth: 2, borderDash: [6, 4], pointRadius: 2, tension: .35 },
          { label: '平均最低', data: tmin, borderColor: '#2f6fb5', backgroundColor: 'transparent',
            borderWidth: 2, pointRadius: 3, tension: .35 }
        ]
      },
      options: baseOpts({ yTitle: '℃', beginAtZero: false })
    });

    /* 图表 2：降水 + 湿度 */
    mkChart('chartRain', {
      data: {
        labels: MONTHS,
        datasets: [
          { type: 'bar', label: '月降水 (mm)', data: d.mP, backgroundColor: 'rgba(74,144,217,.75)',
            borderRadius: 4, yAxisID: 'y', order: 2 },
          { type: 'line', label: '平均湿度 (%)', data: d.mRh, borderColor: '#0b7285',
            backgroundColor: 'transparent', borderWidth: 2, tension: .35, pointRadius: 2,
            yAxisID: 'y1', order: 1 }
        ]
      },
      options: baseOpts({ yTitle: 'mm', y1Title: '%', y1Range: [30, 100] })
    });

    /* 图表 3：太阳辐射 + 风 */
    mkChart('chartSun', {
      data: {
        labels: MONTHS,
        datasets: [
          { type: 'bar', label: '月均太阳辐射 (MJ/m²·日)', data: d.m.map((x) => x.rad),
            backgroundColor: 'rgba(232,178,61,.8)', borderRadius: 4, yAxisID: 'y', order: 2 },
          { type: 'line', label: '平均风速 (km/h)', data: d.m.map((x) => x.wind),
            borderColor: '#7a8b99', backgroundColor: 'transparent', borderWidth: 2,
            tension: .35, pointRadius: 2, yAxisID: 'y1', order: 1 }
        ]
      },
      options: baseOpts({ yTitle: 'MJ/m²·日', y1Title: 'km/h' })
    });

    /* 舒适度条带 */
    $('#ovStrip').innerHTML = d.m.map((x, i) => {
      const b = bandOf(d.at[i]);
      return `<div class="strip-cell" style="background:${b.color}"
        title="${MONTHS[i]}｜平均 ${fmt(x.tMean)}℃｜湿度 ${fmt(x.rh, 0)}%｜体感 ${fmt(d.at[i])}℃｜降水 ${fmt(x.precip, 0)}mm">
        <b>${i + 1}月</b>${b.label}<br>${fmt(d.at[i], 0)}℃</div>`;
    }).join('');
    $('#ovStripDesc').textContent =
      `采用 Steadman 表观温度（综合气温、湿度、风速）计算：本城市体感最舒适的月份为 ` +
      (d.bestMonths.map((x) => x + '月').join('、') || '—') +
      `；全年体感≥32℃(酷热) 的月份 ${d.m.filter((x, i) => d.at[i] >= 32).length} 个，` +
      `体感<0℃(严寒) 的月份 ${d.m.filter((x, i) => d.at[i] < 0).length} 个。`;
  }

  function baseOpts(o) {
    o = o || {};
    const scales = {
      x: { grid: { display: false }, ticks: { color: '#64748b', font: { size: 11 } } },
      y: {
        title: o.yTitle ? { display: true, text: o.yTitle, color: '#94a3b8', font: { size: 11 } } : undefined,
        grid: { color: '#eef2f7' }, ticks: { color: '#64748b', font: { size: 11 } },
        beginAtZero: o.beginAtZero !== false
      }
    };
    if (o.y1Title) {
      scales.y1 = {
        position: 'right',
        title: { display: true, text: o.y1Title, color: '#94a3b8', font: { size: 11 } },
        grid: { drawOnChartArea: false }, ticks: { color: '#94a3b8', font: { size: 11 } },
        min: o.y1Range ? o.y1Range[0] : undefined,
        max: o.y1Range ? o.y1Range[1] : undefined
      };
    }
    return {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { boxWidth: 12, boxHeight: 12, usePointStyle: true, color: '#475569', font: { size: 11.5 } } },
        tooltip: {
          backgroundColor: 'rgba(15,23,42,.92)', padding: 10, cornerRadius: 8,
          titleFont: { size: 12 }, bodyFont: { size: 12 }, displayColors: true, boxPadding: 4
        }
      },
      scales: scales
    };
  }

  /* ------------------------- 多城对比 ------------------------- */
  function renderCompare() {
    const cities = state.selected.map(getCity).filter(Boolean);
    const base = getCity(state.primary) || cities[0];

    /* 气温：平均气温实线 + 最高/最低虚线（仅前 2 城，避免过密） */
    const tempSets = cities.map((c, i) => ({
      label: c.name + (c.id === base.id ? ' ★' : ''),
      data: derive(c).mTemp, borderColor: SERIES[i % SERIES.length],
      backgroundColor: 'transparent', borderWidth: 2.6, tension: .35, pointRadius: 2.6
    }));
    cities.slice(0, 2).forEach((c, i) => {
      const dd = derive(c);
      tempSets.push({
        label: c.name + ' 平均最高', data: dd.m.map((x) => x.tMax),
        borderColor: SERIES[i % SERIES.length] + '77', backgroundColor: 'transparent',
        borderWidth: 1.6, borderDash: [5, 4], tension: .35, pointRadius: 0
      });
      tempSets.push({
        label: c.name + ' 平均最低', data: dd.m.map((x) => x.tMin),
        borderColor: SERIES[i % SERIES.length] + '55', backgroundColor: 'transparent',
        borderWidth: 1.6, borderDash: [2, 3], tension: .35, pointRadius: 0
      });
    });
    mkChart('chartCmpTemp', {
      type: 'line',
      data: { labels: MONTHS, datasets: tempSets },
      options: baseOpts({ yTitle: '℃', beginAtZero: false })
    });

    /* 降水 */
    mkChart('chartCmpRain', {
      data: {
        labels: MONTHS,
        datasets: cities.map((c, i) => ({
          type: 'bar', label: c.name, data: derive(c).mP,
          backgroundColor: SERIES[i % SERIES.length] + 'cc', borderRadius: 3
        }))
      },
      options: baseOpts({ yTitle: 'mm' })
    });

    /* 湿度 */
    mkChart('chartCmpRh', {
      type: 'line',
      data: { labels: MONTHS, datasets: cities.map((c, i) => ({
        label: c.name + (c.id === base.id ? ' ★' : ''),
        data: derive(c).mRh, borderColor: SERIES[i % SERIES.length],
        backgroundColor: 'transparent', borderWidth: 2.4, tension: .35, pointRadius: 2.4
      })) },
      options: baseOpts({ yTitle: '%', y1Title: null })
    });

    /* 年度指标对比表 */
    $('#cmpBaseNote').textContent = `基准：★ ${base.name}`;
    const rows = [
      ['年均气温', '℃', (d) => d.a.tMean, 2, 0],
      ['平均日最高温', '℃', (d) => d.a.tMaxAvg, 1, 0],
      ['平均日最低温', '℃', (d) => d.a.tMinAvg, 1, 0],
      ['最热月均温', '℃', (d) => d.a.warmestT, 1, 0],
      ['最冷月均温', '℃', (d) => d.a.coldestT, 1, 1],
      ['年温差', '℃', (d) => d.a.range, 1, -1],
      ['年降水量', 'mm', (d) => d.a.precip, 0, 0],
      ['年降水日数', '天', (d) => d.a.rainDays, 0, 0],
      ['暴雨日 ≥25mm', '天', (d) => d.a.heavy, 1, -1],
      ['特大暴雨 ≥50mm', '天', (d) => d.a.storm, 1, -1],
      ['年均相对湿度', '%', (d) => d.a.rh, 1, 0],
      ['高湿月份 (≥80%)', '个', (d) => d.humidMonths, 0, -1],
      ['年均太阳辐射', 'kWh/m²·日', (d) => (d.a.rad || 0) / 3.6, 1, 1],
      ['年平均风速', 'km/h', (d) => d.a.wind, 1, 0],
      ['体感舒适天数', '天', (d) => d.a.comfort, 0, 1],
      ['≥30℃ 天数', '天', (d) => d.a.hot30, 0, -1],
      ['≥35℃ 天数', '天', (d) => d.a.hot35, 1, -1],
      ['霜冻天数', '天', (d) => d.a.frost, 1, -1],
      ['十年极端最高', '℃', (d) => d.a.absMax, 1, -1],
      ['十年极端最低', '℃', (d) => d.a.absMin, 1, 1],
      ['采暖度日 HDD', '', (d) => d.hdd, 0, -1],
      ['制冷度日 CDD', '', (d) => d.cdd, 0, -1],
      ['宜居参考分', '分', null, 0, 1, 'score']
    ];

    const ds = cities.map((c) => derive(c));
    const ss = cities.map((c) => scoreCity(c, state.prefs));
    let html = '<table><thead><tr><th>指标</th>' +
      cities.map((c, i) => `<th>${esc(c.name)}${c.id === base.id ? ' ★' : ''}</th>`).join('') +
      cities.map((c) => c.id === base.id ? '' :
        `<th>差值<br><span style="font-weight:400;color:#94a3b8">${esc(c.name)} − ${esc(base.name)}</span></th>`).join('') +
      '<th>更优</th></tr></thead><tbody>';

    rows.forEach((row) => {
      const [label, unit, fn, dig, dir] = row;
      if (row[5] === 'score') {
        html += `<tr class="group-head"><td colspan="${cities.length * 2 + 2}">综合评分（随偏好权重变化）</td></tr>`;
      }
      html += `<tr><td>${esc(label)}${unit ? `<span style="color:#94a3b8"> ${unit}</span>` : ''}</td>`;
      const vals = [];
      cities.forEach((c, i) => {
        const v = row[5] === 'score' ? ss[i].total / 100 : fn(ds[i]);
        vals.push(v);
        html += `<td>${row[5] === 'score' ? fmt(ss[i].total) : fmt(v, dig)}</td>`;
      });
      cities.forEach((c, i) => {
        if (c.id === base.id) return;
        const dv = vals[i] - vals[0];
        const cls = Math.abs(dv) < 0.05 ? '' : (dv > 0 ? 'pos' : 'neg');
        html += `<td class="${cls}">${dv > 0 ? '+' : ''}${fmt(dv, dig)}</td>`;
      });
      /* 更优：差异小于显示精度的一半视为持平 */
      let best = '—';
      if (dir === 1 || dir === -1) {
        const score = vals.map((v) => dir === 1 ? v : -v);
        const mx = Math.max.apply(null, score);
        const tol = 0.5 * Math.pow(10, -(dig === null ? 1 : dig));
        const winners = cities.filter((c, i) => Math.abs(score[i] - mx) < tol).map((c) => c.name);
        best = winners.length === cities.length ? '持平'
          : winners.length > 2 ? '多城接近'
            : winners.join(' / ') + (dir === 1 ? ' ▲' : ' ▼');
      } else {
        best = '中性';
      }
      html += `<td style="color:#475569">${esc(best)}</td></tr>`;
    });
    html += '</tbody></table>';
    $('#cmpTable').innerHTML = html;

    /* 月度差值表（温度/降水/湿度） */
    let m2 = '<table><thead><tr><th>月份</th>' +
      cities.map((c) => `<th>${esc(c.name)} 气温</th>`).join('') +
      cities.map((c, i) => i === 0 ? '' : `<th>Δ气温</th>`).join('') +
      cities.map((c) => `<th>${esc(c.name)} 降水</th>`).join('') +
      cities.map((c, i) => i === 0 ? '' : `<th>Δ降水</th>`).join('') +
      '</tr></thead><tbody>';
    for (let mi = 0; mi < 12; mi++) {
      m2 += `<tr><td>${MONTHS[mi]}</td>`;
      ds.forEach((d) => { m2 += `<td>${fmt(d.mTemp[mi])}</td>`; });
      ds.forEach((d, i) => {
        if (i === 0) return;
        const dv = d.mTemp[mi] - ds[0].mTemp[mi];
        m2 += `<td class="${dv > 0 ? 'pos' : 'neg'}">${dv > 0 ? '+' : ''}${fmt(dv)}</td>`;
      });
      ds.forEach((d) => { m2 += `<td>${fmt(d.mP[mi], 0)}</td>`; });
      ds.forEach((d, i) => {
        if (i === 0) return;
        const dv = d.mP[mi] - ds[0].mP[mi];
        m2 += `<td class="${dv > 0 ? 'pos' : 'neg'}">${dv > 0 ? '+' : ''}${fmt(dv, 0)}</td>`;
      });
      m2 += '</tr>';
    }
    m2 += '</tbody></table>';
    $('#cmpMonthTable').innerHTML = m2;
    $('#cmpDiffNote').textContent =
      `Δ = 该城市 − ${base.name}（第一列城市）；单位：气温 ℃、降水 mm`;
  }

  /* ------------------------- 宜居分析 ------------------------- */
  function renderLive() {
    const cities = state.selected.map(getCity).filter(Boolean);
    const p = state.prefs;
    $('#livCards').innerHTML = cities.map((c) => {
      const r = advise(c, p);
      const s = r.score;
      const color = s.total >= 72 ? '#0f7b6c' : s.total >= 62 ? '#3f9d8f' : s.total >= 52 ? '#c9a227' : '#c2691a';
      const dims = DIMS.map((dim) => {
        const v = s.dims[dim.key];
        const col = v >= 75 ? '#0f7b6c' : v >= 60 ? '#3f9d8f' : v >= 45 ? '#c9a227' : '#c2691a';
        return `<div class="dim">
          <div class="dim-top"><span>${dim.label}</span><span>${fmt(v, 0)} 分</span></div>
          <div class="dim-bar"><i style="width:${clamp(v, 0, 100)}%;background:${col}"></i></div>
        </div>`;
      }).join('');
      return `<div class="card">
        <div class="score-head">
          <div class="score-ring" style="background:conic-gradient(${color} ${s.total * 3.6}deg, #e8edf3 0deg)">
            <div class="sr-val"><b style="color:${color}">${fmt(s.total, 0)}</b><span>宜居参考分</span></div>
          </div>
          <div class="score-verdict">
            <div class="tag">${esc(c.name)} · ${esc(s.verdict.tag)}</div>
            <div>${esc(s.verdict.text)}</div>
            <div class="footer-note">年均 ${fmt(s.d.a.tMean)}℃ ｜ 年降水 ${fmt(s.d.a.precip, 0)}mm ｜ 年均湿度 ${fmt(s.d.a.rh)}% ｜ 年均辐射 ${fmt(s.d.a.rad, 1)} MJ/m²·日</div>
          </div>
        </div>
        <div class="dims">${dims}</div>
      </div>
      <div class="card">
        <div class="card-head"><div class="card-title">${esc(c.name)} · 居住建议</div>
          <div class="card-note">共 ${r.items.length} 条，均由气候数据推导</div></div>
        <div class="advice">${r.items.map((it) => `
          <div class="advice-item lv-${it.level}">
            <div class="ai-ico">${it.icon}</div>
            <div><div class="ai-title">${esc(it.title)}</div><div class="ai-text">${esc(it.text)}</div></div>
          </div>`).join('')}</div>
      </div>`;
    }).join('');

    /* 相似城市（以主城市为基准） */
    const base = getCity(state.primary) || cities[0];
    const sim = similarCities(base.id, 6);
    $('#livSimilar').innerHTML = `<div class="card-desc">与 ★${esc(base.name)}
      气候最接近的城市（相似度按 12 个月的气温、湿度、降水向量计算）：</div>
      <div class="similar">${sim.map((x) => {
        const c = getCity(x.id);
        return `<span class="similar-item"><b>${esc(c.name)}</b>
          <span style="color:#94a3b8">${esc(c.admin || c.country)}</span>
          <span class="sim-pct">${fmt(x.sim, 0)}%</span></span>`;
      }).join('')}</div>`;
  }

  function renderPrefs() {
    const defs = [
      ['cold', '怕冷程度（影响冬季权重）'],
      ['heat', '怕热程度（影响夏季权重）'],
      ['humid', '怕潮程度（影响湿度权重）'],
      ['sun', '对日照的重视'],
      ['', '']
    ];
    const items = defs.slice(0, 4);
    $('#prefs').innerHTML = items.map((it) => `
      <div class="pref">
        <label>${it[1]}<span id="pv-${it[0]}">${state.prefs[it[0]]}</span></label>
        <input type="range" min="1" max="5" step="1" value="${state.prefs[it[0]]}" data-k="${it[0]}">
      </div>`).join('');
    $('#prefs').querySelectorAll('input').forEach((inp) => {
      inp.oninput = () => {
        state.prefs[inp.dataset.k] = +inp.value;
        $('#pv-' + inp.dataset.k).textContent = inp.value;
        renderLive();
        renderCompare();
      };
    });
  }

  /* ------------------------- 数据表 ------------------------- */
  function renderTable() {
    const cities = state.selected.map(getCity).filter(Boolean);
    /* [标签, 单位, 月度取值, 小数位, 年度字段名] */
    const cols = [
      ['平均最高温', '℃', (x) => x.tMax, 1, 'tMaxAvg'],
      ['平均气温', '℃', (x) => x.tMean, 1, 'tMean'],
      ['平均最低温', '℃', (x) => x.tMin, 1, 'tMinAvg'],
      ['相对湿度', '%', (x) => x.rh, 0, 'rh'],
      ['降水量', 'mm', (x) => x.precip, 0, 'precip'],
      ['降水日 ≥1mm', '天', (x) => x.rainDays, 1, 'rainDays'],
      ['暴雨日 ≥25mm', '天', (x) => x.heavy, 1, 'heavy'],
      ['太阳辐射', 'MJ/m²·日', (x) => x.rad, 1, 'rad'],
      ['平均风速', 'km/h', (x) => x.wind, 1, 'wind'],
      ['≥30℃ 天数', '天', (x) => x.hot30, 1, 'hot30'],
      ['≥35℃ 天数', '天', (x) => x.hot35, 1, 'hot35'],
      ['霜冻天数', '天', (x) => x.frost, 1, 'frost']
    ];
    let html = '<table><thead><tr><th>城市 / 月份</th>' +
      cols.map((c) => `<th>${c[0]}<br><span style="font-weight:400;color:#94a3b8">${c[1]}</span></th>`).join('') +
      '</tr></thead><tbody>';
    cities.forEach((c) => {
      html += `<tr class="group-head"><td colspan="${cols.length + 1}">${esc(c.name)} 
        （${esc(c.admin || c.country)} · ${fmt(c.lat, 2)}°N ${fmt(c.lon, 2)}°E · 海拔 ${fmt(c.elev, 0)}m）</td></tr>`;
      c.monthly.forEach((x, i) => {
        html += `<tr><td>${MONTHS[i]}</td>` +
          cols.map((cc) => `<td>${fmt(cc[2](x), cc[3])}</td>`).join('') + '</tr>';
      });
      const a = c.annual;
      html += '<tr style="font-weight:600;background:#f1f7f8"><td>全年</td>' +
        cols.map((cc) => `<td>${fmt(a[cc[4]], cc[3])}</td>`).join('') + '</tr>';
    });
    html += '</tbody></table>';
    $('#tbTable').innerHTML = html;
    $('#tbDesc').textContent =
      `共 ${cities.length} 个城市 × 12 个月；数据为 ${META.start || '2015'}–${META.end || '2024'} 年逐日实测/再分析数据的月平均。`;
  }

  function exportCsv() {
    const cities = state.selected.map(getCity).filter(Boolean);
    if (!cities.length) { toast('请先选择城市'); return; }
    const head = ['城市', '省份/国家', '纬度', '经度', '海拔m', '月份',
      '平均最高温C', '平均气温C', '平均最低温C', '相对湿度%', '降水量mm',
      '降水日数', '暴雨日数(>=25mm)', '太阳辐射MJ/m2/d', '平均风速km/h',
      '>=30C天数', '>=35C天数', '霜冻天数'];
    const lines = [head.join(',')];
    cities.forEach((c) => {
      c.monthly.forEach((x, i) => {
        lines.push([c.name, c.admin || c.country, c.lat, c.lon, c.elev, i + 1,
          x.tMax, x.tMean, x.tMin, x.rh, x.precip, x.rainDays, x.heavy,
          x.rad, x.wind, x.hot30, x.hot35, x.frost].join(','));
      });
      const a = c.annual;
      lines.push([c.name, c.admin || c.country, c.lat, c.lon, c.elev, '全年',
        a.tMaxAvg, a.tMean, a.tMinAvg, a.rh, a.precip, a.rainDays, a.heavy,
        a.rad, a.wind, a.hot30, a.hot35, a.frost].join(','));
    });
    const blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a2 = document.createElement('a');
    a2.href = URL.createObjectURL(blob);
    a2.download = '气候对比_' + cities.map((c) => c.name).join('_') + '.csv';
    a2.click();
    toast('CSV 已导出');
  }

  /* ------------------------- 在线抓取任意城市（NASA POWER） ------------------------- */
  const POWER_API = 'https://power.larc.nasa.gov/api/temporal/daily/point';
  const POWER_PARAMS = 'T2M,T2M_MAX,T2M_MIN,RH2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN,WS2M';
  const POWER_FILL = -999;

  async function geocode(q) {
    const url = 'https://geocoding-api.open-meteo.com/v1/search?name=' +
      encodeURIComponent(q) + '&count=8&language=zh&format=json';
    const r = await fetch(url);
    const j = await r.json();
    return j.results || [];
  }

  /* 生成 YYYY-MM-DD 日期序列 */
  function dateKeys(startISO, endISO) {
    const out = [];
    const d = new Date(startISO + 'T00:00:00Z');
    const end = new Date(endISO + 'T00:00:00Z');
    while (d <= end) {
      out.push(d.toISOString().slice(0, 10));
      d.setUTCDate(d.getUTCDate() + 1);
    }
    return out;
  }

  /* NASA POWER 参数字典 → Open-Meteo 风格 daily 结构 */
  function powerToOm(p, keys) {
    const col = (name, scale, def) => {
      const src = p[name] || {};
      return keys.map((k) => {
        const v = src[k.replace(/-/g, '')];
        if (v === undefined || v === null || v <= POWER_FILL + 1) {
          return def === undefined ? null : def;
        }
        return Math.round(v * scale * 10000) / 10000;
      });
    };
    return {
      time: keys,
      temperature_2m_max: col('T2M_MAX', 1),
      temperature_2m_min: col('T2M_MIN', 1),
      temperature_2m_mean: col('T2M', 1),
      relative_humidity_2m_mean: col('RH2M', 1),
      precipitation_sum: col('PRECTOTCORR', 1, 0),
      wind_speed_10m_max: col('WS2M', 3.6),          // m/s → km/h（2m 平均风速）
      shortwave_radiation_sum: col('ALLSKY_SFC_SW_DWN', 1)  // AG 社区原始单位 MJ/m²/日
    };
  }

  function aggDaily(daily) {
    const t = daily.time;
    const nm = ['temperature_2m_max', 'temperature_2m_min', 'temperature_2m_mean',
      'relative_humidity_2m_mean', 'precipitation_sum', 'wind_speed_10m_max',
      'shortwave_radiation_sum'];
    const S = {};
    nm.forEach((k) => { S[k] = daily[k] || []; });
    const buckets = Array.from({ length: 12 }, () => ({}));
    t.forEach((ds, i) => {
      const p = ds.split('-');
      (buckets[+p[1] - 1][p[0]] = buckets[+p[1] - 1][p[0]] || []).push(i);
    });
    const nyear = new Set(t.map((s) => s.slice(0, 4))).size;
    const g = (arr, idx) => idx.map((i) => arr[i]).filter((v) => v !== null && v !== undefined);
    const monthly = buckets.map((b) => {
      const acc = { tMax: [], tMin: [], tMean: [], rh: [], precip: [], rad: [], wind: [],
        rainDays: [], hot30: [], hot35: [], frost: [], comfort: [], heavy: [], storm: [], dryDays: [] };
      Object.keys(b).forEach((y) => {
        const idx = b[y];
        const vm = g(S.temperature_2m_max, idx), vn = g(S.temperature_2m_min, idx),
          vt = g(S.temperature_2m_mean, idx), vh = g(S.relative_humidity_2m_mean, idx),
          vp = g(S.precipitation_sum, idx),
          vw = g(S.wind_speed_10m_max, idx), vr = g(S.shortwave_radiation_sum, idx);
        if (vt.length) acc.tMean.push(avg(vt));
        if (vm.length) acc.tMax.push(avg(vm));
        if (vn.length) acc.tMin.push(avg(vn));
        if (vh.length) acc.rh.push(avg(vh));
        if (vr.length) acc.rad.push(avg(vr));
        acc.precip.push(sum(vp));
        if (vw.length) acc.wind.push(avg(vw));
        acc.rainDays.push(vp.filter((x) => x >= 1).length);
        acc.heavy.push(vp.filter((x) => x >= 25).length);
        acc.storm.push(vp.filter((x) => x >= 50).length);
        acc.dryDays.push(vp.filter((x) => x < 1).length);
        acc.hot30.push(vm.filter((x) => x >= 30).length);
        acc.hot35.push(vm.filter((x) => x >= 35).length);
        acc.frost.push(vn.filter((x) => x < 0).length);
        let n = 0;
        idx.forEach((i) => {
          const tv = S.temperature_2m_mean[i], hv = S.relative_humidity_2m_mean[i];
          if (tv !== null && hv !== null && tv >= 15 && tv <= 25 && hv <= 75) n++;
        });
        acc.comfort.push(n);
      });
      const o = {};
      Object.keys(acc).forEach((k) => { o[k] = acc[k].length ? r1(avg(acc[k])) : 0; });
      return o;
    });
    const S2 = (k) => r1(sum(monthly.map((x) => x[k])));
    const hi = monthly.reduce((b, x, i) => x.tMean > monthly[b].tMean ? i : b, 0);
    const lo = monthly.reduce((b, x, i) => x.tMean < monthly[b].tMean ? i : b, 0);
    const allIdx = t.map((_, i) => i);
    const allMax = g(S.temperature_2m_max, allIdx);
    const allMin = g(S.temperature_2m_min, allIdx);
    const allP = g(S.precipitation_sum, allIdx);
    const annual = {
      tMean: r1(avg(monthly.map((x) => x.tMean))),
      tMaxAvg: r1(avg(monthly.map((x) => x.tMax))),
      tMinAvg: r1(avg(monthly.map((x) => x.tMin))),
      rh: r1(avg(monthly.map((x) => x.rh))),
      precip: S2('precip'), rainDays: r1(S2('rainDays')),
      rad: r1(avg(monthly.map((x) => x.rad)) * 100) / 100,
      wind: r1(avg(monthly.map((x) => x.wind))),
      hot30: r1(S2('hot30')), hot35: r1(S2('hot35')),
      frost: r1(S2('frost')), comfort: Math.round(S2('comfort')),
      heavy: r1(S2('heavy')), storm: r1(S2('storm')),
      dryDays: Math.round(S2('dryDays')),
      maxDaily: r1(Math.max.apply(null, allP)),
      warmestMonth: hi + 1, warmestT: monthly[hi].tMean,
      coldestMonth: lo + 1, coldestT: monthly[lo].tMean,
      wetMonth: monthly.reduce((b, x, i) => x.precip > monthly[b].precip ? i : b, 0) + 1,
      wetMonthP: Math.max.apply(null, monthly.map((x) => x.precip)),
      range: r1(monthly[hi].tMean - monthly[lo].tMean),
      absMax: r1(Math.max.apply(null, allMax)), absMin: r1(Math.min.apply(null, allMin)),
      years: nyear
    };
    return { monthly: monthly, annual: annual };
  }

  async function loadLiveCity(res) {
    const id = 'live_' + res.latitude.toFixed(3) + '_' + res.longitude.toFixed(3);
    if (getCity(id)) return id;
    const keys = dateKeys(META.start || '2015-01-01', META.end || '2024-12-31');
    loading(true, `正在从 NASA POWER 抓取 ${res.name} 近 10 年逐日气候数据…`);
    const url = POWER_API + '?' + [
      'parameters=' + POWER_PARAMS, 'community=AG',
      'longitude=' + res.longitude, 'latitude=' + res.latitude,
      'start=' + keys[0].replace(/-/g, ''), 'end=' + keys[keys.length - 1].replace(/-/g, ''),
      'format=JSON'
    ].join('&');
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      const p = j && j.properties && j.properties.parameter;
      if (!p) throw new Error('接口返回数据不完整');
      const agg = aggDaily(powerToOm(p, keys));
      const rec = {
        id: id, name: res.name, admin: res.admin1 || '', country: res.country || '',
        countryCode: res.country_code || '', region: '自定义',
        lat: r1(res.latitude), lon: r1(res.longitude), elev: Math.round(res.elevation || 0),
        tz: null, monthly: agg.monthly, annual: agg.annual, custom: true
      };
      state.custom[id] = rec;
      state.simCache = null;
      try { localStorage.setItem(LS_KEY, JSON.stringify(state.custom)); } catch (e) { /* 容量超限时忽略 */ }
      return id;
    } finally {
      loading(false);
    }
  }

  function loadCustomFromStorage() {
    try {
      const s = localStorage.getItem(LS_KEY);
      if (s) state.custom = JSON.parse(s) || {};
    } catch (e) { state.custom = {}; }
  }

  async function doSearch(q) {
    const box = $('#searchResults');
    box.classList.add('open');
    box.innerHTML = '<div class="sr-empty">搜索中…</div>';
    try {
      const rs = await geocode(q);
      if (!rs.length) { box.innerHTML = '<div class="sr-empty">没有找到匹配的城市，试试英文名或拼音。</div>'; return; }
      box.innerHTML = '<div class="sr-head">点击加入对比清单（全球城市均支持，首次会抓取 10 年数据）</div>' +
        rs.map((r, i) => `<button class="sr-item" data-i="${i}">
          <span><span class="sr-name">${esc(r.name)}</span>
            <span class="sr-meta">${esc([r.admin1, r.country].filter(Boolean).join(' · '))}
            · ${fmt(r.latitude, 2)}°, ${fmt(r.longitude, 2)}°</span></span>
          <span class="sr-add">＋ 加入</span></button>`).join('');
      box.querySelectorAll('.sr-item').forEach((el) => {
        el.onclick = async () => {
          const r = rs[+el.dataset.i];
          box.classList.remove('open');
          $('#search').value = '';
          state.region = '我的城市';
          renderRegions();
          try {
            const id = await loadLiveCity(r);
            addCity(id); renderCityList();
            toast('已加入 ' + r.name);
          } catch (e) {
            loading(false);
            toast('抓取失败：' + e.message);
          }
        };
      });
    } catch (e) {
      box.innerHTML = '<div class="sr-empty">地理编码接口请求失败，请检查网络。</div>';
    }
  }

  /* ------------------------- 帮助 ------------------------- */
  function showHelp() {
    alert([
      '数据口径说明',
      '',
      '1. 数据源：NASA POWER Daily API（MERRA-2 再分析，community=AG），全球覆盖、免密钥。',
      '   预设 112 城已随程序打包；「搜索新城市」由浏览器直接调用同一数据源，因此两者完全同源可比。',
      '2. 统计期：' + (META.start || '2015-01-01') + ' 至 ' + (META.end || '2024-12-31') +
        '，共 ' + (META.cityCount || 112) + ' 个预设城市的月度常年值。',
      '3. 月度值 = 先算每年该月平均、再对 10 年取平均，避免 2 月天数不同造成的偏差；',
      '   年度值中的降水、雨日、高温日等为 12 个月之和（即年平均年总量），不再除以年数。',
      '4. 降水日：日降水量 ≥1mm；暴雨日 ≥25mm；特大暴雨日 ≥50mm。',
      '5. 体感温度：Steadman 表观温度 = T + 0.33e − 0.70v − 4.00（e 为水汽压 hPa，v 为风速 m/s）。',
      '6. 采暖/制冷度日：HDD = Σ(18 − 月均温)×月天数，CDD = Σ(月均温 − 24)×月天数（负值取 0）。',
      '7. 光照采用「入射太阳辐射」（MJ/m²·日；POWER 原始单位为 kWh/m²/日，已换算），',
      '   该口径比日照时数稳定可比，不依赖日照阈值定义。',
      '8. 风速为 2m 平均风速（WS2M），不是日最大风速，仅用于体感与通风参考。',
      '8. 宜居参考分：由「冬季/夏季/干湿/光照/降水/温和度」六项加权得来，权重可在「宜居分析」中按个人偏好调节。',
      '   评分为数据驱动的横向比较工具，不构成任何房地产或投资建议。',
      '9. 任意城市：搜索时先用地理编码服务把城市名转成经纬度，再向 NASA POWER 取该格点数据，',
      '   结果缓存在浏览器本地（localStorage），下次打开无需重新抓取。',
      '',
      '提示：本程序为纯本地网页，除在线搜索新城市外不联网。'
    ].join('\n'));
  }

  /* ------------------------- 事件绑定 ------------------------- */
  function bind() {
    document.querySelectorAll('#tabs button').forEach((b) => {
      b.onclick = () => {
        state.tab = b.dataset.tab;
        document.querySelectorAll('#tabs button').forEach((x) => x.classList.toggle('active', x === b));
        document.querySelectorAll('.panel').forEach((p) =>
          p.classList.toggle('active', p.id === 'panel-' + state.tab));
      };
    });
    $('#btnHelp').onclick = showHelp;
    $('#btnCsv').onclick = exportCsv;
    $('#btnClearSel').onclick = () => {
      state.selected = []; state.primary = null;
      renderChips(); renderCityList(); renderAll();
    };
    const s = $('#search');
    let timer = null;
    s.oninput = () => {
      $('#searchClear').style.display = s.value ? 'grid' : 'none';
      clearTimeout(timer);
      if (s.value.trim().length < 2) { $('#searchResults').classList.remove('open'); return; }
      timer = setTimeout(() => doSearch(s.value.trim()), 450);
    };
    s.onkeydown = (e) => { if (e.key === 'Enter') { clearTimeout(timer); doSearch(s.value.trim()); } };
    $('#searchClear').onclick = () => {
      s.value = ''; $('#searchClear').style.display = 'none';
      $('#searchResults').classList.remove('open');
    };
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.search-wrap')) $('#searchResults').classList.remove('open');
    });
  }

  /* ------------------------- 启动 ------------------------- */
  function boot() {
    loadCustomFromStorage();
    if (window.Chart) {
      Chart.defaults.font.family = '"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif';
      Chart.defaults.color = '#64748b';
    }
    const cnt = Object.keys(PRESET).length;
    $('#dataPill').textContent = `${cnt} 个预设城市 · ${META.start || '2015'}–${META.end || '2024'} 年常年值`;
    $('#footerNote').innerHTML =
      `数据来源：NASA POWER Daily API（MERRA-2 再分析）· 统计期 ` +
      `${META.start || '2015-01-01'} ~ ${META.end || '2024-12-31'}（预设 ${META.cityCount || cnt} 城）。<br>` +
      `预设城市数据已随程序打包，离线可用；「搜索新城市」由浏览器直接抓取同一数据源并缓存在本地。` +
      `所有建议均由气候数据推导，用于横向比较参考，不构成地产或投资建议。`;

    renderRegions();
    bind();
    renderPrefs();
    renderChips();
    renderCityList();

    /* 默认带出惠州 vs 芜湖 */
    ['huizhou', 'wuhu'].forEach((id) => { if (PRESET[id]) state.selected.push(id); });
    if (state.selected.length) state.primary = state.selected[0];
    renderChips(); renderCityList(); renderAll();
  }

  /* 调试 / 自动化测试出口（不影响正常使用） */
  window.__WL__ = {
    state, PRESET,
    cities: allCities, derive, scoreCity: (c, p) => scoreCity(c, p || state.prefs),
    advise: (c, p) => advise(c, p || state.prefs), similarCities,
    addCity, removeCity, toggleCity, renderAll, renderOverview, renderCompare,
    renderLive, renderTable, setPrefs(k, v) { state.prefs[k] = v; renderPrefs(); renderLive(); renderCompare(); },
    setPrimary(id) { state.primary = id; renderChips(); renderAll(); },
    metricsOf(c) {
      const d = derive(c), a = d.a;
      return { tMean: a.tMean, tMaxAvg: a.tMaxAvg, tMinAvg: a.tMinAvg,
        warmestT: a.warmestT, warmestMonth: a.warmestMonth,
        coldestT: a.coldestT, coldestMonth: a.coldestMonth, range: a.range,
        precip: a.precip, rainDays: a.rainDays, heavy: a.heavy, storm: a.storm,
        maxDaily: a.maxDaily, rh: a.rh, humidMonths: d.humidMonths,
        rad: a.rad, comfort: a.comfort,
        hot30: a.hot30, hot35: a.hot35, rainDays2: a.rainDays,
        frost: a.frost, absMax: a.absMax, absMin: a.absMin,
        hdd: d.hdd, cdd: d.cdd, conc3: r1(d.conc3 * 100),
        summerRh: r1(d.summerRh), springRh: r1(d.springRh) };
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
