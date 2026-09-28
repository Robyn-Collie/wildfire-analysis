/**
 * console.js — the v3 console state machine.
 *
 * Owns the declarative chapter presets, the live filter mirror, the timeline
 * mode, and the pick predicate. It is UI-agnostic: Console.astro's island wires
 * DOM events to these methods and subscribes to the callbacks. Everything that
 * changes the engine funnels through here so the timeline readout, the pick
 * predicate, and the engine uniforms never drift out of sync.
 *
 * Year filtering note (verified against firemap.js VERT source, line ~171): the
 * shader compares the point's FULL fire year (1992 + year5) against uYearMin/
 * uYearMax. So filters carry full years 1992..2020 — NOT the 0..28 offsets that
 * explore.astro happens to pass. We match the shader, and the pick predicate
 * uses the same full-year comparison so picking and rendering agree.
 *
 * @module console
 */

export const YEAR_MIN = 1992;
export const YEAR_MAX = 2020;

/** class letter for a 0..6 index. */
export const CLASS_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
/** acreage meaning per class (for the filter legend). */
export const CLASS_MEANINGS = [
  'A <0.25', 'B 0.26–9', 'C 10–99', 'D 100–299',
  'E 300–999', 'F 1,000–4,999', 'G 5,000+',
];
export const MONTH_NAMES = [
  'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
  'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER',
];
export const MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];
// first day-of-year of each month (non-leap), for doy -> month + date.
const MONTH_START = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/** month index 0..11 from day-of-year 1..366 (non-leap table). */
export function monthOfDoy(doy) {
  for (let i = 11; i >= 0; i--) if (doy >= MONTH_START[i]) return i;
  return 0;
}

/** "Aug 12" style date from a day-of-year (non-leap month table). */
export function doyToDate(doy) {
  const m = monthOfDoy(doy);
  const day = Math.max(1, Math.floor(doy) - MONTH_START[m] + 1);
  return `${MONTH_ABBR[m]} ${day}`;
}

/** Default (all-open) filter mirror. Years are FULL years. */
export function defaultFilters() {
  return {
    yearMin: YEAR_MIN, yearMax: YEAR_MAX,
    causeMask: 0b111,               // bit0 Human · bit1 Natural · bit2 Undetermined
    classMin: 0, classMax: 6,
    monthMin: 1, monthMax: 12,
    monstersOnly: false,
    stateMask: null,                // Set<number> of state6 indices, null = all
  };
}

/**
 * Chapter presets. Each is a full declarative console state. Captions carry
 * verified numbers + STAT comments — do not reword the FIGURES. Wording was
 * factualized 2026-07-13 per the author (no dramatic naming). `timeline` selects DAY or YEAR mode + start position.
 * Under reduced motion the console forces playing:false (see applyChapter).
 */
