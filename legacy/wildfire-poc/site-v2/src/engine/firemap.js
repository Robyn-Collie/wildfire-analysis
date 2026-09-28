/**
 * firemap.js — the us-wildfires v2 WebGL2 point engine.
 *
 * ONE shader pair renders all five point scenes; scenes differ by a `uMode`
 * uniform plus mode-specific uniforms. A single VBO is uploaded once at
 * `create()`; every `setMode` / `setDay` / `setYear` / filter change is
 * uniforms-only (no re-upload), per design-spec-v2 §3 / §8.
 *
 * Record layout (points-v2.bin, 8 bytes/fire, 4×uint16 LE — verified against
 * the real blob header points-v2.json):
 *   w0 = x  (quantized 0..65535 within the fire's REGION bounds)
 *   w1 = y  (quantized 0..65535 within the fire's REGION bounds)
 *   w2 = doy<<3 | class            (doy 1..366, class 0..6 == A..G)
 *   w3 = year5<<11 | cause2<<9 | region2<<7 | state6<<1
 *        year5  = FIRE_YEAR-1992 (0..28)
 *        cause2 = 0 Human · 1 Natural · 2 Missing/undetermined
 *        region2= 0 CONUS · 1 AK · 2 HI
 *        state6 = index into header.states (postal, sorted)
 *
 * The season shader is a faithful port of site/hero.html's PROVEN shader —
 * the tuned constants are kept EXACTLY: gaussian σ=12, 10% ember floor
 * (wf = 0.10 + 0.90*vW), alpha curve (0.030 + 0.10*t + 0.09*t*t),
 * soft = exp(-r2*18), point size base = 1 + cls*cls*0.45, additive blending.
 *
 * @module firemap
 */

/* ------------------------------------------------------------------ */
/* Region placement                                                    */
/* ------------------------------------------------------------------ */
/**
 * Placement of the three region rects inside NDC, all derived from
 * header.regions bounds. CONUS fills the main stage (aspect-correct,
 * matching the hero fit); AK and HI are small insets bottom-left.
 * AK ~22% of stage width, HI ~10%, per spec §3.
 * @private
 */
const REGION_LAYOUT = [
  // idx 0 = CONUS main; computed at resize() for aspect-correct fill.
  { key: 'CONUS', wFrac: 1.0 },
  { key: 'AK', wFrac: 0.22 },
  { key: 'HI', wFrac: 0.10 },
];

/* ------------------------------------------------------------------ */
/* Shaders                                                             */
/* ------------------------------------------------------------------ */

const VERT = `#version 300 es
layout(location=0) in vec3 a;   // x, y, packed lo   (w0, w1, w2 widened to float)
layout(location=1) in float b;  // packed hi         (w3 widened to float)

uniform int   uMode;            // 0 season · 1 years · 2 cause · 3 drought · 4 explore
uniform float uDay;             // 1..366 composite day (season / drought pulse)
uniform float uSigma;           // gaussian sigma (season: 12)
uniform float uYear;            // 1992..2020 (years sweep / drought year)
uniform float uPointScale;      // dpr-scaled base point size
uniform vec2  uScale, uOffset;  // CONUS main-rect NDC transform
uniform vec2  uAkScale, uAkOffset;   // AK inset transform
uniform vec2  uHiScale, uHiOffset;   // HI inset transform

// camera (v3 console): zoom/pan applied AFTER the CONUS transform. Insets
// keep their fixed corner placement and fade out as the camera moves in.
uniform float uCamZoom;         // 1..60
uniform vec2  uCamPan;          // NDC offset at current zoom

// cause mode
uniform int   uLens;            // 0 all · 1 human · 2 natural

// perf guard: classes < uClassFloor are dropped (culled offscreen)
uniform float uClassFloor;

// explore-mode filters
uniform float uYearMin, uYearMax;      // inclusive FIRE_YEAR range
uniform int   uCauseMask;              // bit c set => cause c allowed (bits 0,1,2)
uniform float uClassMin, uClassMax;    // inclusive class range 0..6
uniform float uMonthMin, uMonthMax;    // inclusive month range 1..12
uniform int   uMonstersOnly;           // 1 => class G (6) only
uniform uint  uStateMaskLo, uStateMaskHi; // 64-bit state allow mask (state6)

// drought-mode PDSI texture: R8, width = 29*12 = 348, height = stateCount.
uniform sampler2D uPdsi;
uniform int   uHasPdsi;         // 1 when texture bound

out float vW;      // pulse weight 0..1
out float vCls;    // class 0..6
out float vDim;    // 1.0 normally, <1 when dimmed (cause lens non-selected)
out vec3  vTint;   // per-point drought tint multiplier (1,1,1 when unused)

// month-of-year (1..12) from day-of-year, cumulative non-leap month starts.
int monthOfDoy(float doy){
  float d = floor(doy);
  if (d >= 335.0) return 12;
  if (d >= 305.0) return 11;
  if (d >= 274.0) return 10;
  if (d >= 244.0) return 9;
  if (d >= 213.0) return 8;
  if (d >= 182.0) return 7;
  if (d >= 152.0) return 6;
  if (d >= 121.0) return 5;
  if (d >= 91.0)  return 4;
  if (d >= 60.0)  return 3;
  if (d >= 32.0)  return 2;
  return 1;
}

void main(){
  // ---- unpack ----
  float w2 = a.z;
  float cls = mod(w2, 8.0);
  float doy = floor(w2 / 8.0);

  float w3 = b;
  float state6 = mod(floor(w3 / 2.0), 64.0);
  float region2 = mod(floor(w3 / 128.0), 4.0);
  float cause2 = mod(floor(w3 / 512.0), 4.0);
  float year5 = mod(floor(w3 / 2048.0), 32.0);
  float fyear = 1992.0 + year5;
  int month = monthOfDoy(doy);

  vCls = cls;
  vDim = 1.0;
  vTint = vec3(1.0);

  // ---- perf guard: cull below class floor ----
  bool cull = cls < uClassFloor;

  // ---- pulse weight (season / drought share the composite-day gaussian) ----
  float d = abs(doy - uDay); d = min(d, 366.0 - d);
  float w = exp(-(d*d) / (2.0 * uSigma * uSigma));

  if (uMode == 1) {
    // YEARS: ignite in FIRE_YEAR, 2-year afterglow decay. Full brightness on
    // the sweep year, linear falloff to 0 across the two following years.
    float age = uYear - fyear;
    if (age < 0.0 || age > 2.0) { cull = true; }
    w = clamp(1.0 - age / 2.0, 0.0, 1.0);
  } else if (uMode == 2) {
    // CAUSE: lens 0 all / 1 human(cause2==0) / 2 natural(cause2==1).
    // Non-selected dimmed to 8% rather than culled (theatrical fade).
    if (uLens == 1 && cause2 != 0.0) vDim = 0.08;
    if (uLens == 2 && cause2 != 1.0) vDim = 0.08;
  } else if (uMode == 3) {
    // DROUGHT: season pulse × per-point PDSI tint for the selected year.
    float qy = floor(uYear + 0.5);
    if (fyear != qy) { cull = true; }        // show only the selected year
    if (uHasPdsi == 1) {
      int col = int(qy - 1992.0) * 12 + (month - 1);
      float raw = texelFetch(uPdsi, ivec2(col, int(state6)), 0).r; // 0..1 (R8)
      if (raw > 0.998) {
        vTint = vec3(1.0);                     // 255 sentinel => neutral
      } else {
        // pdsi 0..254 -> -8..+8 : v = raw*255 mapped. wet (>0) -> teal-ash,
        // dry (<0) -> parched desaturated red-white.
        float pdsi = (raw * 255.0) / 254.0 * 16.0 - 8.0;   // -8..+8
        // saturate at |PDSI| 4 (severe drought/very wet), not the +-8 codomain
        // edge — real droughts live at -3..-4 and were landing mid-ramp where
        // the tint read as neutral.
        float dry = clamp(-pdsi / 4.0, 0.0, 1.0);          // 0 wet .. 1 dry
        float wet = clamp( pdsi / 4.0, 0.0, 1.0);          // 0 dry .. 1 wet
        // tint strength retuned at integration: (1.30,0.95,0.85) read as
        // neutral at typical |PDSI| ~4 — the parch was invisible on screen.
        vec3 parched = vec3(1.50, 0.78, 0.58);             // parched red-white
        vec3 tealAsh = vec3(0.48, 0.92, 1.04);             // deep teal-ash
        vTint = mix(vec3(1.0), parched, dry);
        vTint = mix(vTint, tealAsh, wet);
      }
    }
  } else if (uMode == 4) {
    // EXPLORE: uniform filters. Any failing predicate culls the point.
    if (fyear < uYearMin || fyear > uYearMax) cull = true;
    if ((uCauseMask & (1 << int(cause2))) == 0) cull = true;
    if (cls < uClassMin || cls > uClassMax) cull = true;
    if (float(month) < uMonthMin || float(month) > uMonthMax) cull = true;
    if (uMonstersOnly == 1 && cls < 6.0) cull = true;
    // 64-bit state mask across two uint32 uniforms.
    uint s = uint(state6 + 0.5);
    uint bit = (s < 32u) ? (uStateMaskLo >> s) : (uStateMaskHi >> (s - 32u));
    if ((bit & 1u) == 0u) cull = true;
    // explore is a static composite (no time pulse): show all matching at full weight.
    w = 1.0;
  }

  vW = w;

  // ---- region placement ----
  vec2 p = vec2(a.x, a.y) / 65535.0;
  vec2 clip;
  float zoomGain = 1.0;                       // CONUS-only point growth
  if (region2 == 1.0 || region2 == 2.0) {
    // insets: fixed corner placement; fade out (then cull) as the camera
    // moves into the CONUS so they never float over zoomed content.
    clip = (region2 == 1.0)
      ? p * uAkScale + uAkOffset
      : p * uHiScale + uHiOffset;
    float insetFade = clamp(2.0 - uCamZoom, 0.0, 1.0);
    if (insetFade <= 0.0) cull = true;
    vDim *= insetFade;
  } else {
    clip = (p * uScale + uOffset) * uCamZoom + uCamPan;
    zoomGain = sqrt(uCamZoom);
  }

  // Cull by shoving fully offscreen with zero size (cheaper than branching draw).
  if (cull) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    gl_PointSize = 0.0;
    vW = 0.0;
    return;
  }

  gl_Position = vec4(clip, 0.0, 1.0);

  // size: hero-proven base = 1 + cls*cls*0.45, modulated by pulse weight.
  // zoomGain grows CONUS points ~sqrt(zoom) so per-pixel energy holds while
  // the field spreads apart.
  float base = 1.0 + cls * cls * 0.45;
  gl_PointSize = max(uPointScale * base * zoomGain * (0.35 + 0.65 * w), 1.0);
}
`;

