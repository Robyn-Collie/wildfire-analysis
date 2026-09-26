/* Wildfire map console. Copied to site/assets/console.js by scripts/build_site.py.
 *
 * Draws every FPA FOD fire (1992-2020) as a point with WebGL 1, no libraries. Point files and their
 * layout are written by scripts/build_points.py (see site/data/points_meta.json). Filters run on the GPU
 * as uniforms, so changing one does not re-upload data. Counts shown beside the map are computed on the
 * CPU from the same bits, so every picture carries its n.
 *
 * Usage: WFConsole.mount(element, {compact: bool, state: 'CA' | null, colorBy: 'cause' | 'size' | 'protection'})
 */
(function () {
  'use strict';

  var META_URL = 'data/points_meta.json', OUTLINE_URL = 'data/outline.json';
  var FILES = [['data/points_c_plus.bin', 'Fires of 10 acres or more'], ['data/points_a_b.bin', 'Fires under 10 acres']];
  var CAUSES = ['Human', 'Natural', 'Cause not recorded'];
  var CLASSES = ['A <0.25 ac', 'B 0.25-10', 'C 10-100', 'D 100-300', 'E 300-1,000', 'F 1,000-5,000', 'G 5,000+'];
  var PROT = ['GAP 1-2: managed for biodiversity', 'GAP 3: multiple use', 'GAP 4: no known mandate', 'Not in PAD-US'];
  var MONTH_START = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 366];
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  var VS = [
    'attribute vec2 a_pos; attribute vec2 a_attr;',
    'uniform vec2 u_scale; uniform vec2 u_offset; uniform float u_px; uniform float u_sizeBy;',
    'uniform vec2 u_year; uniform vec2 u_doy; uniform float u_state; uniform float u_gen;',
    'uniform float u_cause[3]; uniform float u_cls[7]; uniform float u_gap[4];',
    'uniform float u_colorBy; uniform vec3 u_pal[8];',
    'varying vec3 v_col;',
    'void main() {',
    '  float lo = a_attr.x; float hi = a_attr.y;',
    '  float year = mod(lo, 32.0); float doy = mod(floor(lo / 32.0), 512.0); float cause = floor(lo / 16384.0);',
    '  float cls = mod(hi, 8.0); float gap = mod(floor(hi / 8.0), 4.0); float st = mod(floor(hi / 32.0), 64.0); float gen = floor(hi / 2048.0);',
    '  float keep = step(u_year.x, year) * step(year, u_year.y);',
    '  keep *= (u_doy.x <= u_doy.y) ? step(u_doy.x, doy) * step(doy, u_doy.y) : max(step(u_doy.x, doy), step(doy, u_doy.y));',
    '  keep *= u_cause[int(cause)] * u_cls[int(cls)] * u_gap[int(gap)];',
    '  if (u_state >= 0.0) keep *= 1.0 - step(0.5, abs(st - u_state));',
    '  if (u_gen >= 0.0) keep *= 1.0 - step(0.5, abs(gen - u_gen));',
    '  if (keep < 0.5) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); gl_PointSize = 0.0; return; }',
    '  vec2 p = a_pos * u_scale + u_offset;',
    '  gl_Position = vec4(p.x, -p.y, 0.0, 1.0);',
    '  float s = u_px;',
    '  if (u_sizeBy > 0.5) s = u_px * (cls < 2.0 ? 0.8 : cls < 4.0 ? 1.2 : cls < 5.0 ? 2.0 : cls < 6.0 ? 2.8 : 4.0);',
    '  gl_PointSize = s;',
    '  if (u_colorBy < 0.5) v_col = u_pal[int(cause)];',
    '  else if (u_colorBy < 1.5) v_col = u_pal[int(cls < 2.0 ? 0.0 : cls < 4.0 ? 1.0 : cls < 6.0 ? 2.0 : 3.0) + 3];',
    '  else v_col = u_pal[int(gap) + 4];',
    '}'
  ].join('\n');
  var FS = [
    'precision mediump float; varying vec3 v_col; uniform float u_alpha;',
    'void main() { vec2 c = gl_PointCoord - 0.5; if (dot(c, c) > 0.25) discard; gl_FragColor = vec4(v_col, u_alpha); }'
  ].join('\n');

  function hex(c) {
    c = (c || '#888888').trim();
    if (c.indexOf('rgb') === 0) { var m = c.match(/\d+/g); return [m[0] / 255, m[1] / 255, m[2] / 255]; }
    if (c.length === 4) c = '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3];
    return [parseInt(c.substr(1, 2), 16) / 255, parseInt(c.substr(3, 2), 16) / 255, parseInt(c.substr(5, 2), 16) / 255];
  }
  // One retry after a short pause: a dropped connection on a phone should not leave the map empty.
  function get(url) {
    return fetch(url).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r; })
      .catch(function () { return new Promise(function (res) { setTimeout(res, 800); }).then(function () { return fetch(url); })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r; }); });
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function fmt(x) { return Math.round(x).toLocaleString('en-US'); }
  function pct(x) { return isFinite(x) ? (100 * x).toFixed(0) + '%' : 'n/a'; }

  function palette() {
    var cs = getComputedStyle(document.documentElement);
    var g = function (n) { return cs.getPropertyValue(n).trim(); };
    var dark = window.WF && WF.isDark ? WF.isDark() : false;
    return {
      dark: dark,
      // cause: human, natural, missing; size: small, medium, large, very large; protection: 4
      cause: [g('--s1'), g('--s2'), g('--missing')],
      size: [g('--seq-300'), g('--s4'), g('--s2'), g('--s8')],
      prot: [g('--s3'), g('--s1'), g('--s4'), g('--missing')],
      bg: g('--surface'), ink: g('--ink-2'), line: g('--axis')
    };
  }

  function Console(host, opts) {
    this.host = host; this.opts = opts || {};
    this.meta = null; this.outline = null; this.chunks = []; this.loaded = {};
    this.view = { k: 1, x: 0, y: 0 };
    this.f = { y0: 0, y1: 28, d0: 0, d1: 365, cause: [1, 1, 1], cls: [1, 1, 1, 1, 1, 1, 1], gap: [1, 1, 1, 1], state: -1, gen: -1,
               colorBy: opts.colorBy || 'cause', sizeBy: 1 };
    this.build();
  }

  Console.prototype.build = function () {
    var self = this, h = this.host;
    h.classList.add('console');
    h.textContent = '';
    var bar = el('div', 'console-bar');
    this.status = el('div', 'console-status', 'Loading fires...');
    var stage = el('div', 'console-stage');
    this.canvas = el('canvas', 'console-gl');
    this.overlay = el('canvas', 'console-lines');
    this.canvas.setAttribute('role', 'img');
    this.canvas.setAttribute('aria-label', 'Map of US wildfire ignition points, 1992-2020, filtered by the controls. Counts are listed beside the map.');
    stage.appendChild(this.overlay); stage.appendChild(this.canvas);
    var zoom = el('div', 'console-zoom');
    [['+', 1.6], ['−', 1 / 1.6], ['Reset', 0]].forEach(function (z) {
      var b = el('button', 'btn', z[0]); b.type = 'button';
      b.onclick = function () { if (!z[1]) self.view = { k: 1, x: 0, y: 0 }; else self.zoomAt(self.canvas.clientWidth / 2, self.canvas.clientHeight / 2, z[1]); self.draw(); };
      zoom.appendChild(b);
    });
    stage.appendChild(zoom);
    this.probe = el('div', 'console-probe'); this.probe.hidden = true; stage.appendChild(this.probe);
    this.controls = el('div', 'console-controls');
    this.legend = el('div', 'console-legend');
    this.counts = el('div', 'console-counts');
    h.appendChild(bar); bar.appendChild(this.status);
    h.appendChild(stage);
    var side = el('div', 'console-side');
    side.appendChild(this.legend); side.appendChild(this.counts); side.appendChild(this.controls);
    h.appendChild(side);
    this.stage = stage;
    this.initGL();
    if (!this.gl) return;
    this.bindPointer();
    Promise.all([get(META_URL).then(function (r) { return r.json(); }), get(OUTLINE_URL).then(function (r) { return r.json(); })])
      .then(function (res) {
        self.meta = res[0]; self.outline = res[1];
        self.buildControls();
        self.resize();
        return self.load(0);
      })
      .then(function () { if (self.opts.loadAll) return self.load(1); })
      .catch(function (e) { self.fail('The fire points did not load (' + e.message + ').'); });
    window.addEventListener('resize', function () { self.resize(); });
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      var re = function () { self.draw(); };
      if (mq.addEventListener) mq.addEventListener('change', re);
    }
    document.addEventListener('click', function (e) { if (e.target && e.target.classList && e.target.classList.contains('theme-btn')) setTimeout(function () { self.draw(); }, 0); });
  };

  Console.prototype.fail = function (msg) {
    this.status.textContent = msg + ' The charts on the other pages hold the same record as tables.';
    this.stage.classList.add('failed');
  };

  Console.prototype.initGL = function () {
    var gl = this.canvas.getContext('webgl', { antialias: false, premultipliedAlpha: false, preserveDrawingBuffer: true }) ||
             this.canvas.getContext('experimental-webgl');
    if (!gl) { this.fail('This browser has no WebGL, so the point map cannot draw.'); return; }
    function sh(type, src) { var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; }
    var p = gl.createProgram();
    try { gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, FS)); } catch (e) { this.fail('WebGL shader error: ' + e.message); return; }
    gl.linkProgram(p); gl.useProgram(p);
    this.gl = gl; this.prog = p;
    this.loc = {};
    var self = this;
    ['a_pos', 'a_attr'].forEach(function (n) { self.loc[n] = gl.getAttribLocation(p, n); });
    ['u_scale', 'u_offset', 'u_px', 'u_sizeBy', 'u_year', 'u_doy', 'u_state', 'u_gen', 'u_cause', 'u_cls', 'u_gap', 'u_colorBy', 'u_pal', 'u_alpha']
      .forEach(function (n) { self.loc[n] = gl.getUniformLocation(p, n); });
  };

  Console.prototype.load = function (i) {
    var self = this;
    if (this.loaded[i]) return Promise.resolve();
    this.loaded[i] = 'loading';
    this.status.textContent = 'Loading ' + FILES[i][1].toLowerCase() + '...';
    return get(FILES[i][0]).then(function (r) { return r.arrayBuffer(); }).then(function (buf) {
      var gl = self.gl, b = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, buf, gl.STATIC_DRAW);
      var u16 = new Uint16Array(buf), n = buf.byteLength / 8;
      self.chunks.push({ buf: b, n: n, u16: u16 });
      self.loaded[i] = true;
      if (i === 0 && self.f.state >= 0) self.fitState(u16, n);
      self.updateLoadButton();
      self.draw();
    });
  };

  // Zoom to the middle 98% of one state's fires (a few records carry wrong coordinates).
  Console.prototype.fitState = function (u16, n) {
    var xs = [], ys = [], st = this.f.state;
    for (var i = 0; i < n; i++) { var j = i * 4; if (((u16[j + 3] >> 5) & 63) === st) { xs.push(u16[j]); ys.push(u16[j + 1]); } }
    if (xs.length < 5) return;
    xs.sort(function (a, b) { return a - b; }); ys.sort(function (a, b) { return a - b; });
    var lo = Math.floor(xs.length * 0.01), hi = Math.ceil(xs.length * 0.99) - 1;
    var x0 = xs[lo], x1 = xs[hi], y0 = ys[lo], y1 = ys[hi];
    var w = this.canvas.clientWidth, h = this.canvas.clientHeight, b = this.base();
    var k = 0.85 * Math.min(w / (Math.max(20, x1 - x0) * b), h / (Math.max(20, y1 - y0) * b));
    k = Math.max(1, Math.min(40, k));
    this.view = { k: k, x: w / 2 - ((x0 + x1) / 2) * b * k, y: h / 2 - ((y0 + y1) / 2) * b * k };
    this.clamp();
  };

  Console.prototype.updateLoadButton = function () {
    if (!this.loadBtn) return;
    var all = this.loaded[1] === true;
    this.loadBtn.hidden = all;
    var n = this.chunks.reduce(function (s, c) { return s + c.n; }, 0);
    this.status.textContent = fmt(n) + ' fires loaded' + (all ? ' (every fire in the record).' : ' (10 acres and more). Fires under 10 acres are ' + fmt(this.meta.files['points_a_b.bin']) + ' more points.');
  };

  Console.prototype.buildControls = function () {
    var self = this, c = this.controls, m = this.meta, f = this.f;
    c.textContent = '';
    function group(label) { var fs = el('fieldset', 'cgroup'); fs.appendChild(el('legend', null, label)); c.appendChild(fs); return fs; }
    function rerun() { self.draw(); }
    // Load more
    this.loadBtn = el('button', 'btn load-all', 'Add the ' + fmt(m.files['points_a_b.bin']) + ' fires under 10 acres (16 MB)');
    this.loadBtn.type = 'button';
    this.loadBtn.onclick = function () { self.loadBtn.disabled = true; self.load(1).catch(function (e) { self.status.textContent = 'Could not load: ' + e.message; }); };
    c.appendChild(this.loadBtn);
    // Years
    var gy = group('Years');
    var y0 = el('input'), y1 = el('input'), yl = el('span', 'val');
    [y0, y1].forEach(function (inp, i) { inp.type = 'range'; inp.min = 0; inp.max = 28; inp.value = i ? f.y1 : f.y0; inp.setAttribute('aria-label', i ? 'Last year' : 'First year'); });
    function yr() { var a = +y0.value, b = +y1.value; if (a > b) { var t = a; a = b; b = t; } f.y0 = a; f.y1 = b; yl.textContent = (1992 + a) + (a === b ? '' : '-' + (1992 + b)); rerun(); }
    y0.oninput = yr; y1.oninput = yr; gy.appendChild(yl); gy.appendChild(y0); gy.appendChild(y1);
    var play = el('button', 'btn', 'Play by year'); play.type = 'button';
    play.onclick = function () {
      if (self.timer) { clearInterval(self.timer); self.timer = null; play.textContent = 'Play by year'; return; }
      var y = 0; play.textContent = 'Stop';
      self.timer = setInterval(function () { y0.value = y; y1.value = y; yr(); y++; if (y > 28) { clearInterval(self.timer); self.timer = null; play.textContent = 'Play by year'; } }, 650);
    };
    gy.appendChild(play);
    this.setYears = function (a, b) { y0.value = a - 1992; y1.value = b - 1992; yr(); };
    yr();
    // Season
    var gs = group('Months');
    var ms = el('select'), me = el('select');
    MONTHS.forEach(function (mn, i) { ms.appendChild(new Option(mn, i)); me.appendChild(new Option(mn, i)); });
    ms.value = 0; me.value = 11; ms.setAttribute('aria-label', 'From month'); me.setAttribute('aria-label', 'To month');
    function mo() { f.d0 = MONTH_START[+ms.value]; f.d1 = MONTH_START[+me.value + 1] - 1; rerun(); }
    ms.onchange = mo; me.onchange = mo;
    gs.appendChild(ms); gs.appendChild(document.createTextNode(' to ')); gs.appendChild(me);
    // Cause
    var gc = group('Cause');
    CAUSES.forEach(function (lab, i) { gc.appendChild(self.check(lab, f.cause, i, rerun)); });
    var gsel = el('select'); gsel.appendChild(new Option('Any general cause', -1));
    m.general_causes.forEach(function (g, i) { gsel.appendChild(new Option(g, i)); });
    gsel.onchange = function () { f.gen = +gsel.value; rerun(); }; gsel.setAttribute('aria-label', 'General cause');
    gc.appendChild(gsel);
    // Size
    var gz = group('Size class (acres)');
    CLASSES.forEach(function (lab, i) { gz.appendChild(self.check(lab, f.cls, i, rerun)); });
    // Protection
    var gp = group('Protected-area status (PAD-US)');
    PROT.forEach(function (lab, i) { gp.appendChild(self.check(lab, f.gap, i, rerun)); });
    // State
    var gst = group('State');
    var ss = el('select'); ss.appendChild(new Option('All states', -1));
    m.states.forEach(function (s, i) { ss.appendChild(new Option(s, i)); });
    ss.onchange = function () { f.state = +ss.value; rerun(); }; ss.setAttribute('aria-label', 'State');
    if (this.opts.state) { var si = m.states.indexOf(this.opts.state); if (si >= 0) { ss.value = si; f.state = si; } }
    gst.appendChild(ss);
    // Color
    var gcol = group('Colour by');
    [['cause', 'Cause'], ['size', 'Size'], ['protection', 'Protection']].forEach(function (o) {
      var lab = el('label', 'radio'), r = el('input'); r.type = 'radio'; r.name = 'colorby-' + (self.opts.id || 'c'); r.value = o[0]; r.checked = f.colorBy === o[0];
      r.onchange = function () { f.colorBy = o[0]; rerun(); };
      lab.appendChild(r); lab.appendChild(document.createTextNode(' ' + o[1])); gcol.appendChild(lab);
    });
    var sz = self.check('Bigger dots for bigger fires', { 0: f.sizeBy }, 0, function (v) { f.sizeBy = v; rerun(); }, true);
    gcol.appendChild(sz);
    if (this.opts.compact) c.classList.add('compact');
  };

  Console.prototype.check = function (label, arr, i, cb, single) {
    var lab = el('label', 'chk'), inp = el('input'); inp.type = 'checkbox'; inp.checked = !!arr[i];
    inp.onchange = function () { arr[i] = inp.checked ? 1 : 0; cb(arr[i]); };
    lab.appendChild(inp); lab.appendChild(document.createTextNode(' ' + label));
    return lab;
  };

  Console.prototype.resize = function () {
    if (!this.meta) return;
    var ext = this.meta.extent, w = this.stage.clientWidth || 600;
    var h = Math.round(w * ext[3] / ext[2]);
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    [this.canvas, this.overlay].forEach(function (cv) { cv.style.width = w + 'px'; cv.style.height = h + 'px'; cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); });
    this.stage.style.height = h + 'px';
    this.dpr = dpr;
    this.draw();
  };

  // frame units -> CSS px: px = (u * base) * k + x, base = width / 4096
  Console.prototype.base = function () { return this.canvas.clientWidth / this.meta.extent[2]; };
  Console.prototype.zoomAt = function (px, py, factor) {
    var v = this.view, k = Math.max(1, Math.min(40, v.k * factor)); factor = k / v.k;
    v.x = px - (px - v.x) * factor; v.y = py - (py - v.y) * factor; v.k = k; this.clamp();
  };
  Console.prototype.clamp = function () {
    var v = this.view, w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    v.x = Math.min(0, Math.max(w - w * v.k, v.x)); v.y = Math.min(0, Math.max(h - h * v.k, v.y));
  };

  Console.prototype.bindPointer = function () {
    var self = this, cv = this.canvas, drag = null, pts = {};
    cv.addEventListener('wheel', function (e) {
      e.preventDefault(); var r = cv.getBoundingClientRect();
      self.zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.25 : 0.8); self.draw();
    }, { passive: false });
    cv.addEventListener('pointerdown', function (e) {
      pts[e.pointerId] = { x: e.clientX, y: e.clientY };
      drag = { x: e.clientX, y: e.clientY, vx: self.view.x, vy: self.view.y, moved: false };
      cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener('pointermove', function (e) {
      if (!drag || !pts[e.pointerId]) return;
      var ids = Object.keys(pts);
      if (ids.length === 2) {
        var o = pts[ids[0]], p = pts[ids[1]], d0 = Math.hypot(o.x - p.x, o.y - p.y);
        pts[e.pointerId] = { x: e.clientX, y: e.clientY };
        o = pts[ids[0]]; p = pts[ids[1]];
        var d1 = Math.hypot(o.x - p.x, o.y - p.y), r = cv.getBoundingClientRect();
        if (d0 > 0) self.zoomAt((o.x + p.x) / 2 - r.left, (o.y + p.y) / 2 - r.top, d1 / d0);
        drag.moved = true; self.draw(); return;
      }
      pts[e.pointerId] = { x: e.clientX, y: e.clientY };
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      if (drag.moved && self.view.k > 1) { self.view.x = drag.vx + dx; self.view.y = drag.vy + dy; self.clamp(); self.draw(); }
    });
    function up(e) {
      delete pts[e.pointerId];
      if (drag && !drag.moved) { var r = cv.getBoundingClientRect(); self.probeAt(e.clientX - r.left, e.clientY - r.top); }
      if (!Object.keys(pts).length) drag = null;
    }
    cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', function (e) { delete pts[e.pointerId]; drag = null; });
  };

  // Decode one record's attribute words (u16 lo, hi) with the same rules as the shader.
  Console.prototype.pass = function (lo, hi) {
    var f = this.f, year = lo & 31, doy = (lo >> 5) & 511, cause = lo >> 14, cls = hi & 7, gap = (hi >> 3) & 3, st = (hi >> 5) & 63, gen = hi >> 11;
    if (year < f.y0 || year > f.y1) return false;
    if (f.d0 <= f.d1 ? (doy < f.d0 || doy > f.d1) : (doy < f.d0 && doy > f.d1)) return false;
    if (!f.cause[cause] || !f.cls[cls] || !f.gap[gap]) return false;
    if (f.state >= 0 && st !== f.state) return false;
    if (f.gen >= 0 && gen !== f.gen) return false;
    return true;
  };

  Console.prototype.tally = function (box) {
    var t = { n: 0, cause: [0, 0, 0], large: 0, gen: new Array(16).fill(0), gap: [0, 0, 0, 0], cls: new Array(7).fill(0) };
    for (var c = 0; c < this.chunks.length; c++) {
      var u = this.chunks[c].u16, n = this.chunks[c].n;
      for (var i = 0; i < n; i++) {
        var j = i * 4, lo = u[j + 2], hi = u[j + 3];
        if (box && (u[j] < box[0] || u[j] > box[2] || u[j + 1] < box[1] || u[j + 1] > box[3])) continue;
        if (!this.pass(lo, hi)) continue;
        t.n++; t.cause[lo >> 14]++; var cl = hi & 7; t.cls[cl]++; if (cl >= 4) t.large++; t.gen[hi >> 11]++; t.gap[(hi >> 3) & 3]++;
      }
    }
    return t;
  };

  Console.prototype.probeAt = function (px, py) {
    var v = this.view, b = this.base();
    var ux = ((px - v.x) / v.k) / b, uy = ((py - v.y) / v.k) / b;
    var r = 20 / (v.k * b); // 20 CSS px radius as a square, in frame units
    var box = [ux - r, uy - r, ux + r, uy + r];
    var t = this.tally(box), km = Math.round(2 * r * 1.16);
    var p = this.probe; p.hidden = false; p.textContent = '';
    p.style.left = Math.min(px + 12, this.canvas.clientWidth - 230) + 'px'; p.style.top = Math.max(0, py - 10) + 'px';
    var close = el('button', 'close', '×'); close.type = 'button'; close.setAttribute('aria-label', 'Close'); close.onclick = function () { p.hidden = true; };
    p.appendChild(close);
    p.appendChild(el('strong', null, fmt(t.n) + ' fires'));
    p.appendChild(el('div', 'small', 'in a square about ' + km + ' km across, with the current filters'));
    if (t.n) {
      var known = t.cause[0] + t.cause[1];
      p.appendChild(el('div', null, 'Human-caused: ' + pct(t.cause[0] / known) + ' of ' + fmt(known) + ' with a known cause'));
      p.appendChild(el('div', null, 'Cause not recorded: ' + pct(t.cause[2] / t.n)));
      p.appendChild(el('div', null, 'Reached 300+ acres: ' + fmt(t.large) + ' (' + (100 * t.large / t.n).toFixed(1) + '%)'));
      var gi = 0; for (var g = 0; g < 13; g++) if (g !== 11 && g !== 12 && t.gen[g] > t.gen[gi]) gi = g;
      if (t.gen[gi]) p.appendChild(el('div', null, 'Most common human cause: ' + this.meta.general_causes[gi].toLowerCase() + ' (' + fmt(t.gen[gi]) + ')'));
      p.appendChild(el('div', null, 'On land managed for biodiversity (GAP 1-2): ' + pct(t.gap[0] / t.n)));
    }
    if (!this.loaded[1]) p.appendChild(el('div', 'small muted', 'Counts cover fires of 10+ acres only until the small fires are added.'));
  };

  Console.prototype.draw = function () {
    if (!this.gl || !this.meta) return;
    var self = this;
    if (this.raf) return;
    this.raf = requestAnimationFrame(function () { self.raf = null; self.render(); });
  };

  Console.prototype.render = function () {
    var gl = this.gl, L = this.loc, f = this.f, pal = palette(), v = this.view;
    var W = this.canvas.width, H = this.canvas.height, dpr = this.dpr || 1;
    gl.viewport(0, 0, W, H);
    var bg = hex(pal.bg); gl.clearColor(bg[0], bg[1], bg[2], 1); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
    if (pal.dark) gl.blendFunc(gl.SRC_ALPHA, gl.ONE); else gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    var b = this.base(), cw = this.canvas.clientWidth, ch = this.canvas.clientHeight;
    // clip = ((u*b)*k + x) / cw * 2 - 1
    gl.uniform2f(L.u_scale, 2 * b * v.k / cw, 2 * b * v.k / ch);
    gl.uniform2f(L.u_offset, 2 * v.x / cw - 1, 2 * v.y / ch - 1);
    var n = this.chunks.reduce(function (s, c) { return s + c.n; }, 0);
    var px = Math.max(1, Math.min(6, (0.9 + 0.35 * Math.log(v.k + 1)) * dpr * (n > 1e6 ? 0.85 : 1)));
    gl.uniform1f(L.u_px, px);
    gl.uniform1f(L.u_sizeBy, f.sizeBy);
    gl.uniform2f(L.u_year, f.y0, f.y1);
    gl.uniform2f(L.u_doy, f.d0, f.d1);
    gl.uniform1f(L.u_state, f.state); gl.uniform1f(L.u_gen, f.gen);
    gl.uniform1fv(L.u_cause, f.cause); gl.uniform1fv(L.u_cls, f.cls); gl.uniform1fv(L.u_gap, f.gap);
    gl.uniform1f(L.u_colorBy, f.colorBy === 'cause' ? 0 : f.colorBy === 'size' ? 1 : 2);
    var cols = [];
    pal.cause.concat([pal.size[0]]).slice(0, 3).forEach(function (c) { cols = cols.concat(hex(c)); });
    // u_pal: 0-2 cause, 3-6 size groups (index +3), 4-7 protection (index +4). Size and protection overlap
    // slots, so fill per mode.
    var slots = new Array(8);
    if (f.colorBy === 'cause') { slots[0] = pal.cause[0]; slots[1] = pal.cause[1]; slots[2] = pal.cause[2]; }
    else if (f.colorBy === 'size') { for (var s = 0; s < 4; s++) slots[s + 3] = pal.size[s]; }
    else { for (var q = 0; q < 4; q++) slots[q + 4] = pal.prot[q]; }
    var flat = []; for (var i = 0; i < 8; i++) flat = flat.concat(hex(slots[i] || '#888888'));
    gl.uniform3fv(L.u_pal, new Float32Array(flat));
    var alpha = pal.dark ? (n > 1e6 ? 0.25 : 0.45) : (n > 1e6 ? 0.35 : 0.55);
    gl.uniform1f(L.u_alpha, alpha);
    for (var c = 0; c < this.chunks.length; c++) {
      var ck = this.chunks[c];
      gl.bindBuffer(gl.ARRAY_BUFFER, ck.buf);
      gl.enableVertexAttribArray(L.a_pos); gl.vertexAttribPointer(L.a_pos, 2, gl.UNSIGNED_SHORT, false, 8, 0);
      gl.enableVertexAttribArray(L.a_attr); gl.vertexAttribPointer(L.a_attr, 2, gl.UNSIGNED_SHORT, false, 8, 4);
      gl.drawArrays(gl.POINTS, 0, ck.n);
    }
    this.drawOutline(pal);
    this.drawLegend(pal);
  };

  Console.prototype.drawOutline = function (pal) {
    var cv = this.overlay, ctx = cv.getContext('2d'), v = this.view, b = this.base(), d = this.dpr || 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.setTransform(d * b * v.k, 0, 0, d * b * v.k, d * v.x, d * v.y);
    ctx.lineWidth = 0.8 / (b * v.k); ctx.strokeStyle = pal.line;
    ctx.beginPath();
    this.outline.forEach(function (line) { ctx.moveTo(line[0][0], line[0][1]); for (var i = 1; i < line.length; i++) ctx.lineTo(line[i][0], line[i][1]); });
    ctx.stroke();
  };

  Console.prototype.drawLegend = function (pal) {
    var f = this.f, lg = this.legend, t = this.tally(null);
    lg.textContent = '';
    var names, cols, counts;
    if (f.colorBy === 'cause') { names = CAUSES; cols = pal.cause; counts = t.cause; }
    else if (f.colorBy === 'size') { names = ['Under 10 acres (A-B)', '10-300 acres (C-D)', '300-5,000 acres (E-F)', '5,000+ acres (G)']; cols = pal.size; counts = [t.cls[0] + t.cls[1], t.cls[2] + t.cls[3], t.cls[4] + t.cls[5], t.cls[6]]; }
    else { names = PROT; cols = pal.prot; counts = t.gap; }
    var head = el('div', 'console-n'); head.appendChild(el('strong', null, fmt(t.n))); head.appendChild(document.createTextNode(' fires shown'));
    lg.appendChild(head);
    var ul = el('ul', 'console-keys');
    names.forEach(function (nm, i) {
      var li = el('li'), sw = el('span', 'swatch'); sw.style.background = cols[i];
      li.appendChild(sw); li.appendChild(document.createTextNode(' ' + nm + ' '));
      li.appendChild(el('span', 'muted', fmt(counts[i]) + (t.n ? ' (' + (100 * counts[i] / t.n).toFixed(0) + '%)' : '')));
      ul.appendChild(li);
    });
    lg.appendChild(ul);
    this.counts.textContent = 'Of these, ' + fmt(t.large) + ' reached 300 acres or more. Click the map for counts around a point. Dots overlap: dense areas saturate, so read the counts, not the brightness.';
  };

  window.WFConsole = {
    mount: function (elOrId, opts) {
      var h = typeof elOrId === 'string' ? document.getElementById(elOrId) : elOrId;
      if (!h) return null;
      var c = new Console(h, opts || {});
      h._console = c;
      return c;
    }
  };
})();