export const CHAPTERS = [
  {
    id: 'year-of-fire',
    label: 'Season cycle',
    mode: 'season',
    density: false,
    timeline: { kind: 'day', day: 1 },
    playing: true,
    filters: null,                  // season mode ignores explore filters
    monsters: false,
    caption:
      'One million ignition points, 1992–2020, looping day by day. ' +
      'Southeast fires peak in spring; western fires peak in mid-summer. ' +
      '<!-- STAT: points-v2.json meta (1,020,005 points) -->',
    aria: 'Season cycle: one year of ignitions looping day by day across the country.',
  },
  {
    id: 'three-decades',
    label: 'Year by year',
    mode: 'years',
    density: false,
    timeline: { kind: 'year', year: YEAR_MIN },
    playing: true,
    filters: null,
    monsters: false,
    caption:
      'Acres burned per year, swept 1992–2020. The lowest-acre year rose ' +
      '2.35× between eras: 1.15M acres before 2000, 2.69M after. ' +
      '<!-- STAT: trend_stats.era_comparison_nifc_macres.floor_shift.ratio (2.35) -->',
    aria: 'Year by year: acres burned per year swept from 1992 to 2020.',
  },
  {
    id: 'two-kinds',
    label: 'By cause',
    mode: 'cause',
    density: false,
    timeline: { kind: 'day', day: 200 },
    playing: false,
    lens: 0,
    filters: null,
    monsters: false,
    caption:
      'Human-caused fires cluster in the East and in spring and fall; ' +
      'lightning fires cluster in the West in mid-summer. ' +
      '<!-- STAT: causes_classes.json cause_classification -->',
    aria: 'By cause: human versus lightning ignitions, paused at day 200.',
  },
  {
    id: 'the-monsters',
    label: 'Class G (5,000+ ac)',
    mode: 'explore',
    density: false,
    timeline: { kind: 'day', day: 200 },
    playing: false,
    monsters: true,
    filters: () => {
      const f = defaultFilters();
      f.monstersOnly = true;
      return f;
    },
    caption:
      '4,783 class-G fires (5,000+ acres) — 0.2% of fires, ~75% of the acres. ' +
      'Each ring is named in the fire record; click one for details. ' +
      '<!-- STAT: causes_classes.json size_class[G] (4,783; 135,131,873 ac / 180,048,736 = 75%) -->',
    aria: 'Class G: 4,783 fires of 5,000 acres or more, each a named ring you can click.',
  },
  {
    id: 'the-thirst',
    label: 'Drought overlay',
    mode: 'drought',
    density: false,
    needsPdsi: true,
    timeline: { kind: 'day', day: 1 },
    year: 2020,
    playing: true,
    filters: null,
    monsters: false,
    caption:
      'Fires tinted by state-month drought (PDSI): red = dry, teal = wet. ' +
      '2020 was one of only three years above ten million acres. ' +
      '<!-- STAT: trend_stats.ten_million_club.years (2015, 2017, 2020) -->',
    aria: 'Drought overlay: 2020 fires tinted red where drought was severe, teal where wet.',
  },
  {
    id: 'explore-freely',
    label: 'Explore',
    mode: 'explore',
    density: true,
    timeline: { kind: 'day', day: 218 },
    playing: false,
    openFilters: true,
    monsters: false,
    filters: () => defaultFilters(),
    caption:
      'Free exploration. Filter by year, cause, size, month, and state; ' +
      'zoom in to isolate a single fire and click it for details.',
    aria: 'Explore freely: filter the full record and pick individual fires.',
  },
];

/**
 * The console controller. Construct with the engine and a set of UI callbacks;
 * call applyChapter / setFilters / timeline methods from the DOM layer.
 */
export class Console {
  /**
   * @param {import('../engine/firemap.js').FireMap} engine
   * @param {object} header  points-v2.json (for states, meta)
   * @param {object} annual  national_annual.json (for year-mode acres readout)
   * @param {object} [opts]
   * @param {boolean} [opts.reducedMotion]
   * @param {(state:object) => void} [opts.onChapter]   chapter applied
   * @param {(readout:object) => void} [opts.onReadout] timeline readout changed
   * @param {(filters:object) => void} [opts.onFilters] filter mirror changed
   */
  constructor(engine, header, annual, opts = {}) {
    this.engine = engine;
    this.header = header;
    this.states = header.states || [];
    this.reduced = !!opts.reducedMotion;
    this.cb = {
      onChapter: opts.onChapter || (() => {}),
      onReadout: opts.onReadout || (() => {}),
      onFilters: opts.onFilters || (() => {}),
    };

    // year -> acres, from national_annual.fod[]  (STAT: national_annual.json fod[year].acres)
    this.acresByYear = new Map();
    for (const r of (annual && annual.fod) || []) this.acresByYear.set(r.year, r.acres);

    this.filters = defaultFilters();
    this.timeline = { kind: 'day', day: 1, year: YEAR_MIN };
    this.chapter = null;

    // the engine emits 'frame' every rendered frame (playing or a paused
    // redraw). That is the ONE source of truth for the readout — we never run a
    // parallel clock. It carries {day, year, fps}.
    engine.on('frame', ({ day, year }) => {
      if (this.timeline.kind === 'year') this.timeline.year = year;
      else this.timeline.day = day;
      this.cb.onReadout(this.readout());
    });
  }

  /* ---------------- chapters ---------------- */