const FRAG = `#version 300 es
precision mediump float;
in float vW; in float vCls; in float vDim; in vec3 vTint;
uniform float uExposure;   // overdraw compensation, set in resize()
out vec4 o;
void main(){
  vec2 c = gl_PointCoord - 0.5; float r2 = dot(c, c);
  if (r2 > 0.25) discard;
  float soft = exp(-r2 * 18.0);
  // ember ramp by class: dim rust (A) -> white-hot (G). PROVEN hero constants.
  float t = vCls / 6.0;
  vec3 col = mix(vec3(0.55, 0.22, 0.05), vec3(1.0, 0.86, 0.62), t);
  col = mix(col, vec3(1.0, 0.97, 0.92), t * t);
  col *= vTint;                                  // drought tint (1,1,1 elsewhere)
  float wf = 0.10 + 0.90 * vW;                   // 10% ember floor
  // uExposure compensates overdraw density: the hero alphas were tuned at
  // desktop widths; on a phone the same million points land on half the
  // pixels and the additive blend blows out white.
  float a = wf * soft * (0.030 + 0.10 * t + 0.09 * t * t) * vDim * uExposure;
  o = vec4(col * a, a);                          // premultiplied, additive
}
`;

/* Density colormap pass (v3 console): the point pass accumulates into a
   half-res offscreen target with big soft kernels; this fullscreen pass maps
   accumulated energy through an ember ramp. gl_VertexID triangle — no VBO. */
const DENSITY_VS = `#version 300 es
out vec2 vUv;
void main(){
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
`;

const DENSITY_FS = `#version 300 es
precision mediump float;
in vec2 vUv;
uniform sampler2D uField;
uniform float uGain;    // energy normalization
uniform float uMix;     // 0 points-only .. 1 density-only
out vec4 o;
vec3 ramp(float t){
  // dark -> deep rust -> ember -> near-white (matches the point palette)
  vec3 c0 = vec3(0.03, 0.02, 0.015);
  vec3 c1 = vec3(0.30, 0.08, 0.02);
  vec3 c2 = vec3(0.92, 0.42, 0.10);
  vec3 c3 = vec3(1.00, 0.90, 0.65);
  vec3 c = mix(c0, c1, smoothstep(0.00, 0.35, t));
  c = mix(c, c2, smoothstep(0.35, 0.75, t));
  c = mix(c, c3, smoothstep(0.75, 1.00, t));
  return c;
}
void main(){
  vec3 field = texture(uField, vUv).rgb;
  float lum = dot(field, vec3(0.5, 0.35, 0.15));
  float t = 1.0 - exp(-lum * uGain);       // soft knee, no hard clip
  vec3 bg = vec3(0.027, 0.024, 0.016);     // matches clearColor
  o = vec4(bg + ramp(t) * t * uMix, 1.0);
}
`;

/* ------------------------------------------------------------------ */
/* Small helpers                                                       */
/* ------------------------------------------------------------------ */

/** Compile a shader or throw with the info log. @private */
function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(s);
    gl.deleteShader(s);
    throw new Error('shader compile failed: ' + log);
  }
  return s;
}

/** Aspect-correct fit of a lon/lat span into NDC, hero-style. @private */
function fitSpan(lonSpan, latSpan, viewAspect, fill) {
  // horizontal compressed by cos(mid-lat) is folded into lonSpan by the caller.
  const dataAspect = lonSpan / latSpan;
  let sx = fill, sy = fill;
  if (viewAspect > dataAspect) sx = sy * dataAspect / viewAspect;
  else sy = sx * viewAspect / dataAspect;
  return { sx, sy };
}

const MONTH_DAY0 = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
/** Composite month index 0..11 from a fractional day 1..366. @private */
function monthOfDay(d) {
  for (let i = 11; i >= 0; i--) if (d > MONTH_DAY0[i]) return i;
  return 0;
}

/* ------------------------------------------------------------------ */
/* FireMap                                                             */
/* ------------------------------------------------------------------ */

/**
 * The WebGL2 point-scene engine. Construct via {@link FireMap.create}.
 *
 * Public API (all documented on the prototype below):
 *   setMode(mode, opts) · setDay(day) · setYear(year) ·
 *   play() · pause() · setSpeed(x) · on(event, cb) · destroy()
 *
 * Events (via `on`): `'frame'` → {day, year, fps}; `'degraded'` → {classFloor}.
 */
