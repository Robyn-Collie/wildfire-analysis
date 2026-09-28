/* scatter.js — predicted-vs-actual validation cloud (Act 5)
 * Ported from site/js/common.js WF.scatter (proven v1 component), rewritten as an
 * ES module owned by w3-acts-b. Adds year-by-year reveal for the Act 5 narrative
 * (the v1 static component is preserved on the receipts model page).
 *
 * Public API:
 *   createScatter(el, rows, opts) -> { revealUpToYear(y), revealAll(), destroy() }
 *     rows: cv_predictions rows, each {state,year,actual_acres,predicted_acres}
 *           (also accepts {actual,predicted,label}). 1:1 reference line always drawn.
 *     opts: { log=true, xlabel, ylabel, label, reduced=false }
 *
 * Reduced-motion: caller passes reduced:true and drives revealUpToYear() from the
 * scroll.js stepper; nothing autoplays here. role=img + aria-label on the svg.
 */
const SVGNS = 'http://www.w3.org/2000/svg';

function fmt(n) {
  if (n == null || isNaN(n)) return '—';
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}
function svgEl(tag, attrs, txt) {
  const n = document.createElementNS(SVGNS, tag);
  if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (txt != null) n.textContent = txt;
  return n;
}
function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function createScatter(elm, rows, opts) {
  opts = opts || {};
  clear(elm);

  const pts = (rows || []).map((r) => {
    const a = r.actual != null ? r.actual : r.actual_acres;
    const p = r.predicted != null ? r.predicted : r.predicted_acres;
    const year = r.year != null ? r.year : null;
    const lbl = r.label || (r.state ? r.state + ' ' + (r.year || '') : '');
    return { a, p, year, label: lbl.trim() };
  });

  const log = opts.log !== false; // default log for acres
  const tv = (v) => (log ? Math.log10((v || 0) + 1) : v);

  const W = 560, H = 520, m = { t: 22, r: 22, b: 54, l: 62 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;

  const all = [];
  pts.forEach((d) => { all.push(tv(d.a)); all.push(tv(d.p)); });
  let lo = all.length ? Math.min.apply(null, all) : 0;
  let hi = all.length ? Math.max.apply(null, all) : 1;
  const pad = (hi - lo) * 0.06 || 1;
  lo -= pad; hi += pad;
  const sx = (v) => m.l + ((tv(v) - lo) / (hi - lo)) * iw;
  const sy = (v) => m.t + ih - ((tv(v) - lo) / (hi - lo)) * ih;

  const s = svgEl('svg', {
    viewBox: '0 0 ' + W + ' ' + H,
    preserveAspectRatio: 'xMidYMid meet',
    role: 'img',
    class: 'wf-svg wf-scatter-svg',
    'aria-label': opts.label || 'Predicted versus actual acres for held-out state-year predictions, with a 1:1 reference line.',
  });

  // 1:1 reference line
  s.appendChild(svgEl('line', {
    x1: m.l, y1: m.t + ih, x2: m.l + iw, y2: m.t,
    class: 'wf-oneone', stroke: 'var(--text-faint)', 'stroke-dasharray': '5 5',
  }));
  s.appendChild(svgEl('text', {
    x: m.l + iw - 4, y: m.t + 12, 'text-anchor': 'end',
    class: 'wf-annot-sm', fill: 'var(--text-faint)',
  }, '1:1'));

  // axes frame + titles
  s.appendChild(svgEl('line', { x1: m.l, y1: m.t, x2: m.l, y2: m.t + ih, class: 'wf-axis' }));
  s.appendChild(svgEl('line', { x1: m.l, y1: m.t + ih, x2: m.l + iw, y2: m.t + ih, class: 'wf-axis' }));
  s.appendChild(svgEl('text', {
    x: m.l + iw / 2, y: H - 12, 'text-anchor': 'middle', class: 'wf-axis-title',
  }, opts.xlabel || (log ? 'Actual (log₁₀ acres+1)' : 'Actual')));
  s.appendChild(svgEl('text', {
    x: 16, y: m.t + ih / 2, 'text-anchor': 'middle', class: 'wf-axis-title',
    transform: 'rotate(-90 16 ' + (m.t + ih / 2) + ')',
  }, opts.ylabel || (log ? 'Predicted (log₁₀ acres+1)' : 'Predicted')));

  const detail = document.createElement('div');
  detail.className = 'wf-scatter-detail';
  detail.setAttribute('aria-live', 'polite');
  detail.textContent = 'Focus or hover a point for its values.';

  const ptsG = svgEl('g', { class: 'wf-scatter-pts' });
  s.appendChild(ptsG);

  const nodes = pts.map((d) => {
    const g = svgEl('g', {
      class: 'wf-pt', tabindex: '0', role: 'button',
      'aria-label': (d.label || 'point') + ', actual ' + fmt(d.a) + ' acres, predicted ' + fmt(d.p) + ' acres',
    });
    g.appendChild(svgEl('circle', {
      cx: sx(d.a), cy: sy(d.p), r: 5, class: 'wf-pt-dot',
      fill: 'var(--ember)', stroke: 'var(--bg)', 'stroke-width': '1',
    }));
    g.appendChild(svgEl('title', null,
      (d.label ? d.label + ' — ' : '') + 'actual ' + fmt(d.a) + ', predicted ' + fmt(d.p)));
    const show = () => {
      detail.textContent =
        (d.label ? d.label + ' — ' : '') +
        'actual ' + fmt(d.a) + ' acres · predicted ' + fmt(d.p) + ' acres';
    };
    g.addEventListener('mouseenter', show);
    g.addEventListener('focus', show);
    // hidden until its year is revealed
    g.style.display = 'none';
    ptsG.appendChild(g);
    return { g, year: d.year };
  });

  elm.appendChild(s);
  elm.appendChild(detail);

  let revealedYear = null;
  function revealUpToYear(y) {
    revealedYear = y;
    let shown = 0;
    nodes.forEach((n) => {
      const on = n.year == null || y == null || n.year <= y;
      n.g.style.display = on ? '' : 'none';
      if (on) shown++;
    });
    s.setAttribute('aria-label',
      (opts.label || 'Held-out predictions vs actual acres') +
      (y != null ? ' — years through ' + y + ' revealed' : '') +
      ' (' + shown + ' of ' + nodes.length + ' points shown).');
  }
  function revealAll() { revealUpToYear(null); }

  // default: everything visible (static / no-JS-equivalent state)
  revealAll();

  return { revealUpToYear, revealAll, node: s, destroy() { clear(elm); } };
}

export default createScatter;
