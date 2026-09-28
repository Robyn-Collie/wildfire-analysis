/* tilemini.js — US state tile-grid map (Act 4 side rail: drought-fire correlation)
 * Ported from site/js/common.js WF.tilemap (proven v1 component), rewritten as an
 * ES module owned by w3-acts-b. Diverging cool<->ember scale, no geo libs, DC excluded.
 *
 * Public API:
 *   createTilemap(el, values, opts) -> wrap element
 *     values: { "CO": -0.724, "CA": -0.506, ... }  (keyed by USPS postal code)
 *     opts: { mode='diverging'|'sequential', domain:[lo,hi], valueFmt(v), label,
 *             unit, hint, onselect(st,v) }
 *
 * Each tile is a focusable role=button feeding an aria-live detail line. Palette
 * matches the v1 ember/diverging ramps so the side rail reads identically to the
 * receipts Drivers page.
 */
const SVGNS = 'http://www.w3.org/2000/svg';

// v1 palette (site/js/common.js): ember ramp + diverging cool<->ember.
const EMBER_STOPS = [
  [26, 24, 21], [120, 53, 15], [234, 88, 12], [251, 146, 60], [251, 191, 36],
];
const DIVERGING = { cool: [125, 211, 252], mid: [40, 35, 24], ember: [251, 146, 60] };

function lerp(a, b, t) { return Math.round(a + (b - a) * t); }
function rgb(c) { return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')'; }
function emberRamp(t) {
  if (t <= 0) return rgb(EMBER_STOPS[0]);
  if (t >= 1) return rgb(EMBER_STOPS[EMBER_STOPS.length - 1]);
  const seg = t * (EMBER_STOPS.length - 1);
  const i = Math.floor(seg), f = seg - i;
  const a = EMBER_STOPS[i], b = EMBER_STOPS[i + 1];
  return rgb([lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)]);
}
function divergingRamp(t) {
  let lo, hi, u;
  if (t < 0) { lo = DIVERGING.mid; hi = DIVERGING.cool; u = -t; }
  else { lo = DIVERGING.mid; hi = DIVERGING.ember; u = t; }
  if (u > 1) u = 1;
  return rgb([lerp(lo[0], hi[0], u), lerp(lo[1], hi[1], u), lerp(lo[2], hi[2], u)]);
}