class FireMap {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {ArrayBuffer} blob   points-v2.bin
   * @param {object} header      parsed points-v2.json (regions, states, …)
   * @param {object} [opts]
   * @param {('season'|'years'|'cause'|'drought'|'explore')} [opts.mode='season']
   * @param {boolean} [opts.reducedMotion] defaults to the media query
   * @param {string}  [opts.ariaLabel] set as the canvas aria-label
   * @private  Use {@link FireMap.create}.
   */
  constructor(canvas, blob, header, opts = {}) {
    this.canvas = canvas;
    this.header = header;
    this.opts = opts;
    this._listeners = { frame: [], degraded: [] };

    this.reduced = opts.reducedMotion != null
      ? opts.reducedMotion
      : (typeof matchMedia === 'function' &&
         matchMedia('(prefers-reduced-motion: reduce)').matches);

    // a11y: every scene is an image with a settable label.
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', opts.ariaLabel || 'Wildfire ignition map');

    const gl = canvas.getContext('webgl2', { antialias: false, alpha: false });
    if (!gl) throw new Error('WebGL2 unavailable');
    this.gl = gl;
    // float accumulation for the density field (no 8-bit clipping); RGBA8
    // fallback keeps the feature working where the extension is missing.
    this._floatFbo = !!gl.getExtension('EXT_color_buffer_float');

    // ---- program ----
    const prog = gl.createProgram();
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      throw new Error('program link failed: ' + gl.getProgramInfoLog(prog));
    }
    gl.useProgram(prog);
    this.prog = prog;

    // ---- uniforms ----
    this.U = {};
    [
      'uMode', 'uDay', 'uSigma', 'uYear', 'uPointScale', 'uExposure',
      'uCamZoom', 'uCamPan',
      'uScale', 'uOffset', 'uAkScale', 'uAkOffset', 'uHiScale', 'uHiOffset',
      'uLens', 'uClassFloor',
      'uYearMin', 'uYearMax', 'uCauseMask', 'uClassMin', 'uClassMax',
      'uMonthMin', 'uMonthMax', 'uMonstersOnly', 'uStateMaskLo', 'uStateMaskHi',
      'uPdsi', 'uHasPdsi',
    ].forEach((n) => { this.U[n] = gl.getUniformLocation(prog, n); });

    // ---- density colormap program (v3 console) ----
    const dprog = gl.createProgram();
    gl.attachShader(dprog, compile(gl, gl.VERTEX_SHADER, DENSITY_VS));
    gl.attachShader(dprog, compile(gl, gl.FRAGMENT_SHADER, DENSITY_FS));
    gl.linkProgram(dprog);
    if (!gl.getProgramParameter(dprog, gl.LINK_STATUS)) {
      throw new Error('density program link failed: ' + gl.getProgramInfoLog(dprog));
    }
    this.dProg = dprog;
    this.DU = {};
    ['uField', 'uGain', 'uMix'].forEach((n) => {
      this.DU[n] = gl.getUniformLocation(dprog, n);
    });
    gl.useProgram(dprog);
    gl.uniform1i(this.DU.uField, 1);       // field texture lives on unit 1
    gl.uniform1f(this.DU.uGain, 3.0);
    gl.useProgram(prog);
    this.densityOn = false;
    this._dMix = 0;
    this._fbo = null;
    this._fboTex = null;
    this._fboW = 0;
    this._fboH = 0;

    // ---- decode + single VBO upload ----
    // Records are uint16; the attribute is fed as float (widened) exactly like
    // the hero. We split into two attributes: vec3 (w0,w1,w2) + float (w3).
    const u16 = new Uint16Array(blob);
    this.N = (u16.length / 4) | 0;
    const lo = new Float32Array(this.N * 3);   // x, y, w2
    const hi = new Float32Array(this.N);       // w3
    for (let i = 0; i < this.N; i++) {
      const o = i * 4;
      lo[i * 3] = u16[o];
      lo[i * 3 + 1] = u16[o + 1];
      lo[i * 3 + 2] = u16[o + 2];
      hi[i] = u16[o + 3];
    }

