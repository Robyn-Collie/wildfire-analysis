/**
 * gestures.js — cooperative zoom/pan gesture layer for the v3 console.
 *
 * The map lives INSIDE a scrolling page, so gestures must never steal a plain
 * scroll or a one-finger swipe. The rules (v3-console brief §5):
 *   - Desktop wheel zooms ONLY with ctrl/cmd held; a plain wheel over the map
 *     scrolls the page and briefly shows a "Ctrl + scroll to zoom" hint.
 *   - Drag pans when zoomed in (z > 1).
 *   - Double-click zooms in 2× at the cursor.
 *   - Touch: pinch = zoom (anchored at the pinch center), two-finger drag =
 *     pan, and ONE FINGER ALWAYS SCROLLS THE PAGE. We only ever preventDefault
 *     on 2+ pointer gestures; the canvas carries touch-action: pan-y so the
 *     browser owns single-finger vertical scroll.
 *
 * Click-vs-drag is disambiguated by movement threshold so the pick handler
 * (owned by console.js) fires only on a genuine tap/click.
 *
 * @module gestures
 */

const CLICK_SLOP = 6;        // px of movement below which a pointerup is a click
const HINT_MS = 1400;        // how long the "ctrl + scroll" hint stays up

/**
 * Attach cooperative gestures to a canvas driving a FireMap engine.
 *
 * @param {HTMLCanvasElement} canvas   the WebGL canvas (also the hit target)
 * @param {import('../engine/firemap.js').FireMap} engine
 * @param {object} [opts]
 * @param {(clientX:number, clientY:number) => void} [opts.onTap]
 *   called on a genuine click/tap (movement under CLICK_SLOP, single pointer)
 * @param {(msg:string) => void} [opts.onHint]
 *   called with a transient hint string (or '' to clear) — the console shows it
 * @returns {{destroy: () => void}}
 */
export function attachGestures(canvas, engine, opts = {}) {
  const onTap = opts.onTap || (() => {});
  const onHint = opts.onHint || (() => {});

  // active pointers by id -> {x, y}
  const pointers = new Map();
  let downPt = null;           // {x, y} of a single-pointer press (for click/drag)
  let moved = 0;               // max movement during the current press
  let panning = false;         // single-pointer drag-pan in progress (desktop)

  // two-pointer (pinch/pan) state
  let pinchPrev = null;        // {cx, cy, dist}

  let hintTimer = null;
  function flashHint() {
    onHint('Ctrl + scroll to zoom');
    clearTimeout(hintTimer);
    hintTimer = setTimeout(() => onHint(''), HINT_MS);
  }

  /* ---- wheel: ctrl/cmd zoom, else let the page scroll ---- */
  function onWheel(e) {
    if (e.ctrlKey || e.metaKey) {
      // browser pinch-zoom and intentional ctrl+wheel both land here.
      e.preventDefault();
      const factor = Math.exp(-e.deltaY * 0.0015);   // smooth, direction-correct
      engine.zoomAt(factor, e.clientX, e.clientY);
    } else {
      // plain wheel over the map: do NOT preventDefault (page scrolls), hint.
      flashHint();
    }
  }

  /* ---- pointer down ---- */
  function onPointerDown(e) {
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1) {
      downPt = { x: e.clientX, y: e.clientY };
      moved = 0;
      panning = false;
    } else if (pointers.size === 2) {
      // entering a two-pointer gesture: cancel any pending click, seed pinch.
      downPt = null;
      const pts = [...pointers.values()];
      pinchPrev = pinchState(pts[0], pts[1]);
    }
  }

  /* ---- pointer move ---- */
  function onPointerMove(e) {
    const p = pointers.get(e.pointerId);
    if (!p) return;
    const prevX = p.x, prevY = p.y;
    p.x = e.clientX; p.y = e.clientY;

    if (pointers.size >= 2) {
      // two-finger / two-button gesture: pinch-zoom + pan. Always ours.
      e.preventDefault();
      const pts = [...pointers.values()];
      const cur = pinchState(pts[0], pts[1]);
      if (pinchPrev) {
        if (pinchPrev.dist > 0 && cur.dist > 0) {
          engine.zoomAt(cur.dist / pinchPrev.dist, cur.cx, cur.cy);
        }
        // pan by the movement of the pinch centroid
        const dx = cur.cx - pinchPrev.cx;
        const dy = cur.cy - pinchPrev.cy;
        if (dx || dy) engine.panBy(dx, dy);
      }
      pinchPrev = cur;
      return;
    }

    // single pointer.
    const dx = e.clientX - prevX, dy = e.clientY - prevY;
    if (downPt) {
      moved = Math.max(moved, Math.hypot(e.clientX - downPt.x, e.clientY - downPt.y));
    }

    // desktop drag-pan: mouse button held AND zoomed in. Touch single-finger is
    // left to the browser (page scroll) — pointerType guards that.
    if (e.pointerType === 'mouse' && (e.buttons & 1) && engine.cam.z > 1) {
      if (moved > CLICK_SLOP) {
        panning = true;
        canvas.style.cursor = 'grabbing';
        engine.panBy(dx, dy);
      }
    }
  }

  /* ---- pointer up / cancel ---- */
  function endPointer(e) {
    const had = pointers.has(e.pointerId);
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinchPrev = null;

    if (!had) return;
    if (pointers.size === 0) {
      canvas.style.cursor = engine.cam.z > 1 ? 'grab' : '';
      // a genuine tap/click: single pointer, minimal movement, not a pan.
      if (downPt && !panning && moved <= CLICK_SLOP) {
        onTap(e.clientX, e.clientY);
      }
      downPt = null;
      panning = false;
    }
  }

  /* ---- double-click: zoom in at cursor ---- */
  function onDblClick(e) {
    e.preventDefault();
    engine.zoomAt(2, e.clientX, e.clientY);
  }

  function pinchState(a, b) {
    return {
      cx: (a.x + b.x) / 2,
      cy: (a.y + b.y) / 2,
      dist: Math.hypot(a.x - b.x, a.y - b.y),
    };
  }

  // wheel must be non-passive so preventDefault works when ctrl is held.
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', endPointer);
  canvas.addEventListener('pointercancel', endPointer);
  canvas.addEventListener('pointerleave', endPointer);
  canvas.addEventListener('dblclick', onDblClick);

  // reflect zoom state in the cursor when the camera changes elsewhere.
  const onCam = ({ z }) => {
    if (!panning) canvas.style.cursor = z > 1 ? 'grab' : '';
  };
  engine.on('camera', onCam);

  return {
    destroy() {
      clearTimeout(hintTimer);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', endPointer);
      canvas.removeEventListener('pointercancel', endPointer);
      canvas.removeEventListener('pointerleave', endPointer);
      canvas.removeEventListener('dblclick', onDblClick);
    },
  };
}

export default attachGestures;