  /**
   * Apply a chapter preset by id. Sequences engine calls, timeline reconfig,
   * filter mirror, and fires onChapter with the resolved state.
   * @param {string} id
   */
  applyChapter(id) {
    const ch = CHAPTERS.find((c) => c.id === id);
    if (!ch) return;
    this.chapter = ch;
    const { engine } = this;

    engine.pause();                       // stop any prior loop before reconfig

    // filters first (explore/monsters modes read them)
    if (ch.filters) {
      this.filters = ch.filters();
      this._pushFilters();
    }

    // mode
    if (ch.mode === 'season') {
      engine.setMode('season', { day: ch.timeline.day });
    } else if (ch.mode === 'years') {
      engine.setMode('years', { year: ch.timeline.year });
    } else if (ch.mode === 'cause') {
      engine.setMode('cause', { lens: ch.lens || 0 });
      if (ch.timeline.day != null) engine.setDay(ch.timeline.day);
    } else if (ch.mode === 'drought') {
      // pdsi upload is handled by the caller (lazy fetch) before applyChapter,
      // via setDroughtGrid(); here we just select the mode + year.
      engine.setMode('drought', { year: ch.year != null ? ch.year : 2020 });
      if (ch.timeline.day != null) engine.setDay(ch.timeline.day);
    } else if (ch.mode === 'explore') {
      engine.setMode('explore', this._filterUniforms());
      if (ch.timeline.day != null) engine.setDay(ch.timeline.day);
    }

    engine.setDensity(!!ch.density);

    // timeline mode
    this.timeline = {
      kind: ch.timeline.kind,
      day: ch.timeline.day != null ? ch.timeline.day : this.timeline.day,
      year: ch.year != null ? ch.year
        : (ch.timeline.year != null ? ch.timeline.year : this.timeline.year),
    };

    // playback — reduced motion never autoplays.
    const wantPlay = ch.playing && !this.reduced;
    if (wantPlay) engine.play();
    else engine.pause();

    engine.canvas.setAttribute('aria-label', ch.aria);

    this.cb.onChapter({
      chapter: ch,
      timeline: this.timeline,
      playing: wantPlay,
      openFilters: !!ch.openFilters,
      showMonsters: !!ch.monsters,
    });
    this.cb.onReadout(this.readout());
    this.cb.onFilters(this.filters);
  }

  /* ---------------- filters ---------------- */

  /** Merge a partial filter change, switch to explore mode, push to engine. */
  updateFilters(partial) {
    Object.assign(this.filters, partial);
    if (!this.engine || this.engine.mode !== 'explore') {
      this.engine.setMode('explore', this._filterUniforms());
      this.timeline = { ...this.timeline, kind: 'day' };
    } else {
      this._pushFilters();
    }
    this.cb.onFilters(this.filters);
    this.cb.onReadout(this.readout());
  }

  /** Reset filters to all-open (stays in explore mode). */
  resetFilters() {
    this.filters = defaultFilters();
    this._pushFilters();
    this.cb.onFilters(this.filters);
  }

  /** Count of non-default filter facets, for the badge. */
  activeFilterCount() {
    const f = this.filters, d = defaultFilters();
    let n = 0;
    if (f.yearMin !== d.yearMin || f.yearMax !== d.yearMax) n++;
    if (f.causeMask !== d.causeMask) n++;
    if (f.classMin !== d.classMin || f.classMax !== d.classMax) n++;
    if (f.monthMin !== d.monthMin || f.monthMax !== d.monthMax) n++;
    if (f.monstersOnly) n++;
    if (f.stateMask && f.stateMask.size) n++;
    return n;
  }

  /** @private translate the filter mirror into engine.setFilters() uniforms. */
  _filterUniforms() {
    const f = this.filters;
    const stateArr = (f.stateMask && f.stateMask.size) ? [...f.stateMask] : null;
    return {
      yearMin: f.yearMin,               // FULL years — matches the shader
      yearMax: f.yearMax,
      causeMask: f.causeMask,
      classMin: f.classMin,
      classMax: f.classMax,
      monthMin: f.monthMin,
      monthMax: f.monthMax,
      monstersOnly: f.monstersOnly,
      // an empty number[] would forbid every state; send a full BigInt for "all".
      stateMask: stateArr ? stateArr : (1n << BigInt(this.states.length)) - 1n,
    };
  }