    this.vboLo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vboLo);
    gl.bufferData(gl.ARRAY_BUFFER, lo, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

    this.vboHi = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vboHi);
    gl.bufferData(gl.ARRAY_BUFFER, hi, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 1, gl.FLOAT, false, 0, 0);

    // retain the raw records for the picker (a view over the fetched blob —
    // no copy). The grid index builds lazily on first pick().
    this._u16 = u16;
    this._pickGrid = null;

    // ---- default uniform state ----
    this.pdsiTex = null;
    this._setDefaults();

    // ---- runtime state ----
    this.mode = 'season';
    this.modeId = 0;
    this.day = this.reduced ? 200 : 1;
    this.year = 2020;
    this.speed = 1;
    this.playing = false;         // never autoplay; caller opts in via play()
    this._raf = null;
    this._last = null;
    this.SECS_PER_YEAR = 32;      // matches hero cadence

    // fps guard state (spec §8)
    this._fpsSamples = [];
    this._lowSince = null;
    this.classFloor = 0;
    this.fps = 60;

    // camera (v3 console)
    this.cam = { z: 1, x: 0, y: 0 };

    this._onResize = () => this.resize();
    addEventListener('resize', this._onResize);
    this.resize();

    if (opts.mode) this.setMode(opts.mode, opts);
    else { gl.uniform1i(this.U.uMode, 0); this.draw(); }
  }

  /**
   * Create a FireMap bound to a canvas.
   * @param {HTMLCanvasElement} canvas
   * @param {ArrayBuffer} blob   points-v2.bin contents
   * @param {object} header      parsed points-v2.json
   * @param {object} [opts]      {mode, reducedMotion, ariaLabel}
   * @returns {FireMap}
   */
  static create(canvas, blob, header, opts = {}) {
    return new FireMap(canvas, blob, header, opts);
  }

  /** Establish neutral defaults for every uniform. @private */
  _setDefaults() {
    const { gl, U } = this;
    gl.uniform1i(U.uMode, 0);
    gl.uniform1f(U.uDay, this.reduced ? 200 : 1);
    gl.uniform1f(U.uSigma, 12.0);
    gl.uniform1f(U.uYear, 2020.0);
    gl.uniform1i(U.uLens, 0);
    gl.uniform1f(U.uClassFloor, 0.0);
    gl.uniform1f(U.uYearMin, 1992.0);
    gl.uniform1f(U.uYearMax, 2020.0);
    gl.uniform1i(U.uCauseMask, 0b111);
    gl.uniform1f(U.uClassMin, 0.0);
    gl.uniform1f(U.uClassMax, 6.0);
    gl.uniform1f(U.uMonthMin, 1.0);
    gl.uniform1f(U.uMonthMax, 12.0);
    gl.uniform1i(U.uMonstersOnly, 0);
    gl.uniform1ui(U.uStateMaskLo, 0xffffffff);
    gl.uniform1ui(U.uStateMaskHi, 0xffffffff);
    gl.uniform1i(U.uHasPdsi, 0);
    gl.uniform1i(U.uPdsi, 0);
    gl.uniform1f(U.uExposure, 1.0);
    gl.uniform1f(U.uCamZoom, 1.0);
    gl.uniform2f(U.uCamPan, 0.0, 0.0);
  }

  /* ---------------- layout ---------------- */

  /**
   * Recompute canvas backing size and all region transforms. Called on
   * construction and window resize; safe to call manually.
   */
  resize() {
    const { gl, canvas } = this;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.floor(canvas.clientWidth || innerWidth) * dpr);
    canvas.height = Math.max(1, Math.floor(canvas.clientHeight || innerHeight) * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    const viewAspect = canvas.width / canvas.height;

    const regions = this.header.regions || [];
    const conus = regions[0] || { bounds: [-125, -66, 24, 50] };
    const ak = regions[1] || { bounds: [-170, -129, 54, 72] };
    const hi = regions[2] || { bounds: [-161, -154, 18.5, 22.8] };

    // --- CONUS main rect (hero fit) ---
    const cMidLat = (conus.bounds[2] + conus.bounds[3]) / 2;
    const cLonSpan = (conus.bounds[1] - conus.bounds[0]) * Math.cos(cMidLat * Math.PI / 180);
    const cLatSpan = conus.bounds[3] - conus.bounds[2];
    const cf = fitSpan(cLonSpan, cLatSpan, viewAspect, 1.72);
    gl.uniform2f(this.U.uScale, cf.sx, cf.sy);
    gl.uniform2f(this.U.uOffset, -cf.sx / 2, -cf.sy / 2 - 0.04);

    // --- insets bottom-left. Each keeps its own aspect; widths per REGION_LAYOUT. ---
    // Inset NDC width fractions (of full 2.0 NDC span).
    const place = (bounds, wFrac, xNdc, yNdc) => {
      const midLat = (bounds[2] + bounds[3]) / 2;
      const lonSpan = (bounds[1] - bounds[0]) * Math.cos(midLat * Math.PI / 180);
      const latSpan = bounds[3] - bounds[2];
      const wNdc = 2.0 * wFrac;                       // desired NDC width
      const hNdc = wNdc * (latSpan / lonSpan) * viewAspect; // aspect-correct height
      // p in [0,1] -> [xNdc, xNdc+wNdc] × [yNdc, yNdc+hNdc]
      return {
        scale: [wNdc, hNdc],
        offset: [xNdc, yNdc],
      };
    };

    const akP = place(ak.bounds, REGION_LAYOUT[1].wFrac, -0.97, -0.92);
    gl.uniform2f(this.U.uAkScale, akP.scale[0], akP.scale[1]);
    gl.uniform2f(this.U.uAkOffset, akP.offset[0], akP.offset[1]);

    // HI sits just to the right of AK.
    const hiX = akP.offset[0] + akP.scale[0] + 0.03;
    const hiP = place(hi.bounds, REGION_LAYOUT[2].wFrac, hiX, -0.92);
    gl.uniform2f(this.U.uHiScale, hiP.scale[0], hiP.scale[1]);
    gl.uniform2f(this.U.uHiOffset, hiP.offset[0], hiP.offset[1]);

    this._pointScale = 1.1 * dpr;
    gl.uniform1f(this.U.uPointScale, this._pointScale);

    // overdraw compensation: alphas were tuned at desktop widths; scale the
    // energy down as the CSS width shrinks so phones don't blow out white.
    const cssW = canvas.clientWidth || innerWidth;
    this._exposure = Math.min(1, Math.max(0.4, cssW / 1100));
    gl.uniform1f(this.U.uExposure, this._exposure);

    // stash the CONUS transform for the picker's inverse mapping.
    this._conus = { sx: cf.sx, sy: cf.sy, ox: -cf.sx / 2, oy: -cf.sy / 2 - 0.04 };

    // density accumulation target: half-res, recreated when the canvas
    // backing size changes.
    const fw = Math.max(1, canvas.width >> 1);
    const fh = Math.max(1, canvas.height >> 1);
    if (fw !== this._fboW || fh !== this._fboH) {
      if (this._fboTex) gl.deleteTexture(this._fboTex);
      if (this._fbo) gl.deleteFramebuffer(this._fbo);
      this._fboTex = gl.createTexture();
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, this._fboTex);
      if (this._floatFbo) {
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, fw, fh, 0, gl.RGBA, gl.HALF_FLOAT, null);
      } else {
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, fw, fh, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      }
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      this._fbo = gl.createFramebuffer();
      gl.bindFramebuffer(gl.FRAMEBUFFER, this._fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this._fboTex, 0);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      this._fboW = fw; this._fboH = fh;
    }

    if (!this.playing) this.draw();
  }

  /* ---------------- density mode (v3 console) ---------------- */

  /**
   * Toggle the density/heat rendering. While on, the density weight
   * crossfades automatically with camera zoom (full field at z<=1, gone by
   * z>=3); points re-emerge underneath as the field fades.
   * @param {boolean} on
   * @returns {FireMap} this
   */
  setDensity(on) {
    this.densityOn = !!on;
    this._updateDensityMix();
    if (!this.playing) this.draw();
    return this;
  }

  /** @private zoom-linked crossfade weight. */
  _updateDensityMix() {
    this._dMix = this.densityOn
      ? Math.min(1, Math.max(0, (3 - this.cam.z) / 2))
      : 0;
  }

  /* ---------------- camera (v3 console) ---------------- */

  /**
   * Set the camera directly. zoom clamps to [1, 60]; pan clamps so the CONUS
   * never leaves the frame entirely. Redraws when paused, emits 'camera'.
   * @param {{z?:number, x?:number, y?:number}} cam
   * @returns {FireMap} this
   */
  setCamera(cam = {}) {
    const c = this.cam;
    if (cam.z != null) c.z = Math.min(60, Math.max(1, cam.z));
    if (cam.x != null) c.x = cam.x;
    if (cam.y != null) c.y = cam.y;
    // pan bound: at z=1 the map is centered (no pan); the budget grows with z.
    const bound = (c.z - 1) * 1.05 + 0.02;
    c.x = Math.min(bound, Math.max(-bound, c.x));
    c.y = Math.min(bound, Math.max(-bound, c.y));
    this.gl.uniform1f(this.U.uCamZoom, c.z);
    this.gl.uniform2f(this.U.uCamPan, c.x, c.y);
    this._updateDensityMix();
    this._emit('camera', { z: c.z, x: c.x, y: c.y });
    if (!this.playing) this.draw();
    return this;
  }

  /**
   * Multiply zoom by `factor`, anchored at a client-space point so whatever
   * is under the cursor/pinch stays put.
   * @param {number} factor
   * @param {number} clientX  relative to the canvas
   * @param {number} clientY
   * @returns {FireMap} this
   */
  zoomAt(factor, clientX, clientY) {
    const r = this.canvas.getBoundingClientRect();
    const ndcX = ((clientX - r.left) / r.width) * 2 - 1;
    const ndcY = -(((clientY - r.top) / r.height) * 2 - 1);
    const c = this.cam;
    const z2 = Math.min(60, Math.max(1, c.z * factor));
    const k = z2 / c.z;
    return this.setCamera({
      z: z2,
      x: ndcX - (ndcX - c.x) * k,
      y: ndcY - (ndcY - c.y) * k,
    });
  }

  /**
   * Pan by a CSS-pixel delta (drag).
   * @param {number} dxPx @param {number} dyPx
   * @returns {FireMap} this
   */
  panBy(dxPx, dyPx) {
    const r = this.canvas.getBoundingClientRect();
    return this.setCamera({
      x: this.cam.x + (dxPx / r.width) * 2,
      y: this.cam.y - (dyPx / r.height) * 2,
    });
  }

  /** Reset to the full-country frame. @returns {FireMap} this */
  resetCamera() { return this.setCamera({ z: 1, x: 0, y: 0 }); }

  /* ---------------- picking (v3 console) ---------------- */

  /** Decode record i from the raw blob. @private */
  _record(i) {
    const u = this._u16;
    const o = i * 4;
    const w2 = u[o + 2], w3 = u[o + 3];
    return {
      index: i,
      qx: u[o], qy: u[o + 1],                  // quantized 0..65535 unit coords
      cls: w2 & 7,
      doy: w2 >> 3,
      state6: (w3 >> 1) & 63,
      region2: (w3 >> 7) & 3,
      cause2: (w3 >> 9) & 3,
      year: 1992 + ((w3 >> 11) & 31),
    };
  }

  /** CSR grid over CONUS (region 0) points; built once, ~5MB. @private */
  _buildPickGrid() {
    const G = 128;
    const u = this._u16, N = this.N;
    const cellOf = (i) => {
      const o = i * 4;
      const gx = Math.min(G - 1, (u[o] * G / 65536) | 0);
      const gy = Math.min(G - 1, (u[o + 1] * G / 65536) | 0);
      return gy * G + gx;
    };
    const counts = new Int32Array(G * G);
    for (let i = 0; i < N; i++) {
      if (((u[i * 4 + 3] >> 7) & 3) !== 0) continue;   // CONUS only
      counts[cellOf(i)]++;
    }
    const starts = new Int32Array(G * G + 1);
    for (let c = 0; c < G * G; c++) starts[c + 1] = starts[c] + counts[c];
    const items = new Int32Array(starts[G * G]);
    const cursor = starts.slice(0, G * G);
    for (let i = 0; i < N; i++) {
      if (((u[i * 4 + 3] >> 7) & 3) !== 0) continue;
      items[cursor[cellOf(i)]++] = i;
    }
    this._pickGrid = { G, starts, items };
  }

  /**
   * Nearest fire to a client-space point, CONUS only (insets are hidden at
   * pick-relevant zooms). Inverts camera + CONUS transforms, scans the grid
   * neighborhood, measures in CSS pixels.
   * @param {number} clientX @param {number} clientY
   * @param {number} [radiusPx=14] max hit distance in CSS pixels
   * @param {(rec: object) => boolean} [predicate]
   *   optional filter — return false to make a record unpickable (the console
   *   passes its active filter set so hidden points can't be picked).
   * @returns {?object} decoded record + {px, py} screen position, or null
   */
  pick(clientX, clientY, radiusPx = 14, predicate) {
    if (!this._pickGrid) this._buildPickGrid();
    const { G, starts, items } = this._pickGrid;
    const r = this.canvas.getBoundingClientRect();
    const cx = clientX - r.left, cy = clientY - r.top;
    const c = this.cam, t = this._conus;

    // screen px -> NDC -> pre-camera -> unit [0,1] -> quantized
    const toUnit = (px, py) => {
      const ndcX = (px / r.width) * 2 - 1;
      const ndcY = -((py / r.height) * 2 - 1);
      const qxN = (ndcX - c.x) / c.z;
      const qyN = (ndcY - c.y) / c.z;
      return [(qxN - t.ox) / t.sx, (qyN - t.oy) / t.sy];
    };
    // forward: quantized -> screen px (for exact px distances)
    const toPx = (qx, qy) => {
      const ndcX = ((qx / 65535) * t.sx + t.ox) * c.z + c.x;
      const ndcY = ((qy / 65535) * t.sy + t.oy) * c.z + c.y;
      return [((ndcX + 1) / 2) * r.width, ((1 - ndcY) / 2) * r.height];
    };

    const [ux, uy] = toUnit(cx, cy);
    // search radius in unit space (use the larger axis conversion)
    const uRad = Math.max(
      Math.abs((radiusPx / r.width) * 2 / (c.z * t.sx)),
      Math.abs((radiusPx / r.height) * 2 / (c.z * t.sy)),
    );
    const g0x = Math.max(0, Math.floor((ux - uRad) * G));
    const g1x = Math.min(G - 1, Math.floor((ux + uRad) * G));
    const g0y = Math.max(0, Math.floor((uy - uRad) * G));
    const g1y = Math.min(G - 1, Math.floor((uy + uRad) * G));
    if (g0x > G - 1 || g1x < 0 || g0y > G - 1 || g1y < 0) return null;

    let best = null, bestD2 = radiusPx * radiusPx;
    for (let gy = g0y; gy <= g1y; gy++) {
      for (let gx = g0x; gx <= g1x; gx++) {
        const cell = gy * G + gx;
        for (let k = starts[cell]; k < starts[cell + 1]; k++) {
          const i = items[k];
          const o = i * 4;
          const [px, py] = toPx(this._u16[o], this._u16[o + 1]);
          const dx = px - cx, dy = py - cy;
          const d2 = dx * dx + dy * dy;
          if (d2 >= bestD2) continue;
          const rec = this._record(i);
          if (predicate && !predicate(rec)) continue;
          rec.px = px; rec.py = py;
          bestD2 = d2; best = rec;
        }
      }
    }
    return best;
  }

  /* ---------------- modes ---------------- */

  /**
   * Switch scene. Uniforms-only — never re-uploads the VBO.
   * @param {('season'|'years'|'cause'|'drought'|'explore')} mode
   * @param {object} [opts] mode-specific options:
   *   season/drought: {day, sigma}
   *   years/drought:  {year}
   *   cause:          {lens: 0|1|2}
   *   drought:        {pdsi: {buffer, width, height} | ArrayBuffer, states}
   *   explore:        {yearMin,yearMax, causeMask, classMin,classMax,
   *                    monthMin,monthMax, monstersOnly, stateMask (BigInt|number[])}
   * @returns {FireMap} this
   */
  setMode(mode, opts = {}) {
    const { gl, U } = this;
    const ids = { season: 0, years: 1, cause: 2, drought: 3, explore: 4 };
    if (!(mode in ids)) throw new Error('unknown mode: ' + mode);
    this.mode = mode;
    this.modeId = ids[mode];
    gl.uniform1i(U.uMode, this.modeId);

    if (mode === 'season') {
      gl.uniform1f(U.uSigma, opts.sigma != null ? opts.sigma : 12.0);
      if (opts.day != null) this.setDay(opts.day);
    } else if (mode === 'years') {
      if (opts.year != null) this.setYear(opts.year);
    } else if (mode === 'cause') {
      gl.uniform1i(U.uLens, opts.lens | 0);
    } else if (mode === 'drought') {
      gl.uniform1f(U.uSigma, opts.sigma != null ? opts.sigma : 12.0);
      if (opts.pdsi) this._uploadPdsi(opts.pdsi);
      if (opts.year != null) this.setYear(opts.year);
    } else if (mode === 'explore') {
      this.setFilters(opts);
    }
    if (!this.playing) this.draw();
    return this;
  }

  /**
   * Set the cause lens (cause mode). 0 all · 1 human · 2 natural.
   * @param {0|1|2} lens
   * @returns {FireMap} this
   */
  setLens(lens) {
    this.gl.uniform1i(this.U.uLens, lens | 0);
    if (!this.playing) this.draw();
    return this;
  }

  /**
   * Apply explore-mode filters. All fields optional; omitted fields are left
   * unchanged. `stateMask` may be a BigInt (bit s => state6 s allowed), a
   * number[] of allowed state6 indices, or {lo, hi} uint32 pair.
   * @param {object} f
   * @returns {FireMap} this
   */
  setFilters(f = {}) {
    const { gl, U } = this;
    if (f.yearMin != null) gl.uniform1f(U.uYearMin, f.yearMin);
    if (f.yearMax != null) gl.uniform1f(U.uYearMax, f.yearMax);
    if (f.causeMask != null) gl.uniform1i(U.uCauseMask, f.causeMask & 0b111);
    if (f.classMin != null) gl.uniform1f(U.uClassMin, f.classMin);
    if (f.classMax != null) gl.uniform1f(U.uClassMax, f.classMax);
    if (f.monthMin != null) gl.uniform1f(U.uMonthMin, f.monthMin);
    if (f.monthMax != null) gl.uniform1f(U.uMonthMax, f.monthMax);
    if (f.monstersOnly != null) gl.uniform1i(U.uMonstersOnly, f.monstersOnly ? 1 : 0);
    if (f.stateMask != null) {
      const { lo, hi } = FireMap._stateMask(f.stateMask);
      gl.uniform1ui(U.uStateMaskLo, lo);
      gl.uniform1ui(U.uStateMaskHi, hi);
    }
    if (!this.playing) this.draw();
    return this;
  }

  /** Normalize a state mask into {lo, hi} uint32. @private */
  static _stateMask(mask) {
    let big;
    if (typeof mask === 'bigint') big = mask;
    else if (Array.isArray(mask)) {
      big = 0n;
      for (const s of mask) big |= (1n << BigInt(s));
    } else if (mask && typeof mask === 'object') {
      return { lo: mask.lo >>> 0, hi: mask.hi >>> 0 };
    } else {
      big = BigInt(mask >>> 0);
    }
    const lo = Number(big & 0xffffffffn) >>> 0;
    const hi = Number((big >> 32n) & 0xffffffffn) >>> 0;
    return { lo, hi };
  }

  /**
   * Upload the PDSI grid as an R8 texture for drought mode. Width must be
   * 29*12 = 348 (year-months 1992..2020), height = stateCount, row order
   * matching header.states.
   * @param {(ArrayBuffer|Uint8Array|{buffer:ArrayBuffer|Uint8Array,width:number,height:number})} pdsi
   * @private
   */
  _uploadPdsi(pdsi) {
    const { gl, U } = this;
    let bytes, width, height;
    if (pdsi && pdsi.buffer && pdsi.width) {
      bytes = pdsi.buffer instanceof Uint8Array ? pdsi.buffer : new Uint8Array(pdsi.buffer);
      width = pdsi.width; height = pdsi.height;
    } else {
      bytes = pdsi instanceof Uint8Array ? pdsi : new Uint8Array(pdsi);
      width = 29 * 12;
      height = bytes.length / width;
    }
    if (!this.pdsiTex) this.pdsiTex = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.pdsiTex);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R8, width, height, 0, gl.RED, gl.UNSIGNED_BYTE, bytes);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.uniform1i(U.uPdsi, 0);
    gl.uniform1i(U.uHasPdsi, 1);
  }

  /* ---------------- time controls ---------------- */

  /**
   * Set the composite day (season / drought pulse). Redraws when paused.
   * @param {number} day 1..366
   * @returns {FireMap} this
   */
  setDay(day) {
    this.day = ((day - 1) % 366 + 366) % 366 + 1;
    this.gl.uniform1f(this.U.uDay, this.day);
    if (!this.playing) this.draw();
    return this;
  }

  /**
   * Set the sweep / drought year.
   * @param {number} year 1992..2020
   * @returns {FireMap} this
   */
  setYear(year) {
    this.year = year;
    this.gl.uniform1f(this.U.uYear, year);
    if (!this.playing) this.draw();
    return this;
  }

  /**
   * Set playback speed multiplier.
   * @param {number} x
   * @returns {FireMap} this
   */
  setSpeed(x) { this.speed = x; return this; }

  /**
   * Start autoplay. No-op under reduced motion (stepping API stays usable).
   * In season/drought playback advances the day; in years, the year sweeps
   * 1992→2020 and loops.
   * @returns {FireMap} this
   */
  play() {
    if (this.reduced) return this;       // never autoplay under reduced motion
    if (this.playing) return this;
    this.playing = true;
    this._last = null;
    this._raf = requestAnimationFrame(this._tick.bind(this));
    return this;
  }

  /** Pause autoplay. @returns {FireMap} this */
  pause() {
    this.playing = false;
    if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; }
    return this;
  }

  /* ---------------- events ---------------- */

  /**
   * Subscribe to an engine event.
   * @param {('frame'|'degraded')} event
   *   `'frame'` payload {day:number, year:number, fps:number} (per rendered frame)
   *   `'degraded'` payload {classFloor:number} (fps guard raised the floor)
   * @param {Function} cb
   * @returns {FireMap} this
   */
  on(event, cb) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(cb);
    return this;
  }

  /** @private */
  _emit(event, payload) {
    const ls = this._listeners[event];
    if (ls) for (const cb of ls) cb(payload);
  }

  /* ---------------- render ---------------- */

  /** Issue one draw of the current uniform state. */
  draw() {
    const { gl } = this;
    const mix = this._dMix;

    if (mix > 0.005 && this._fbo) {
      // ---- pass 1: accumulate big soft kernels into the half-res field ----
      gl.bindFramebuffer(gl.FRAMEBUFFER, this._fbo);
      gl.viewport(0, 0, this._fboW, this._fboH);
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);
      gl.uniform1f(this.U.uPointScale, this._pointScale * 2.5);
      gl.uniform1f(this.U.uExposure, this._exposure * 0.12);
      gl.drawArrays(gl.POINTS, 0, this.N);
      gl.uniform1f(this.U.uPointScale, this._pointScale);
      gl.uniform1f(this.U.uExposure, this._exposure);

      // ---- pass 2: colormap the field onto the screen ----
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, this.canvas.width, this.canvas.height);
      gl.disable(gl.BLEND);
      gl.useProgram(this.dProg);
      gl.uniform1f(this.DU.uMix, mix);
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, this._fboTex);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.useProgram(this.prog);

      // ---- pass 3: points re-emerge as the field fades ----
      if (mix < 0.995) {
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.ONE, gl.ONE);
        gl.uniform1f(this.U.uExposure, this._exposure * (1 - mix));
        gl.drawArrays(gl.POINTS, 0, this.N);
        gl.uniform1f(this.U.uExposure, this._exposure);
      }
    } else {
      gl.clearColor(0.027, 0.024, 0.016, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);              // additive glow (hero)
      gl.drawArrays(gl.POINTS, 0, this.N);
    }
    this._emit('frame', { day: this.day, year: this.year, fps: this.fps });
  }

  /** @private rAF loop */
  _tick(ts) {
    if (!this.playing) return;
    if (this._last == null) this._last = ts;
    const dt = (ts - this._last) / 1000;
    this._last = ts;

    if (this.mode === 'years') {
      // sweep years across the same seconds-per-year cadence; loop.
      const span = 2020 - 1992;
      this.year += dt * (span / this.SECS_PER_YEAR) * this.speed;
      if (this.year > 2020) this.year = 1992;
      this.gl.uniform1f(this.U.uYear, this.year);
    } else {
      this.day += dt * (366 / this.SECS_PER_YEAR) * this.speed;
      if (this.day > 366) this.day -= 366;
      this.gl.uniform1f(this.U.uDay, this.day);
    }

    // fps sampling for the guard.
    if (dt > 0) {
      const inst = 1 / dt;
      this._fpsSamples.push(inst);
      if (this._fpsSamples.length > 30) this._fpsSamples.shift();
      this.fps = this._fpsSamples.reduce((a, b) => a + b, 0) / this._fpsSamples.length;
      this._guard(ts);
    }

    this.draw();
    this._raf = requestAnimationFrame(this._tick.bind(this));
  }

  /**
   * fps guard (spec §8): sustained <30fps for 3s raises the class-drop
   * threshold uniform (culls A/B first) and emits 'degraded'.
   * @private
   */
  _guard(ts) {
    if (this.fps < 30) {
      if (this._lowSince == null) this._lowSince = ts;
      else if (ts - this._lowSince >= 3000 && this.classFloor < 2) {
        this.classFloor += 1;    // 1 drops A, 2 drops A+B
        this.gl.uniform1f(this.U.uClassFloor, this.classFloor);
        this._lowSince = ts;     // re-arm; escalate again only after another 3s
        this._fpsSamples.length = 0;
        this._emit('degraded', { classFloor: this.classFloor });
      }
    } else {
      this._lowSince = null;
    }
  }

  /** Convenience: current composite month index 0..11. */
  get month() { return monthOfDay(this.day); }

  /** Tear down: stop rAF, delete GL resources, drop listeners. */
  destroy() {
    this.pause();
    removeEventListener('resize', this._onResize);
    const { gl } = this;
    if (this.vboLo) gl.deleteBuffer(this.vboLo);
    if (this.vboHi) gl.deleteBuffer(this.vboHi);
    if (this.pdsiTex) gl.deleteTexture(this.pdsiTex);
    if (this.prog) gl.deleteProgram(this.prog);
    if (this._fboTex) gl.deleteTexture(this._fboTex);
    if (this._fbo) gl.deleteFramebuffer(this._fbo);
    if (this.dProg) gl.deleteProgram(this.dProg);
    this._u16 = null;
    this._pickGrid = null;
    this._listeners = { frame: [], degraded: [] };
  }

  /* ================================================================ */
  /* Monsters overlay (separate 2D canvas)                            */
  /* ================================================================ */

  /**
   * Build the named-fires overlay on a 2D canvas — the 4,783 Class-G fires
   * with hit-testing, keyboard roving tabindex, and a name/year/acres tooltip.
   * Independent of the WebGL scene; draws sized rings sized by relative acreage.
   *
   * Record layout (monsters.bin, 16 bytes/fire — verified against the real
   * blob): f32 lon, f32 lat, f32 acres, uint16 meta (year5<<6|cause2<<4|
   * region2<<2), uint16 nameIdx.
   *
   * @param {HTMLCanvasElement} canvas   a 2D canvas
   * @param {ArrayBuffer} blob           monsters.bin contents
   * @param {string[]} names             monsters-names.json (nameIdx → display)
   * @param {object} [opts]
   * @param {object} [opts.header]       points-v2.json (for region bounds; else defaults)
   * @param {number} [opts.topN=100]     how many of the largest are keyboard-focusable
   * @param {boolean} [opts.reducedMotion]
   * @param {(fire:object)=>void} [opts.onSelect] called on Enter/click with the fire record
   * @param {string} [opts.ariaLabel]
   * @returns {MonstersOverlay}
   */
  static monsters(canvas, blob, names, opts = {}) {
    return new MonstersOverlay(canvas, blob, names, opts);
  }
}

