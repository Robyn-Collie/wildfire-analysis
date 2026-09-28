/* us-wildfires — shared runtime (WF namespace)
 * Owner: w1-foundation. No globals beyond window.WF.
 * Data shapes are pinned to the pipeline outputs in site-data/*.json.
 * Every component: init(el, data, opts) -> renders into el; keyboard-focusable;
 * role="img" + aria-label on every canvas/svg; prefers-reduced-motion kills animation.
 */
(function () {
  "use strict";

  var SVGNS = "http://www.w3.org/2000/svg";
  var REDUCED = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;

  /* ---------- ember ramp (shared by heatmap / tilemap-sequential / eramap) ---------- */
  // dark surface -> amber -> ember -> deep ember -> flame red. t in [0,1].
  var EMBER_STOPS = [
    [26, 24, 21], // --surface-ish
    [120, 53, 15], // brown-800
    [234, 88, 12], // --ember-deep
    [251, 146, 60], // --ember
    [251, 191, 36], // --amber
  ];
  // diverging: cool (wet) <-> neutral <-> ember (dry). t in [-1,1].
  var DIVERGING = {
    cool: [125, 211, 252], // --cool
    mid: [40, 35, 24], // near --surface2
    ember: [251, 146, 60], // --ember
  };

  function lerp(a, b, t) {
    return Math.round(a + (b - a) * t);
  }
  function rgb(c) {
    return "rgb(" + c[0] + "," + c[1] + "," + c[2] + ")";
  }
  function emberRamp(t) {
    if (t <= 0) return rgb(EMBER_STOPS[0]);
    if (t >= 1) return rgb(EMBER_STOPS[EMBER_STOPS.length - 1]);
    var seg = t * (EMBER_STOPS.length - 1);
    var i = Math.floor(seg);
    var f = seg - i;
    var a = EMBER_STOPS[i];
    var b = EMBER_STOPS[i + 1];
    return rgb([lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)]);
  }
  function divergingRamp(t) {
    // t in [-1,1]; negative -> cool, positive -> ember
    var lo, hi, u;
    if (t < 0) {
      lo = DIVERGING.mid;
      hi = DIVERGING.cool;
      u = -t;
    } else {
      lo = DIVERGING.mid;
      hi = DIVERGING.ember;
      u = t;
    }
    if (u > 1) u = 1;
    return rgb([lerp(lo[0], hi[0], u), lerp(lo[1], hi[1], u), lerp(lo[2], hi[2], u)]);
  }

  /* ---------- small DOM helpers ---------- */
  function svg(w, h, label) {
    var s = document.createElementNS(SVGNS, "svg");
    s.setAttribute("viewBox", "0 0 " + w + " " + h);
    s.setAttribute("preserveAspectRatio", "xMidYMid meet");
    s.setAttribute("role", "img");
    if (label) s.setAttribute("aria-label", label);
    s.setAttribute("class", "wf-svg");
    return s;
  }
  function el(tag, attrs, txt) {
    var n = document.createElementNS(SVGNS, tag);
    if (attrs) for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (txt != null) n.textContent = txt;
    return n;
  }
  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }
  var MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /* ==================================================================
   * WF.load — fetch+cache from relative site-data/; on failure reveal
   * any .data-fallback notes inside/around the target so static content stays.
   * ================================================================== */
  var _cache = {};
  function load(names, cb) {
    if (typeof names === "string") names = [names];
    var out = {};
    var pending = names.length;
    var failed = false;
    if (pending === 0) {
      cb(out);
      return;
    }
    names.forEach(function (name) {
      if (_cache[name]) {
        out[name] = _cache[name];
        if (--pending === 0) cb(out, failed);
        return;
      }
      fetch("site-data/" + name + ".json")
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (j) {
          _cache[name] = j;
          out[name] = j;
        })
        .catch(function (e) {
          failed = true;
          out[name] = null;
          revealFallback(e);
        })
        .then(function () {
          if (--pending === 0) cb(out, failed);
        });
    });
  }
  function revealFallback() {
    var notes = document.querySelectorAll(".data-fallback");
    for (var i = 0; i < notes.length; i++) notes[i].hidden = false;
  }

  /* ---------- formatters ---------- */
  function fmt(n) {
    if (n == null || isNaN(n)) return "—";
    return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  function macres(n) {
    // n = acres; render millions-of-acres, 1 dp
    if (n == null || isNaN(n)) return "—";
    return (n / 1e6).toFixed(1) + "M acres";
  }

  /* ==================================================================
   * WF.envelope(el, band, annual, opts) — the signature chart.
   *   band   = rolling_band_nifc_macres.rows: [[year, p10, p50, p90], ...] (M acres)
   *   annual = array of {year, acres, fires, count_flag?} (NIFC), pass FOD via opts.fod
   *   opts   = { fod:[{year,acres}], club:[2015,2017,2020], eraSplit:2000 }
   * NIFC annual acres as bars; ribbon p10-p90; p50 line; 10M-club annotations;
   * era shading pre/post eraSplit.
   * ================================================================== */
  function envelope(elm, band, annual, opts) {
    opts = opts || {};
    clear(elm);
    var W = 900,
      H = 460,
      m = { t: 28, r: 20, b: 46, l: 60 };
    var iw = W - m.l - m.r,
      ih = H - m.t - m.b;

    var club = opts.club || [2015, 2017, 2020];
    var eraSplit = opts.eraSplit || 2000;
    var fod = opts.fod || null;

    // domain
    var years = annual.map(function (d) { return d.year; });
    var minY = Math.min.apply(null, years);
    var maxY = Math.max.apply(null, years);
    var maxAcres = 0;
    annual.forEach(function (d) { if (d.acres > maxAcres) maxAcres = d.acres; });
    if (fod) fod.forEach(function (d) { if (d.acres > maxAcres) maxAcres = d.acres; });
    var maxM = Math.ceil((maxAcres / 1e6) * 1.05); // headroom, M acres

    function sx(y) { return m.l + ((y - minY) / (maxY - minY)) * iw; }
    function sy(mAcres) { return m.t + ih - (mAcres / maxM) * ih; }

    var label =
      "NIFC annual wildfire acreage, " + minY + "–" + maxY +
      ", with an 11-year rolling 10th–90th percentile band and median line; " +
      "millions of acres burned per year.";
    var s = svg(W, H, label);

    // era shading (pre/post split)
    s.appendChild(el("rect", {
      x: m.l, y: m.t, width: sx(eraSplit) - m.l, height: ih,
      fill: "var(--surface2)", opacity: "0.35", class: "wf-era wf-era-pre",
    }));
    var eraLbl = el("text", {
      x: m.l + 6, y: m.t + 14, class: "wf-annot-sm", fill: "var(--text-faint)",
    }, "← pre-" + eraSplit);
    s.appendChild(eraLbl);
    s.appendChild(el("text", {
      x: sx(eraSplit) + 6, y: m.t + 14, class: "wf-annot-sm", fill: "var(--text-faint)",
    }, "post-" + eraSplit + " →"));

    // y gridlines + axis (M acres)
    var ticks = niceTicks(0, maxM, 5);
    ticks.forEach(function (t) {
      s.appendChild(el("line", {
        x1: m.l, x2: W - m.r, y1: sy(t), y2: sy(t),
        class: "wf-grid", stroke: "var(--border-soft)",
      }));
      s.appendChild(el("text", {
        x: m.l - 8, y: sy(t) + 4, "text-anchor": "end", class: "wf-tick",
      }, t));
    });
    s.appendChild(el("text", {
      x: 14, y: m.t + ih / 2, class: "wf-axis-title",
      transform: "rotate(-90 14 " + (m.t + ih / 2) + ")", "text-anchor": "middle",
    }, "M acres burned"));

    // x ticks (every 5 yrs)
    for (var y = Math.ceil(minY / 5) * 5; y <= maxY; y += 5) {
      s.appendChild(el("text", {
        x: sx(y), y: H - m.b + 20, "text-anchor": "middle", class: "wf-tick",
      }, y));
    }

    // NIFC bars
    var barW = Math.max(3, (iw / (maxY - minY)) * 0.72);
    var barsG = el("g", { class: "wf-bars" });
    annual.forEach(function (d) {
      var mA = d.acres / 1e6;
      var h = (mA / maxM) * ih;
      var r = el("rect", {
        x: sx(d.year) - barW / 2, y: sy(mA), width: barW, height: Math.max(0, h),
        class: "wf-bar" + (club.indexOf(d.year) >= 0 ? " wf-bar-club" : ""),
        fill: club.indexOf(d.year) >= 0 ? "var(--flame-red)" : "var(--ember-deep)",
      });
      var tt = el("title", null,
        d.year + ": " + macres(d.acres) + (d.fires != null ? " · " + fmt(d.fires) + " fires" : "") +
        (d.count_flag ? " (count undercounted)" : ""));
      r.appendChild(tt);
      barsG.appendChild(r);
    });
    s.appendChild(barsG);

    // optional FOD overlay (open bars)
    if (fod) {
      var fg = el("g", { class: "wf-fod" });
      fod.forEach(function (d) {
        var mA = d.acres / 1e6;
        fg.appendChild(el("rect", {
          x: sx(d.year) - barW / 2, y: sy(mA), width: barW, height: 2,
          fill: "var(--amber)", opacity: "0.9",
        }));
      });
      s.appendChild(fg);
    }

    // rolling p10-p90 ribbon
    if (band && band.length) {
      var top = [],
        bot = [];
      band.forEach(function (r) {
        top.push(sx(r[0]) + "," + sy(r[3])); // p90
      });
      for (var i = band.length - 1; i >= 0; i--) {
        bot.push(sx(band[i][0]) + "," + sy(band[i][1])); // p10
      }
      s.appendChild(el("polygon", {
        points: top.concat(bot).join(" "),
        class: "wf-ribbon", fill: "var(--ember)", opacity: "0.16",
      }));
      // p50 line
      var p50 = band.map(function (r) { return sx(r[0]) + "," + sy(r[2]); }).join(" ");
      var line = el("polyline", {
        points: p50, class: "wf-p50", fill: "none",
        stroke: "var(--amber)", "stroke-width": "2.5",
      });
      s.appendChild(line);
      if (!REDUCED) animateDash(line);
    }

    // 10M-club annotations
    club.forEach(function (cy) {
      var d = annual.filter(function (a) { return a.year === cy; })[0];
      if (!d) return;
      var x = sx(cy),
        yv = sy(d.acres / 1e6);
      s.appendChild(el("circle", { cx: x, cy: yv, r: 3.5, fill: "var(--amber)", stroke: "var(--bg)", "stroke-width": "1" }));
      s.appendChild(el("text", { x: x, y: yv - 8, "text-anchor": "middle", class: "wf-annot" }, cy));
    });
    // one club caption
    s.appendChild(el("text", {
      x: W - m.r, y: m.t + 4, "text-anchor": "end", class: "wf-annot-sm", fill: "var(--amber)",
    }, "● 10M-acre club"));

    elm.appendChild(s);
    return s;
  }

  function animateDash(line) {
    try {
      var len = line.getTotalLength ? line.getTotalLength() : 0;
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
      /* getTotalLength unsupported (e.g. detached) — leave static */
    }
  }

  function niceTicks(min, max, count) {
    var span = max - min || 1;
    var step = Math.pow(10, Math.floor(Math.log10(span / count)));
    var err = (count * step) / span;
    if (err <= 0.15) step *= 10;
    else if (err <= 0.35) step *= 5;
    else if (err <= 0.75) step *= 2;
    var t = [];
    for (var v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) t.push(Math.round(v * 100) / 100);
    return t;
  }

  /* ==================================================================
   * WF.heatmap(el, rows, opts) — month x key.
   *   rows = [[key, month(1-12), fires, acres], ...]   (seasonality shape)
   *   opts = { metric:"fires"|"acres", sort:"peak"|"total"|"key",
   *            valueLabel, title }
   * ember ramp; keyboard-focusable cells with title tooltips.
   * ================================================================== */
  function heatmap(elm, rows, opts) {
    opts = opts || {};
    clear(elm);
    var metric = opts.metric || "fires";
    var mi = metric === "acres" ? 3 : 2;
    var sort = opts.sort || "total";

    // group by key
    var keys = {};
    rows.forEach(function (r) {
      var k = r[0];
      if (!keys[k]) keys[k] = { key: k, cells: {}, total: 0, peak: 0, peakMonth: 0 };
      keys[k].cells[r[1]] = r[mi];
      keys[k].total += r[mi];
      if (r[mi] > keys[k].peak) {
        keys[k].peak = r[mi];
        keys[k].peakMonth = r[1];
      }
    });
    var list = Object.keys(keys).map(function (k) { return keys[k]; });
    if (sort === "total") list.sort(function (a, b) { return b.total - a.total; });
    else if (sort === "peak") list.sort(function (a, b) { return a.peakMonth - b.peakMonth || b.total - a.total; });
    else list.sort(function (a, b) { return a.key < b.key ? -1 : 1; });

    // per-key normalization (each row scaled to its own max => shows timing)
    var container = document.createElement("div");
    container.className = "wf-heatmap";
    container.setAttribute("role", "img");
    container.setAttribute(
      "aria-label",
      (opts.title || "Monthly heatmap") + " by " + metric + "; each row scaled to its own peak month. " +
      list.length + " rows."
    );

    // header row
    var head = document.createElement("div");
    head.className = "wf-hm-row wf-hm-head";
    head.appendChild(cellDiv("wf-hm-key", ""));
    for (var mo = 1; mo <= 12; mo++) head.appendChild(cellDiv("wf-hm-mlabel", MONTHS[mo][0]));
    container.appendChild(head);

    list.forEach(function (row) {
      var tr = document.createElement("div");
      tr.className = "wf-hm-row";
      tr.appendChild(cellDiv("wf-hm-key", row.key));
      var rowMax = row.peak || 1;
      for (var mo = 1; mo <= 12; mo++) {
        var v = row.cells[mo] || 0;
        var t = v / rowMax;
        var c = document.createElement("button");
        c.type = "button";
        c.className = "wf-hm-cell";
        c.style.background = emberRamp(t);
        c.setAttribute(
          "title",
          row.key + " · " + MONTHS[mo] + " · " + fmt(v) + " " + metric +
          (mo === row.peakMonth ? " (peak)" : "")
        );
        c.setAttribute("aria-label", c.getAttribute("title"));
        if (mo === row.peakMonth) c.classList.add("wf-hm-peak");
        tr.appendChild(c);
      }
      container.appendChild(tr);
    });
    elm.appendChild(container);
    return container;

    function cellDiv(cls, txt) {
      var d = document.createElement("div");
      d.className = cls;
      d.textContent = txt;
      return d;
    }
  }

  /* ==================================================================
   * WF.tilemap(el, values, opts) — US state tile-grid.
   *   values = { "CO": -0.724, "CA": 0.48, ... }  (keyed by postal code)
   *   opts = { mode:"diverging"|"sequential", domain:[lo,hi],
   *            valueFmt:function(v), label, unit, onselect:function(st,v) }
   * fixed 11x8 grid embedded as const. Each tile is a focusable button
   * feeding a detail line beneath the grid. NO geo libs. DC excluded.
   * ================================================================== */
  // Standard 11-col x 8-row US state postal tile-grid arrangement.
  // [col(0-10), row(0-7)]. DC is intentionally EXCLUDED (spec: 50 states only).
  var TILE_GRID = {
    AK: [0, 0], ME: [10, 0],
    VT: [9, 1], NH: [10, 1],
    WA: [0, 2], ID: [1, 2], MT: [2, 2], ND: [3, 2], MN: [4, 2], IL: [5, 2], WI: [6, 2], MI: [7, 2], NY: [9, 2], RI: [10, 2],
    OR: [0, 3], NV: [1, 3], WY: [2, 3], SD: [3, 3], IA: [4, 3], IN: [5, 3], OH: [6, 3], PA: [7, 3], NJ: [8, 3], CT: [9, 3], MA: [10, 3],
    CA: [0, 4], UT: [1, 4], CO: [2, 4], NE: [3, 4], MO: [4, 4], KY: [5, 4], WV: [6, 4], VA: [7, 4], MD: [8, 4], DE: [9, 4],
    AZ: [1, 5], NM: [2, 5], KS: [3, 5], AR: [4, 5], TN: [5, 5], NC: [6, 5], SC: [7, 5],
    OK: [3, 6], LA: [4, 6], MS: [5, 6], AL: [6, 6], GA: [7, 6],
    HI: [0, 7], TX: [3, 7], FL: [8, 7],
  };

  function tilemap(elm, values, opts) {
    opts = opts || {};
    clear(elm);
    var mode = opts.mode || "sequential";
    var cols = 11,
      rows = 8;
    var cell = 46,
      gap = 5,
      pad = 4;
    var W = cols * (cell + gap) + pad * 2;
    var H = rows * (cell + gap) + pad * 2;

    // domain
    var vals = [];
    for (var k in values) if (values[k] != null && !isNaN(values[k])) vals.push(values[k]);
    var lo = opts.domain ? opts.domain[0] : Math.min.apply(null, vals);
    var hi = opts.domain ? opts.domain[1] : Math.max.apply(null, vals);
    if (mode === "diverging") {
      var a = Math.max(Math.abs(lo), Math.abs(hi)) || 1;
      lo = -a;
      hi = a;
    }
    function norm(v) {
      // opts.invert flips the diverging ramp (negative -> ember): the
      // drought-fire rail needs "drier -> more fire" (negative rho) to read
      // ember, matching its map-note and aria text. Values are untouched.
      if (mode === "diverging") {
        var t = v / (hi || 1); // -> [-1,1]
        return opts.invert ? -t : t;
      }
      return (v - lo) / (hi - lo || 1); // -> [0,1]
    }
    function color(v) {
      if (v == null || isNaN(v)) return "var(--surface2)";
      return mode === "diverging" ? divergingRamp(norm(v)) : emberRamp(norm(v));
    }
    var vfmt = opts.valueFmt || function (v) { return v == null ? "n/a" : v; };

    var wrap = document.createElement("div");
    wrap.className = "wf-tilemap-wrap";

    var s = svg(W, H, opts.label || "US state tile-grid map; 50 states, DC excluded.");
    s.classList.add("wf-tilemap");

    var detail = document.createElement("div");
    detail.className = "wf-tile-detail";
    detail.setAttribute("aria-live", "polite");
    detail.textContent = opts.hint || "Focus or hover a state for its value.";

    function setDetail(st, v) {
      detail.textContent =
        st + " · " + vfmt(v) + (opts.unit ? " " + opts.unit : "");
      if (opts.onselect) opts.onselect(st, v);
    }

    Object.keys(TILE_GRID).forEach(function (st) {
      var pos = TILE_GRID[st];
      var x = pad + pos[0] * (cell + gap);
      var y = pad + pos[1] * (cell + gap);
      var v = values.hasOwnProperty(st) ? values[st] : null;
      var g = el("g", { class: "wf-tile", tabindex: "0", role: "button",
        "aria-label": st + ", " + (v == null ? "no data" : vfmt(v)) });
      var rect = el("rect", {
        x: x, y: y, width: cell, height: cell, rx: 4,
        fill: color(v), class: "wf-tile-rect" + (v == null ? " wf-tile-nodata" : ""),
      });
      g.appendChild(rect);
      g.appendChild(el("text", {
        x: x + cell / 2, y: y + cell / 2 + 4, "text-anchor": "middle",
        class: "wf-tile-abbr",
      }, st));
      g.appendChild(el("title", null, st + ": " + (v == null ? "no data" : vfmt(v))));
      g.addEventListener("mouseenter", function () { setDetail(st, v); });
      g.addEventListener("focus", function () { setDetail(st, v); });
      g.addEventListener("click", function () { setDetail(st, v); });
      g.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setDetail(st, v); }
      });
      s.appendChild(g);
    });

    // legend
    var legend = document.createElement("div");
    legend.className = "wf-tile-legend";
    var lg = buildLegend(mode, lo, hi, vfmt, opts.invert);
    legend.appendChild(lg);

    wrap.appendChild(s);
    wrap.appendChild(legend);
    wrap.appendChild(detail);
    elm.appendChild(wrap);
    return wrap;
  }

  function buildLegend(mode, lo, hi, vfmt, invert) {
    var bar = document.createElement("div");
    bar.className = "wf-legend-bar";
    var grad = document.createElement("div");
    grad.className = "wf-legend-grad";
    var stops = [];
    for (var i = 0; i <= 10; i++) {
      var t = i / 10;
      if (mode === "diverging") stops.push(divergingRamp(invert ? -(t * 2 - 1) : t * 2 - 1));
      else stops.push(emberRamp(t));
    }
    grad.style.background = "linear-gradient(to right," + stops.join(",") + ")";
    var labels = document.createElement("div");
    labels.className = "wf-legend-labels";
    var l = document.createElement("span"),
      r = document.createElement("span");
    l.textContent = vfmt(lo);
    r.textContent = vfmt(hi);
    labels.appendChild(l);
    labels.appendChild(r);
    bar.appendChild(grad);
    bar.appendChild(labels);
    return bar;
  }

  /* ==================================================================
   * WF.eramap(el, grid, opts) — canvas 0.5-degree dot grid.
   *   grid = { rows:[[era,lat,lon,fires,acres],...], columns:[...] }
   *          or a raw rows array.
   *   opts = { metric:"fires"|"acres" }
   * 6-era stepper + fires/acres toggle + log scale. AK/HI inset.
   * equirectangular; "not a projection" footnote hook.
   * ================================================================== */
  function eramap(elm, grid, opts) {
    opts = opts || {};
    clear(elm);
    var rows = grid && grid.rows ? grid.rows : grid;
    var eras = [];
    rows.forEach(function (r) { if (eras.indexOf(r[0]) < 0) eras.push(r[0]); });
    eras.sort();

    var state = { eraIdx: eras.length - 1, metric: opts.metric || "fires" };
    var mi = function () { return state.metric === "acres" ? 4 : 3; };

    // global max (over ALL eras) for stable color scale, log space
    var gmax = 0;
    rows.forEach(function (r) {
      var v = state.metric === "acres" ? r[4] : r[3];
      if (v > gmax) gmax = v;
    });

    // --- controls ---
    var controls = document.createElement("div");
    controls.className = "wf-eramap-controls";

    var toggle = document.createElement("div");
    toggle.className = "wf-toggle";
    toggle.setAttribute("role", "radiogroup");
    toggle.setAttribute("aria-label", "Metric");
    ["fires", "acres"].forEach(function (mname) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "wf-toggle-btn" + (mname === state.metric ? " active" : "");
      b.textContent = mname === "fires" ? "Fires" : "Acres";
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", mname === state.metric ? "true" : "false");
      b.addEventListener("click", function () {
        state.metric = mname;
        recomputeMax();
        [].forEach.call(toggle.children, function (c) {
          var on = c === b;
          c.classList.toggle("active", on);
          c.setAttribute("aria-checked", on ? "true" : "false");
        });
        draw();
      });
      toggle.appendChild(b);
    });

    var stepper = document.createElement("div");
    stepper.className = "wf-stepper";
    var prev = stepBtn("‹", -1);
    var eraLabel = document.createElement("span");
    eraLabel.className = "wf-era-label wf-mono";
    var next = stepBtn("›", 1);
    stepper.appendChild(prev);
    stepper.appendChild(eraLabel);
    stepper.appendChild(next);

    var slider = document.createElement("input");
    slider.type = "range";
    slider.min = "0";
    slider.max = String(eras.length - 1);
    slider.value = String(state.eraIdx);
    slider.className = "wf-era-slider";
    slider.setAttribute("aria-label", "Era selector");
    slider.addEventListener("input", function () {
      state.eraIdx = parseInt(slider.value, 10);
      draw();
    });

    controls.appendChild(toggle);
    controls.appendChild(stepper);
    controls.appendChild(slider);

    function stepBtn(txt, dir) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "wf-step-btn";
      b.textContent = txt;
      b.setAttribute("aria-label", dir < 0 ? "Previous era" : "Next era");
      b.addEventListener("click", function () {
        state.eraIdx = Math.max(0, Math.min(eras.length - 1, state.eraIdx + dir));
        slider.value = String(state.eraIdx);
        draw();
      });
      return b;
    }
    function recomputeMax() {
      gmax = 0;
      rows.forEach(function (r) {
        var v = state.metric === "acres" ? r[4] : r[3];
        if (v > gmax) gmax = v;
      });
    }

    // --- canvas ---
    var CW = 900,
      CH = 470;
    var canvas = document.createElement("canvas");
    canvas.width = CW;
    canvas.height = CH;
    canvas.className = "wf-eramap-canvas";
    canvas.setAttribute("role", "img");
    var ctx = canvas.getContext("2d");

    // CONUS equirectangular window; AK & HI drawn as insets.
    var CONUS = { latMin: 24, latMax: 50, lonMin: -125, lonMax: -66 };
    function inConus(lat, lon) {
      return lat >= CONUS.latMin && lat <= CONUS.latMax && lon >= CONUS.lonMin && lon <= CONUS.lonMax;
    }

    function draw() {
      var era = eras[state.eraIdx];
      eraLabel.textContent = era;
      ctx.clearRect(0, 0, CW, CH);
      // main frame
      var mL = 20, mR = 20, mT = 16, mB = 30;
      var pw = CW - mL - mR,
        ph = CH - mT - mB;
      var logMax = Math.log10(gmax + 1) || 1;
      var dot = 3.2;

      function project(lat, lon) {
        var x = mL + ((lon - CONUS.lonMin) / (CONUS.lonMax - CONUS.lonMin)) * pw;
        var y = mT + (1 - (lat - CONUS.latMin) / (CONUS.latMax - CONUS.latMin)) * ph;
        return [x, y];
      }
      // inset boxes
      var akBox = { x: mL, y: mT + ph - 118, w: 150, h: 110 };
      var hiBox = { x: mL + 158, y: mT + ph - 62, w: 74, h: 54 };

      var drawn = 0;
      rows.forEach(function (r) {
        if (r[0] !== era) return;
        var lat = r[1],
          lon = r[2],
          v = state.metric === "acres" ? r[4] : r[3];
        if (!v) return;
        var t = Math.log10(v + 1) / logMax;
        var px, py;
        if (inConus(lat, lon)) {
          var p = project(lat, lon);
          px = p[0];
          py = p[1];
        } else if (lat >= 51) {
          // Alaska inset
          px = akBox.x + ((lon + 179) / (130 - 0)) * akBox.w * 0 + ((lon + 170) / 60) * akBox.w;
          py = akBox.y + (1 - (lat - 51) / (72 - 51)) * akBox.h;
          if (px < akBox.x || px > akBox.x + akBox.w) return;
        } else if (lon < -150) {
          // Hawaii inset
          px = hiBox.x + ((lon + 161) / 8) * hiBox.w;
          py = hiBox.y + (1 - (lat - 18) / (23 - 18)) * hiBox.h;
        } else {
          return; // PR etc: skip on this CONUS-focused map
        }
        ctx.fillStyle = emberRamp(t);
        ctx.globalAlpha = 0.85;
        ctx.beginPath();
        ctx.arc(px, py, dot, 0, Math.PI * 2);
        ctx.fill();
        drawn++;
      });
      ctx.globalAlpha = 1;

      // inset outlines + labels
      ctx.strokeStyle = "rgba(120,110,95,0.45)";
      ctx.lineWidth = 1;
      ctx.strokeRect(akBox.x, akBox.y, akBox.w, akBox.h);
      ctx.strokeRect(hiBox.x, hiBox.y, hiBox.w, hiBox.h);
      ctx.fillStyle = "#6b6357";
      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.fillText("AK (inset)", akBox.x + 4, akBox.y + 12);
      ctx.fillText("HI", hiBox.x + 4, hiBox.y + 12);

      canvas.setAttribute(
        "aria-label",
        "Discovery-point density grid, 0.5° bins, era " + era + ", metric " + state.metric +
        ", log color scale; " + drawn + " active cells. Alaska and Hawaii shown as insets. " +
        "Not a projection of burned area."
      );
    }

    var footnote = document.createElement("p");
    footnote.className = "wf-eramap-note";
    footnote.innerHTML =
      "Equirectangular dot grid of <strong>discovery points</strong> binned to 0.5°, " +
      "not burned footprints. Color is log-scaled. <em>This is not a projection.</em>";

    elm.appendChild(controls);
    elm.appendChild(canvas);
    elm.appendChild(footnote);
    draw();
    return { redraw: draw, state: state };
  }

  /* ==================================================================
   * WF.scatter(el, rows, opts) — pred vs actual.
   *   rows = [{actual, predicted, label?}, ...]  OR
   *          worst_misses shape [{state,year,actual_acres,predicted_acres}]
   *   opts = { log:true, xlabel, ylabel, label }
   * 1:1 line; hover/focus detail.
   * ================================================================== */
  function scatter(elm, rows, opts) {
    opts = opts || {};
    clear(elm);
    // normalize rows
    var pts = rows.map(function (r) {
      var a = r.actual != null ? r.actual : r.actual_acres;
      var p = r.predicted != null ? r.predicted : r.predicted_acres;
      var lbl = r.label || (r.state ? r.state + " " + (r.year || "") : "");
      return { a: a, p: p, label: lbl.trim() };
    });
    var log = opts.log !== false; // default log for acres
    function tv(v) { return log ? Math.log10((v || 0) + 1) : v; }

    var W = 560,
      H = 520,
      m = { t: 22, r: 22, b: 54, l: 62 };
    var iw = W - m.l - m.r,
      ih = H - m.t - m.b;

    var all = [];
    pts.forEach(function (d) { all.push(tv(d.a)); all.push(tv(d.p)); });
    var lo = Math.min.apply(null, all),
      hi = Math.max.apply(null, all);
    var pad = (hi - lo) * 0.06 || 1;
    lo -= pad;
    hi += pad;
    function sx(v) { return m.l + ((tv(v) - lo) / (hi - lo)) * iw; }
    function sy(v) { return m.t + ih - ((tv(v) - lo) / (hi - lo)) * ih; }

    var s = svg(W, H, opts.label || "Predicted versus actual, with a 1:1 reference line.");

    // 1:1 line
    s.appendChild(el("line", {
      x1: m.l, y1: m.t + ih, x2: m.l + iw, y2: m.t,
      class: "wf-oneone", stroke: "var(--text-faint)", "stroke-dasharray": "5 5",
    }));
    s.appendChild(el("text", {
      x: m.l + iw - 4, y: m.t + 12, "text-anchor": "end", class: "wf-annot-sm",
      fill: "var(--text-faint)",
    }, "1:1"));

    // axes frame
    s.appendChild(el("line", { x1: m.l, y1: m.t, x2: m.l, y2: m.t + ih, class: "wf-axis" }));
    s.appendChild(el("line", { x1: m.l, y1: m.t + ih, x2: m.l + iw, y2: m.t + ih, class: "wf-axis" }));
    s.appendChild(el("text", {
      x: m.l + iw / 2, y: H - 12, "text-anchor": "middle", class: "wf-axis-title",
    }, opts.xlabel || (log ? "Actual (log₁₀ acres+1)" : "Actual")));
    s.appendChild(el("text", {
      x: 16, y: m.t + ih / 2, "text-anchor": "middle", class: "wf-axis-title",
      transform: "rotate(-90 16 " + (m.t + ih / 2) + ")",
    }, opts.ylabel || (log ? "Predicted (log₁₀ acres+1)" : "Predicted")));

    var detail = document.createElement("div");
    detail.className = "wf-scatter-detail";
    detail.setAttribute("aria-live", "polite");
    detail.textContent = "Focus or hover a point for its values.";

    pts.forEach(function (d) {
      var g = el("g", { class: "wf-pt", tabindex: "0", role: "button",
        "aria-label": (d.label || "point") + ", actual " + fmt(d.a) + " acres, predicted " + fmt(d.p) + " acres" });
      var c = el("circle", { cx: sx(d.a), cy: sy(d.p), r: 5, class: "wf-pt-dot",
        fill: "var(--ember)", stroke: "var(--bg)", "stroke-width": "1" });
      g.appendChild(c);
      g.appendChild(el("title", null,
        (d.label ? d.label + " — " : "") + "actual " + fmt(d.a) + ", predicted " + fmt(d.p)));
      function show() {
        detail.textContent =
          (d.label ? d.label + " — " : "") +
          "actual " + fmt(d.a) + " acres · predicted " + fmt(d.p) + " acres";
      }
      g.addEventListener("mouseenter", show);
      g.addEventListener("focus", show);
      s.appendChild(g);
    });

    elm.appendChild(s);
    elm.appendChild(detail);
    return s;
  }

  /* ---------- expose ---------- */
  window.WF = {
    load: load,
    fmt: fmt,
    macres: macres,
    envelope: envelope,
    heatmap: heatmap,
    tilemap: tilemap,
    eramap: eramap,
    scatter: scatter,
    // exposed for pages that want the exact palette / grid
    _emberRamp: emberRamp,
    _divergingRamp: divergingRamp,
    _tileGrid: TILE_GRID,
    reducedMotion: REDUCED,
  };
})();
