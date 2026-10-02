/* 自动化冒烟测试：用最小 DOM 桩在 Node 中真实执行 app.js，覆盖全部渲染路径。
   运行: node scripts/test_app.mjs
*/
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

/* ---------- DOM 桩 ---------- */
function makeEl(name) {
  const el = {
    _name: name, _html: '', _text: '', value: '', checked: false,
    style: {}, dataset: {}, children: [],
    classList: {
      _s: new Set(),
      add(...c) { c.forEach((x) => this._s.add(x)); },
      remove(...c) { c.forEach((x) => this._s.delete(x)); },
      toggle(c, on) { on === undefined ? (this._s.has(c) ? this._s.delete(c) : this._s.add(c)) : (on ? this._s.add(c) : this._s.delete(c)); },
      contains(c) { return this._s.has(c); }
    },
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); },
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); },
    querySelector() { return makeEl('q'); },
    querySelectorAll() { return []; },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() { },
    removeEventListener() { },
    getContext() { return { canvas: el }; },
    click() { },
    closest() { return null; },
    get parentElement() { return makeEl('parent'); },
    focus() { }, setAttribute() { }, getAttribute() { return null; }
  };
  return el;
}
const cache = new Map();
function getEl(sel) {
  if (!cache.has(sel)) cache.set(sel, makeEl(sel));
  return cache.get(sel);
}

const document = {
  readyState: 'complete',
  querySelector: getEl,
  getElementById: (id) => getEl('#' + id),
  querySelectorAll: (sel) => {
    if (sel === '#tabs button') {
      return ['overview', 'compare', 'live', 'table'].map((t) => {
        const e = makeEl('tab-' + t); e.dataset.tab = t; return e;
      });
    }
    if (sel === '.panel') {
      return ['overview', 'compare', 'live', 'table'].map((t) => {
        const e = makeEl('panel-' + t); e.id = 'panel-' + t; return e;
      });
    }
    return [];
  },
  addEventListener() { },
  createElement: () => makeEl('created')
};

const charts = [];
class Chart {
  constructor(ctx, cfg) { this.cfg = cfg; charts.push(cfg); }
  destroy() { }
}
Chart.defaults = { font: {}, color: '' };

const store = new Map();
const localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, v),
  removeItem: (k) => store.delete(k)
};

const sandbox = {
  console, document, localStorage, Chart,
  Blob: class { constructor(p) { this.parts = p; } },
  URL: { createObjectURL: () => 'blob:x' },
  alert: (m) => { console.log('[alert]', String(m).split('\n')[0] + '…'); },
  setTimeout, clearTimeout,
  fetch: () => Promise.reject(new Error('offline in test')),
  encodeURIComponent, Math, JSON, Date, isFinite, parseFloat, parseInt, Object, Array, String, Number, Set, Promise
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

/* ---------- 执行 ---------- */
const ctx = vm.createContext(sandbox);
vm.runInContext(read('data/climate-data.js'), ctx, { filename: 'climate-data.js' });
vm.runInContext(read('app.js'), ctx, { filename: 'app.js' });

const WL = sandbox.__WL__;
if (!WL) { console.error('FAIL: __WL__ 未导出，app.js 启动失败'); process.exit(1); }

console.log('预设城市数:', Object.keys(WL.PRESET).length);
console.log('默认选中:', WL.state.selected.join(','), '| primary =', WL.state.primary);
console.log('已渲染图表数:', charts.length);

/* 逐视图渲染 + 交互 */
const ids = Object.keys(WL.PRESET);
let checked = 0;
for (const id of ids.slice(0, 8)) {
  if (WL.state.selected.length >= 6) WL.state.selected.pop();
  WL.addCity(id);
}
console.log('多城选中:', WL.state.selected.join(','));

for (const id of ids) {
  const c = WL.cities()[id];
  if (!c) continue;
  const m = WL.metricsOf(c);
  const s = WL.scoreCity(c);
  const adv = WL.advise(c);
  // 完整性断言
  const bad = Object.entries(m).filter(([k, v]) => typeof v !== 'number' || !isFinite(v));
  if (bad.length) { console.error('BAD METRIC', id, bad); process.exit(1); }
  if (!(s.total >= 0 && s.total <= 100)) { console.error('BAD SCORE', id, s.total); process.exit(1); }
  if (adv.items.length < 8) { console.error('TOO FEW ADVICE', id, adv.items.length); process.exit(1); }
  if (c.monthly.length !== 12) { console.error('BAD MONTHS', id); process.exit(1); }
  checked++;
}
console.log(`所有 ${checked} 个城市指标/评分/建议校验通过`);

/* 偏好权重变化 */
for (const k of ['cold', 'heat', 'humid', 'sun']) WL.setPrefs(k, 5);
const s1 = WL.scoreCity(WL.cities()[ids[0]]);
for (const k of ['cold', 'heat', 'humid', 'sun']) WL.setPrefs(k, 1);
const s2 = WL.scoreCity(WL.cities()[ids[0]]);
console.log(`偏好权重生效: 全5=${s1.total} 全1=${s2.total}`);

/* 相似城市 */
console.log('相似城市:', WL.similarCities(ids[0], 5).map((x) => x.id + '(' + x.sim.toFixed(0) + '%)').join(' '));

/* 各视图渲染（若内部抛错会直接抛出） */
WL.setPrimary(ids[0]);
WL.renderOverview(); WL.renderCompare(); WL.renderLive(); WL.renderTable();
console.log('四个视图渲染完成, 累计图表配置数:', charts.length);

/* 导出 HTML 片段供人工检查 */
const ov = getEl('#ovMetrics').innerHTML;
const cmp = getEl('#cmpTable').innerHTML;
const liv = getEl('#livCards').innerHTML;
const tb = getEl('#tbTable').innerHTML;
fs.writeFileSync(path.join(ROOT, 'data', '_test_output.html'),
  `<!-- 自动生成：冒烟测试渲染结果 -->\n<section id="ov-metrics">${ov}</section>\n` +
  `<section id="cmp-table">${cmp}</section>\n<section id="live-cards">${liv}</section>\n` +
  `<section id="table">${tb}</section>\n`, 'utf8');
console.log('渲染输出已写入 data/_test_output.html');
console.log('OK');