function svgEl(tag, attrs, txt) {
  const n = document.createElementNS(SVGNS, tag);
  if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (txt != null) n.textContent = txt;
  return n;
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

// Standard 11-col x 8-row US postal tile-grid. DC intentionally EXCLUDED (50 states).
const TILE_GRID = {
  AK: [0, 0], ME: [10, 0],
  VT: [9, 1], NH: [10, 1],
  WA: [0, 2], ID: [1, 2], MT: [2, 2], ND: [3, 2], MN: [4, 2], IL: [5, 2], WI: [6, 2], MI: [7, 2], NY: [9, 2], RI: [10, 2],
  OR: [0, 3], NV: [1, 3], WY: [2, 3], SD: [3, 3], IA: [4, 3], IN: [5, 3], OH: [6, 3], PA: [7, 3], NJ: [8, 3], CT: [9, 3], MA: [10, 3],
  CA: [0, 4], UT: [1, 4], CO: [2, 4], NE: [3, 4], MO: [4, 4], KY: [5, 4], WV: [6, 4], VA: [7, 4], MD: [8, 4], DE: [9, 4],
  AZ: [1, 5], NM: [2, 5], KS: [3, 5], AR: [4, 5], TN: [5, 5], NC: [6, 5], SC: [7, 5],
  OK: [3, 6], LA: [4, 6], MS: [5, 6], AL: [6, 6], GA: [7, 6],
  HI: [0, 7], TX: [3, 7], FL: [8, 7],
};

export function createTilemap(elm, values, opts) {
  opts = opts || {};
  clear(elm);
  const mode = opts.mode || 'diverging';
  const cols = 11, rows = 8;
  const cell = 40, gap = 4, pad = 4;
  const W = cols * (cell + gap) + pad * 2;
  const H = rows * (cell + gap) + pad * 2;

  const vals = [];
  for (const k in values) if (values[k] != null && !isNaN(values[k])) vals.push(values[k]);
  let lo = opts.domain ? opts.domain[0] : (vals.length ? Math.min.apply(null, vals) : -1);
  let hi = opts.domain ? opts.domain[1] : (vals.length ? Math.max.apply(null, vals) : 1);
  if (mode === 'diverging') {
    const a = Math.max(Math.abs(lo), Math.abs(hi)) || 1;
    lo = -a; hi = a;
  }
  // opts.invert flips the diverging ramp (negative -> ember). The drought-fire
  // correlation rail needs it: "drier -> more fire" (negative rho) must read
  // ember to match the map-note and aria text. Values/labels are untouched.
  const norm = (v) => {
    if (mode !== 'diverging') return (v - lo) / (hi - lo || 1);
    const t = v / (hi || 1);
    return opts.invert ? -t : t;
  };
  const color = (v) => {
    if (v == null || isNaN(v)) return 'var(--surface2, #2a2620)';
    return mode === 'diverging' ? divergingRamp(norm(v)) : emberRamp(norm(v));
  };
  const vfmt = opts.valueFmt || ((v) => (v == null ? 'n/a' : v));

  const wrap = document.createElement('div');
  wrap.className = 'wf-tilemap-wrap';

  const s = svgEl('svg', {
    viewBox: '0 0 ' + W + ' ' + H,
    preserveAspectRatio: 'xMidYMid meet',
    role: 'img', class: 'wf-svg wf-tilemap',
    'aria-label': opts.label || 'US state tile-grid map; 50 states, DC excluded.',
  });

  const detail = document.createElement('div');
  detail.className = 'wf-tile-detail';
  detail.setAttribute('aria-live', 'polite');
  detail.textContent = opts.hint || 'Focus or hover a state for its value.';

  function setDetail(st, v) {
    detail.textContent = st + ' · ' + vfmt(v) + (opts.unit ? ' ' + opts.unit : '');
    if (opts.onselect) opts.onselect(st, v);
  }

  Object.keys(TILE_GRID).forEach((st) => {
    const pos = TILE_GRID[st];
    const x = pad + pos[0] * (cell + gap);
    const y = pad + pos[1] * (cell + gap);
    const v = Object.prototype.hasOwnProperty.call(values, st) ? values[st] : null;
    const g = svgEl('g', {
      class: 'wf-tile', tabindex: '0', role: 'button',
      'aria-label': st + ', ' + (v == null ? 'no data' : vfmt(v)),
    });
    g.appendChild(svgEl('rect', {
      x, y, width: cell, height: cell, rx: 4,
      fill: color(v), class: 'wf-tile-rect' + (v == null ? ' wf-tile-nodata' : ''),
    }));
    g.appendChild(svgEl('text', {
      x: x + cell / 2, y: y + cell / 2 + 4, 'text-anchor': 'middle', class: 'wf-tile-abbr',
    }, st));
    g.appendChild(svgEl('title', null, st + ': ' + (v == null ? 'no data' : vfmt(v))));
    g.addEventListener('mouseenter', () => setDetail(st, v));
    g.addEventListener('focus', () => setDetail(st, v));
    g.addEventListener('click', () => setDetail(st, v));
    g.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setDetail(st, v); }
    });
    s.appendChild(g);
  });

  // legend
  const legend = document.createElement('div');
  legend.className = 'wf-tile-legend';
  const bar = document.createElement('div');
  bar.className = 'wf-legend-bar';
  const grad = document.createElement('div');
  grad.className = 'wf-legend-grad';
  const stops = [];
  for (let i = 0; i <= 10; i++) {
    const t = i / 10;
    const d = opts.invert ? -(t * 2 - 1) : (t * 2 - 1);
    stops.push(mode === 'diverging' ? divergingRamp(d) : emberRamp(t));
  }
  grad.style.background = 'linear-gradient(to right,' + stops.join(',') + ')';
  const labels = document.createElement('div');
  labels.className = 'wf-legend-labels';
  const l = document.createElement('span'), r = document.createElement('span');
  l.textContent = vfmt(lo); r.textContent = vfmt(hi);
  labels.appendChild(l); labels.appendChild(r);
  bar.appendChild(grad); bar.appendChild(labels);
  legend.appendChild(bar);

  wrap.appendChild(s);
  wrap.appendChild(legend);
  wrap.appendChild(detail);
  elm.appendChild(wrap);
  return wrap;
}

export default createTilemap;