  /** @private */
  _pushFilters() { this.engine.setFilters(this._filterUniforms()); }

  /**
   * Predicate mirroring the ACTIVE explore filters, for engine.pick(). Only
   * meaningful in explore mode (other modes show all CONUS points, so any pick
   * is valid). Returns true when the record passes every active filter.
   */
  pickPredicate() {
    if (this.engine.mode !== 'explore') return null;   // pick anything visible
    const f = this.filters;
    return (rec) => {
      if (rec.year < f.yearMin || rec.year > f.yearMax) return false;
      if ((f.causeMask & (1 << rec.cause2)) === 0) return false;
      if (rec.cls < f.classMin || rec.cls > f.classMax) return false;
      const m = monthOfDoy(rec.doy) + 1;
      if (m < f.monthMin || m > f.monthMax) return false;
      if (f.monstersOnly && rec.cls < 6) return false;
      if (f.stateMask && f.stateMask.size && !f.stateMask.has(rec.state6)) return false;
      return true;
    };
  }

  /* ---------------- timeline ---------------- */

  play() {
    if (this.reduced) return;             // no autoplay under reduced motion
    this.engine.play();
    this.cb.onReadout(this.readout());
  }

  pause() {
    this.engine.pause();
    this.cb.onReadout(this.readout());
  }

  togglePlay() {
    if (this.engine.playing) this.pause();
    else this.play();
    return this.engine.playing;
  }

  setSpeed(x) { this.engine.setSpeed(x); }

  /** Scrub to a normalized track position 0..1 (works while paused too). */
  scrubTo(t) {
    t = Math.min(1, Math.max(0, t));
    if (this.timeline.kind === 'year') {
      const y = Math.round(YEAR_MIN + t * (YEAR_MAX - YEAR_MIN));
      this.timeline.year = y;
      this.engine.setYear(y);
    } else {
      const d = Math.max(1, Math.min(366, Math.round(1 + t * 365)));
      this.timeline.day = d;
      this.engine.setDay(d);
    }
    // when paused, setDay/setYear already redrew and emitted 'frame'; when
    // playing, the running loop keeps emitting — either way onReadout fires.
    if (!this.engine.playing) this.cb.onReadout(this.readout());
  }

  /** Step the timeline by +/- one unit (keyboard arrows). */
  step(dir) {
    if (this.timeline.kind === 'year') {
      const y = Math.max(YEAR_MIN, Math.min(YEAR_MAX, Math.round(this.timeline.year) + dir));
      this.timeline.year = y;
      this.engine.setYear(y);
    } else {
      const d = Math.max(1, Math.min(366, Math.round(this.timeline.day) + dir));
      this.timeline.day = d;
      this.engine.setDay(d);
    }
    if (!this.engine.playing) this.cb.onReadout(this.readout());
  }

  /** Jump to track start/end (Home/End). */
  seekEnd(which) { this.scrubTo(which === 'home' ? 0 : 1); }

  /**
   * Current readout: {kind, t (0..1), big, aria}. `big` is the mono headline
   * ("AUGUST · day 218" or "2011 · 9.7M acres burned"). Derived from the same
   * timeline values the 'frame' event feeds.
   */
  readout() {
    if (this.timeline.kind === 'year') {
      const y = Math.round(this.timeline.year);
      const acres = this.acresByYear.get(y);
      const t = (y - YEAR_MIN) / (YEAR_MAX - YEAR_MIN);
      // STAT: national_annual.json fod[year].acres
      const acStr = acres != null ? `${abbrevM(acres)} acres burned` : '—';
      return { kind: 'year', t, big: `${y} · ${acStr}`, aria: `${y}, ${acStr}` };
    }
    const d = Math.round(this.timeline.day);
    const mi = monthOfDoy(d);
    const t = (d - 1) / 365;
    const big = `${MONTH_NAMES[mi]} · day ${d}`;
    return { kind: 'day', t, big, aria: `${MONTH_NAMES[mi]}, day ${d} of 366` };
  }
}

/** 10,495,382 -> "10.5M"; 970000 -> "1.0M" style, one decimal. */
function abbrevM(acres) {
  return `${(acres / 1e6).toFixed(1)}M`;
}

export default Console;