/* ------------------------------------------------------------------ */
/* MonstersOverlay                                                     */
/* ------------------------------------------------------------------ */

/**
 * 2D-canvas overlay of named Class-G fires. Constructed via
 * {@link FireMap.monsters}. Pointer + keyboard explorable; emits selection
 * via `opts.onSelect`. Public methods: resize(), draw(), setTooltip(),
 * focusRank(n), destroy().
 */
class MonstersOverlay {
  /** @private Use FireMap.monsters. */
  constructor(canvas, blob, names, opts = {}) {
    this.canvas = canvas;
    this.names = names || [];
    this.opts = opts;
    this.ctx = canvas.getContext('2d');
    this.topN = opts.topN || 100;
    this.reduced = opts.reducedMotion != null
      ? opts.reducedMotion
      : (typeof matchMedia === 'function' &&
         matchMedia('(prefers-reduced-motion: reduce)').matches);

    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', opts.ariaLabel ||
      'Named large wildfires, sized by acreage; focusable for details');

    const regions = (opts.header && opts.header.regions) || [
      { name: 'CONUS', bounds: [-125, -66, 24, 50] },
      { name: 'AK', bounds: [-170, -129, 54, 72] },
      { name: 'HI', bounds: [-161, -154, 18.5, 22.8] },
    ];
    this.regions = regions;

