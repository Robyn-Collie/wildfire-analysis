/* envelope.js — the signature trend chart, ported from v1 site/js/common.js (WF.envelope)
 * as a standalone ES module owned by w2. Figures & caption kept identical to v1's trend page.
 *   band   = trend_stats.rolling_band_nifc_macres.rows: [[year, p10, p50, p90], ...] (M acres)
 *   annual = national_annual.nifc: [{year, acres, fires, count_flag?}, ...]
 *   opts   = { fod:[{year,acres}], club:[2015,2017,2020], eraSplit:2000, reduced:bool }
 * Renders an inline SVG into `elm`. Same ember tokens as global.css.
 */

const SVGNS = "http://www.w3.org/2000/svg";

function elNS(tag, attrs, txt) {
  const n = document.createElementNS(SVGNS, tag);
  if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (txt != null) n.textContent = txt;
  return n;
}
function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}
function svgRoot(w, h, label) {
  const s = document.createElementNS(SVGNS, "svg");
  s.setAttribute("viewBox", "0 0 " + w + " " + h);
  s.setAttribute("preserveAspectRatio", "xMidYMid meet");
  s.setAttribute("role", "img");
  if (label) s.setAttribute("aria-label", label);
  s.setAttribute("class", "wf-svg");
  return s;
}
function fmt(n) {
  if (n == null || isNaN(n)) return "—";
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}
function macres(n) {
  if (n == null || isNaN(n)) return "—";
  return (n / 1e6).toFixed(1) + "M acres";
}
function niceTicks(min, max, count) {
  const span = max - min || 1;
  let step = Math.pow(10, Math.floor(Math.log10(span / count)));
  const err = (count * step) / span;
  if (err <= 0.15) step *= 10;
  else if (err <= 0.35) step *= 5;
  else if (err <= 0.75) step *= 2;
  const t = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step)
    t.push(Math.round(v * 100) / 100);
  return t;
}
function animateDash(line) {
  try {
    const len = line.getTotalLength ? line.getTotalLength() : 0;
    if (!len) return;
    line.style.strokeDasharray = len;
    line.style.strokeDashoffset = len;
    line.style.transition = "stroke-dashoffset 1.1s ease-out";
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        line.style.strokeDashoffset = "0";
      });
    });
  } catch (e) {
    /* getTotalLength unsupported (detached) — leave static */
  }
}

