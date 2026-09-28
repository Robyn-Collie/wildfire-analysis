/* heatmini.js — compact month × cause mini-heatmap for Act 2, ported from the
 * WF.heatmap logic in v1 site/js/common.js as an ES module owned by w2.
 * Scoped to the cause lens: rows are the three NWCG cause classes (Human /
 * Natural / Missing), each scaled to its own peak month so timing reads clearly.
 * Selecting a lens (0 all · 1 human · 2 natural) highlights the matching rows.
 *
 *   rows = seasonality.by_cause_month: [[causeKey, month(1-12), fires, acres], ...]
 *   opts = { metric:"fires"|"acres" }
 * Returns { setLens(n), el } so scroll.js / Act2 can drive it.
 */

const MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ember ramp shared with global.css tokens (dark surface -> amber). t in [0,1].
const EMBER_STOPS = [
  [26, 24, 21],
  [120, 53, 15],
  [234, 88, 12],
  [251, 146, 60],
  [251, 191, 36],
];
function lerp(a, b, t) { return Math.round(a + (b - a) * t); }
function rgb(c) { return "rgb(" + c[0] + "," + c[1] + "," + c[2] + ")"; }
function emberRamp(t) {
  if (t <= 0) return rgb(EMBER_STOPS[0]);
  if (t >= 1) return rgb(EMBER_STOPS[EMBER_STOPS.length - 1]);
  const seg = t * (EMBER_STOPS.length - 1);
  const i = Math.floor(seg);
  const f = seg - i;
  return rgb([
    lerp(EMBER_STOPS[i][0], EMBER_STOPS[i + 1][0], f),
    lerp(EMBER_STOPS[i][1], EMBER_STOPS[i + 1][1], f),
    lerp(EMBER_STOPS[i][2], EMBER_STOPS[i + 1][2], f),
  ]);
}
function fmt(n) {
  if (n == null || isNaN(n)) return "—";
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// which cause keys the lens shows: 0 all, 1 human, 2 natural
const LENS_KEYS = {
  0: ["Human", "Natural", "Missing data/not specified/undetermined"],
  1: ["Human"],
  2: ["Natural"],
};
const SHORT = {
  "Human": "Human",
  "Natural": "Natural",
  "Missing data/not specified/undetermined": "Undet.",
};

export function drawHeatmini(elm, rows, opts) {
  opts = opts || {};
  const metric = opts.metric || "fires";
  const mi = metric === "acres" ? 3 : 2;
  while (elm.firstChild) elm.removeChild(elm.firstChild);

  // group by cause key
  const keys = {};
  rows.forEach((r) => {
    const k = r[0];
    if (!keys[k]) keys[k] = { key: k, cells: {}, total: 0, peak: 0, peakMonth: 0 };
    keys[k].cells[r[1]] = r[mi];
    keys[k].total += r[mi];
    if (r[mi] > keys[k].peak) { keys[k].peak = r[mi]; keys[k].peakMonth = r[1]; }
  });

  // fixed order: Human, Natural, Missing (theatrical contrast)
  const order = ["Human", "Natural", "Missing data/not specified/undetermined"];

  const container = document.createElement("div");
  container.className = "wf-heatmini";
  container.setAttribute("role", "img");
  container.setAttribute("aria-label",
    "Month-by-cause mini heatmap by " + metric +
    "; each row scaled to its own peak month. Human fire peaks in spring; lightning peaks in July.");

  // header row (month initials)
  const head = document.createElement("div");
  head.className = "wf-hm-row wf-hm-head";
  const hk = document.createElement("div");
  hk.className = "wf-hm-key";
  head.appendChild(hk);
  for (let mo = 1; mo <= 12; mo++) {
    const c = document.createElement("div");
    c.className = "wf-hm-mlabel";
    c.textContent = MONTHS[mo][0];
    head.appendChild(c);
  }
  container.appendChild(head);

  const rowEls = {};
  order.forEach((key) => {
    const row = keys[key];
    if (!row) return;
    const tr = document.createElement("div");
    tr.className = "wf-hm-row";
    tr.dataset.cause = key;
    const keyc = document.createElement("div");
    keyc.className = "wf-hm-key";
    keyc.textContent = SHORT[key] || key;
    tr.appendChild(keyc);
    const rowMax = row.peak || 1;
    for (let mo = 1; mo <= 12; mo++) {
      const v = row.cells[mo] || 0;
      const t = v / rowMax;
      const c = document.createElement("div");
      c.className = "wf-hm-cell";
      c.style.background = emberRamp(t);
      c.title = (SHORT[key] || key) + " · " + MONTHS[mo] + " · " + fmt(v) + " " + metric +
        (mo === row.peakMonth ? " (peak)" : "");
      c.setAttribute("aria-label", c.title);
      if (mo === row.peakMonth) c.classList.add("wf-hm-peak");
      tr.appendChild(c);
    }
    container.appendChild(tr);
    rowEls[key] = tr;
  });

  elm.appendChild(container);

  function setLens(n) {
    const active = LENS_KEYS[n] || LENS_KEYS[0];
    order.forEach((key) => {
      const tr = rowEls[key];
      if (!tr) return;
      const on = active.indexOf(key) >= 0;
      tr.classList.toggle("wf-hm-dim", !on);
      tr.classList.toggle("wf-hm-lit", on && n !== 0);
    });
  }
  setLens(0);

  return { setLens, el: container };
}

export default drawHeatmini;