    // ---- decode ----
    const dv = new DataView(blob);
    const n = (blob.byteLength / 16) | 0;
    const fires = new Array(n);
    let maxAcres = 1;
    for (let i = 0; i < n; i++) {
      const o = i * 16;
      const lon = dv.getFloat32(o, true);
      const lat = dv.getFloat32(o + 4, true);
      const acres = dv.getFloat32(o + 8, true);
      const meta = dv.getUint16(o + 12, true);
      const nameIdx = dv.getUint16(o + 14, true);
      const region2 = (meta >> 2) & 3;
      const cause2 = (meta >> 4) & 3;
      const year5 = (meta >> 6) & 0x1f;
      fires[i] = {
        lon, lat, acres,
        year: 1992 + year5,
        cause: cause2,          // 0 human · 1 natural · 2 undetermined
        region: region2,
        name: this.names[nameIdx] || 'Unnamed fire',
        nameIdx,
      };
      if (acres > maxAcres) maxAcres = acres;
    }
    this.maxAcres = maxAcres;
    // rank by acreage descending; the top-N get roving tabindex.
    this.fires = fires;
    this.ranked = fires.slice().sort((a, b) => b.acres - a.acres);
    this.ranked.forEach((f, i) => { f.rank = i + 1; });

    // ---- interaction state ----
    this.focusIdx = 0;          // index into `ranked` (top-N focusable)
    this.hoverFire = null;
    this._pts = [];             // screen-space cache {x,y,r,fire}