export function drawEnvelope(elm, band, annual, opts) {
  opts = opts || {};
  clear(elm);
  const W = 900,
    H = 460,
    m = { t: 28, r: 20, b: 46, l: 60 };
  const iw = W - m.l - m.r,
    ih = H - m.t - m.b;

  const club = opts.club || [2015, 2017, 2020];
  const eraSplit = opts.eraSplit || 2000;
  const fod = opts.fod || null;
  const reduced = !!opts.reduced;

  const years = annual.map((d) => d.year);
  const minY = Math.min.apply(null, years);
  const maxY = Math.max.apply(null, years);
  let maxAcres = 0;
  annual.forEach((d) => { if (d.acres > maxAcres) maxAcres = d.acres; });
  if (fod) fod.forEach((d) => { if (d.acres > maxAcres) maxAcres = d.acres; });
  const maxM = Math.ceil((maxAcres / 1e6) * 1.05);

  const sx = (y) => m.l + ((y - minY) / (maxY - minY)) * iw;
  const sy = (mAcres) => m.t + ih - (mAcres / maxM) * ih;

  const label =
    "NIFC annual wildfire acreage, " + minY + "–" + maxY +
    ", with an 11-year rolling 10th–90th percentile band and median line; " +
    "millions of acres burned per year.";
  const s = svgRoot(W, H, label);

  // era shading (pre/post split)
  s.appendChild(elNS("rect", {
    x: m.l, y: m.t, width: sx(eraSplit) - m.l, height: ih,
    fill: "var(--surface2)", opacity: "0.35", class: "wf-era wf-era-pre",
  }));
  s.appendChild(elNS("text", {
    x: m.l + 6, y: m.t + 14, class: "wf-annot-sm", fill: "var(--text-faint)",
  }, "← pre-" + eraSplit));
  s.appendChild(elNS("text", {
    x: sx(eraSplit) + 6, y: m.t + 14, class: "wf-annot-sm", fill: "var(--text-faint)",
  }, "post-" + eraSplit + " →"));

  // y gridlines + axis (M acres)
  const ticks = niceTicks(0, maxM, 5);
  ticks.forEach((t) => {
    s.appendChild(elNS("line", {
      x1: m.l, x2: W - m.r, y1: sy(t), y2: sy(t),
      class: "wf-grid", stroke: "var(--border-soft)",
    }));
    s.appendChild(elNS("text", {
      x: m.l - 8, y: sy(t) + 4, "text-anchor": "end", class: "wf-tick",
    }, t));
  });
  s.appendChild(elNS("text", {
    x: 14, y: m.t + ih / 2, class: "wf-axis-title",
    transform: "rotate(-90 14 " + (m.t + ih / 2) + ")", "text-anchor": "middle",
  }, "M acres burned"));

  // x ticks (every 5 yrs)
  for (let y = Math.ceil(minY / 5) * 5; y <= maxY; y += 5) {
    s.appendChild(elNS("text", {
      x: sx(y), y: H - m.b + 20, "text-anchor": "middle", class: "wf-tick",
    }, y));
  }

  // NIFC bars
  const barW = Math.max(3, (iw / (maxY - minY)) * 0.72);
  const barsG = elNS("g", { class: "wf-bars" });
  annual.forEach((d) => {
    const mA = d.acres / 1e6;
    const h = (mA / maxM) * ih;
    const r = elNS("rect", {
      x: sx(d.year) - barW / 2, y: sy(mA), width: barW, height: Math.max(0, h),
      class: "wf-bar" + (club.indexOf(d.year) >= 0 ? " wf-bar-club" : ""),
      fill: club.indexOf(d.year) >= 0 ? "var(--flame-red)" : "var(--ember-deep)",
    });
    r.appendChild(elNS("title", null,
      d.year + ": " + macres(d.acres) + (d.fires != null ? " · " + fmt(d.fires) + " fires" : "") +
      (d.count_flag ? " (count undercounted)" : "")));
    barsG.appendChild(r);
  });
  s.appendChild(barsG);

  // optional FOD overlay (open bars)
  if (fod) {
    const fg = elNS("g", { class: "wf-fod" });
    fod.forEach((d) => {
      const mA = d.acres / 1e6;
      fg.appendChild(elNS("rect", {
        x: sx(d.year) - barW / 2, y: sy(mA), width: barW, height: 2,
        fill: "var(--amber)", opacity: "0.9",
      }));
    });
    s.appendChild(fg);
  }

  // rolling p10-p90 ribbon
  if (band && band.length) {
    const top = [],
      bot = [];
    band.forEach((r) => { top.push(sx(r[0]) + "," + sy(r[3])); });
    for (let i = band.length - 1; i >= 0; i--) {
      bot.push(sx(band[i][0]) + "," + sy(band[i][1]));
    }
    s.appendChild(elNS("polygon", {
      points: top.concat(bot).join(" "),
      class: "wf-ribbon", fill: "var(--ember)", opacity: "0.16",
    }));
    const p50 = band.map((r) => sx(r[0]) + "," + sy(r[2])).join(" ");
    const line = elNS("polyline", {
      points: p50, class: "wf-p50", fill: "none",
      stroke: "var(--amber)", "stroke-width": "2.5",
    });
    s.appendChild(line);
    if (!reduced) animateDash(line);
  }

  // 10M-club annotations
  club.forEach((cy) => {
    const d = annual.filter((a) => a.year === cy)[0];
    if (!d) return;
    const x = sx(cy),
      yv = sy(d.acres / 1e6);
    s.appendChild(elNS("circle", { cx: x, cy: yv, r: 3.5, fill: "var(--amber)", stroke: "var(--bg)", "stroke-width": "1" }));
    s.appendChild(elNS("text", { x: x, y: yv - 8, "text-anchor": "middle", class: "wf-annot" }, cy));
  });
  s.appendChild(elNS("text", {
    x: W - m.r, y: m.t + 4, "text-anchor": "end", class: "wf-annot-sm", fill: "var(--amber)",
  }, "● 10M-acre club"));

  elm.appendChild(s);
  return s;
}

export default drawEnvelope;