    this._bindEvents();
    this._onResize = () => this.resize();
    addEventListener('resize', this._onResize);
    this.resize();
  }

  /** Project a fire's lon/lat to screen px within its region rect. @private */
  _project(fire, W, H) {
    const r = this.regions[fire.region] || this.regions[0];
    const [lonMin, lonMax, latMin, latMax] = r.bounds;
    // Main CONUS rect fills the canvas; insets bottom-left (match WebGL layout).
    const midLat = (latMin + latMax) / 2;
    const lonSpan = (lonMax - lonMin) * Math.cos(midLat * Math.PI / 180);
    const latSpan = latMax - latMin;
    const u = (fire.lon - lonMin) / (lonMax - lonMin);
    const v = (fire.lat - latMin) / (latMax - latMin);
    if (fire.region === 0) {
      // aspect-correct fill of the canvas
      const dataAspect = lonSpan / latSpan;
      const viewAspect = W / H;
      let dw = W, dh = H, ox = 0, oy = 0;
      if (viewAspect > dataAspect) { dw = H * dataAspect; ox = (W - dw) / 2; }
      else { dh = W / dataAspect; oy = (H - dh) / 2; }
      return { x: ox + u * dw, y: oy + (1 - v) * dh };
    }
    // insets: small boxes bottom-left, AK then HI
    const boxW = fire.region === 1 ? W * 0.22 : W * 0.10;
    const boxH = boxW * (latSpan / lonSpan) * (W / H);
    const baseX = fire.region === 1 ? W * 0.015 : W * 0.015 + W * 0.22 + W * 0.015;
    const baseY = H - boxH - H * 0.04;
    return { x: baseX + u * boxW, y: baseY + (1 - v) * boxH };
  }

  /** Recompute backing size and screen-space point cache. */
  resize() {
    const { canvas } = this;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const W = canvas.clientWidth || canvas.width || innerWidth;
    const H = canvas.clientHeight || canvas.height || innerHeight;
    canvas.width = Math.max(1, Math.floor(W * dpr));
    canvas.height = Math.max(1, Math.floor(H * dpr));
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._W = W; this._H = H;
    this._rebuild();
    this.draw();
  }

  /** Rebuild the screen-space hit cache (ranked so larger draw on top). @private */
  _rebuild() {
    const W = this._W, H = this._H;
    this._pts = this.ranked.map((fire) => {
      const p = this._project(fire, W, H);
      // ring radius by sqrt(acreage) so AREA tracks acreage; 3..26 px.
      const rel = Math.sqrt(fire.acres / this.maxAcres);
      const r = 3 + rel * 23;
      return { x: p.x, y: p.y, r, fire };
    });
  }

  /**
   * Draw all rings. Larger fires drawn first so smaller ones layer on top;
   * hovered/focused fire gets a highlight ring.
   */
  draw() {
    const ctx = this.ctx, W = this._W, H = this._H;
    ctx.clearRect(0, 0, W, H);
    // draw smallest-last for legibility (ranked is largest-first).
    for (let i = this._pts.length - 1; i >= 0; i--) {
      const p = this._pts[i];
      const f = p.fire;
      // human warm, natural cool, undetermined neutral — subtle hue cue.
      const hue = f.cause === 1 ? '#7dd3fc' : f.cause === 0 ? '#fb923c' : '#d6bc8a';
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.strokeStyle = hue;
      ctx.globalAlpha = 0.55;
      ctx.lineWidth = 1.25;
      ctx.stroke();
      ctx.globalAlpha = 0.12;
      ctx.fillStyle = hue;
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    // highlight active (hover takes precedence over keyboard focus)
    const active = this.hoverFire
      ? this._pts.find((p) => p.fire === this.hoverFire)
      : this._pts.find((p) => p.fire === this.ranked[this.focusIdx]);
    if (active) {
      ctx.beginPath();
      ctx.arc(active.x, active.y, active.r + 3, 0, Math.PI * 2);
      ctx.strokeStyle = '#fff7ed';
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }

  /** @private hit-test at screen px; returns nearest fire within its radius. */
  _hit(x, y) {
    let best = null, bestD = Infinity;
    for (const p of this._pts) {
      const dx = x - p.x, dy = y - p.y;
      const d = dx * dx + dy * dy;
      const rr = (p.r + 3) * (p.r + 3);
      if (d <= rr && d < bestD) { bestD = d; best = p.fire; }
    }
    return best;
  }

  /** @private wire pointer + keyboard interaction. */
  _bindEvents() {
    const canvas = this.canvas;
    canvas.tabIndex = 0;         // container focusable; roving handled internally

    this._onMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      const hit = this._hit(e.clientX - rect.left, e.clientY - rect.top);
      if (hit !== this.hoverFire) {
        this.hoverFire = hit;
        canvas.style.cursor = hit ? 'pointer' : 'default';
        this.setTooltip(hit, e.clientX, e.clientY);
        this.draw();
      } else if (hit) {
        this.setTooltip(hit, e.clientX, e.clientY);
      }
    };
    this._onLeave = () => {
      this.hoverFire = null; this.setTooltip(null); this.draw();
    };
    this._onClick = (e) => {
      const rect = canvas.getBoundingClientRect();
      const hit = this._hit(e.clientX - rect.left, e.clientY - rect.top);
      if (hit && this.opts.onSelect) this.opts.onSelect(hit);
    };
    // roving tabindex over top-N: arrows move focus, Enter selects.
    this._onKey = (e) => {
      const N = Math.min(this.topN, this.ranked.length);
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        this.focusIdx = (this.focusIdx + 1) % N; this._focusChanged(); e.preventDefault();
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        this.focusIdx = (this.focusIdx - 1 + N) % N; this._focusChanged(); e.preventDefault();
      } else if (e.key === 'Home') {
        this.focusIdx = 0; this._focusChanged(); e.preventDefault();
      } else if (e.key === 'End') {
        this.focusIdx = N - 1; this._focusChanged(); e.preventDefault();
      } else if (e.key === 'Enter' || e.key === ' ') {
        const f = this.ranked[this.focusIdx];
        if (f && this.opts.onSelect) this.opts.onSelect(f);
        e.preventDefault();
      }
    };
    canvas.addEventListener('mousemove', this._onMove);
    canvas.addEventListener('mouseleave', this._onLeave);
    canvas.addEventListener('click', this._onClick);
    canvas.addEventListener('keydown', this._onKey);
  }

  /** @private focus moved via keyboard: update aria-label, tooltip, redraw. */
  _focusChanged() {
    const f = this.ranked[this.focusIdx];
    if (!f) return;
    const p = this._pts.find((q) => q.fire === f);
    this.canvas.setAttribute('aria-label',
      `${f.name}, ${f.year}, ${Math.round(f.acres).toLocaleString()} acres. ` +
      `Rank ${f.rank} of ${this.ranked.length}. Arrow keys to browse, Enter for detail.`);
    if (p) {
      const rect = this.canvas.getBoundingClientRect();
      this.setTooltip(f, rect.left + p.x, rect.top + p.y);
    }
    this.draw();
  }

  /**
   * Programmatically focus the fire at rank n (1-based). Useful for the
   * "top-5 name callouts" beats in Act 3.
   * @param {number} n 1-based rank
   * @returns {MonstersOverlay} this
   */
  focusRank(n) {
    this.focusIdx = Math.max(0, Math.min(this.ranked.length - 1, n - 1));
    this._focusChanged();
    return this;
  }

  /**
   * Render (or clear) the tooltip. Default implementation manages a floating
   * `<div>` appended to document.body; override by passing opts.onTooltip, or
   * subclass. Pass a falsy fire to hide.
   * @param {object|null} fire
   * @param {number} [clientX]
   * @param {number} [clientY]
   */
  setTooltip(fire, clientX, clientY) {
    if (this.opts.onTooltip) { this.opts.onTooltip(fire, clientX, clientY); return; }
    if (!this._tip) {
      this._tip = document.createElement('div');
      this._tip.setAttribute('role', 'tooltip');
      Object.assign(this._tip.style, {
        position: 'fixed', pointerEvents: 'none', zIndex: 50,
        background: 'rgba(20,17,13,0.94)', color: '#ece8e2',
        border: '1px solid #332d24', borderRadius: '8px',
        padding: '8px 11px', font: '13px Inter, system-ui, sans-serif',
        maxWidth: '240px', transform: 'translate(-50%, calc(-100% - 12px))',
        opacity: '0', transition: 'opacity 0.12s',
      });
      document.body.appendChild(this._tip);
      // fixed-position tip goes stale the moment the page scrolls (it would
      // float over unrelated content below the console) — hide on scroll.
      this._tipScrollHide = () => { if (this._tip) this._tip.style.opacity = '0'; };
      addEventListener('scroll', this._tipScrollHide, { passive: true });
    }
    if (!fire) { this._tip.style.opacity = '0'; return; }
    const causeName = fire.cause === 1 ? 'Natural'
      : fire.cause === 0 ? 'Human' : 'Undetermined';
    this._tip.innerHTML =
      `<strong>${fire.name}</strong><br>` +
      `<span style="color:#a89f93">${fire.year} · ${causeName}</span><br>` +
      `${Math.round(fire.acres).toLocaleString()} acres`;
    this._tip.style.left = (clientX || 0) + 'px';
    this._tip.style.top = (clientY || 0) + 'px';
    this._tip.style.opacity = '1';
  }

  /** Tear down: remove listeners and the tooltip node. */
  destroy() {
    removeEventListener('resize', this._onResize);
    const c = this.canvas;
    c.removeEventListener('mousemove', this._onMove);
    c.removeEventListener('mouseleave', this._onLeave);
    c.removeEventListener('click', this._onClick);
    c.removeEventListener('keydown', this._onKey);
    if (this._tipScrollHide) removeEventListener('scroll', this._tipScrollHide);
    if (this._tip && this._tip.parentNode) this._tip.parentNode.removeChild(this._tip);
    this._tip = null;
  }
}

export { FireMap, MonstersOverlay };
export default FireMap;
