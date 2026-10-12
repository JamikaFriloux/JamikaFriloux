/** Minimal absolute-coordinate SVG path utilities used for template authoring and layout. */

export type PathCmd =
  | { c: 'M' | 'L'; p: [number, number] }
  | { c: 'C'; p: [number, number, number, number, number, number] }
  | { c: 'Q'; p: [number, number, number, number] }
  | { c: 'Z' };

const TOKEN = /([MLCQZ])|(-?\d*\.?\d+(?:e-?\d+)?)/gi;

export function parsePath(d: string): PathCmd[] {
  const out: PathCmd[] = [];
  let cmd: string | null = null;
  let nums: number[] = [];
  const flush = () => {
    if (!cmd) return;
    const arity = cmd === 'C' ? 6 : cmd === 'Q' ? 4 : cmd === 'Z' ? 0 : 2;
    if (arity === 0) {
      out.push({ c: 'Z' });
    } else {
      if (nums.length % arity !== 0) throw new Error(`Bad arity for ${cmd} in path: ${d}`);
      for (let i = 0; i < nums.length; i += arity) {
        const p = nums.slice(i, i + arity);
        // Implicit repeats after M are L.
        const c = cmd === 'M' && i > 0 ? 'L' : cmd;
        out.push({ c, p } as PathCmd);
      }
    }
    nums = [];
  };
  for (const m of d.matchAll(TOKEN)) {
    if (m[1]) {
      flush();
      cmd = m[1].toUpperCase();
      if (m[1] !== m[1].toUpperCase()) throw new Error(`Relative path commands not supported: ${d}`);
    } else {
      nums.push(parseFloat(m[2]));
    }
  }
  flush();
  return out;
}

const fmt = (n: number) => String(Math.round(n * 100) / 100);

export function serializePath(cmds: PathCmd[]): string {
  return cmds.map((k) => (k.c === 'Z' ? 'Z' : k.c + k.p.map(fmt).join(','))).join(' ');
}

export function mapPath(d: string, f: (x: number, y: number) => [number, number]): string {
  const cmds = parsePath(d).map((k): PathCmd => {
    if (k.c === 'Z') return k;
    const p = [...k.p];
    for (let i = 0; i < p.length; i += 2) {
      const [x, y] = f(p[i], p[i + 1]);
      p[i] = x;
      p[i + 1] = y;
    }
    return { c: k.c, p } as PathCmd;
  });
  return serializePath(cmds);
}

/** Mirror a path horizontally around x = axis/2 (default viewBox width 1000). */
export function mirrorPath(d: string, width = 1000): string {
  return mapPath(d, (x, y) => [width - x, y]);
}

export function translatePath(d: string, dx: number, dy: number): string {
  return mapPath(d, (x, y) => [x + dx, y + dy]);
}

/** Reverse an open path made of M/L/C/Q segments (used for building closed shapes). */
export function reversePath(d: string): string {
  const cmds = parsePath(d);
  const pts: [number, number][] = [];
  const segs: PathCmd[] = [];
  let cur: [number, number] = [0, 0];
  for (const k of cmds) {
    if (k.c === 'Z') continue;
    if (k.c === 'M') {
      cur = [k.p[0], k.p[1]];
      pts.push(cur);
      continue;
    }
    segs.push(k);
    const end: [number, number] = [k.p[k.p.length - 2], k.p[k.p.length - 1]];
    pts.push(end);
    cur = end;
  }
  const out: PathCmd[] = [{ c: 'M', p: pts[pts.length - 1] }];
  for (let i = segs.length - 1; i >= 0; i--) {
    const s = segs[i];
    const start = pts[i];
    if (s.c === 'L') out.push({ c: 'L', p: start });
    else if (s.c === 'C') out.push({ c: 'C', p: [s.p[2], s.p[3], s.p[0], s.p[1], start[0], start[1]] });
    else if (s.c === 'Q') out.push({ c: 'Q', p: [s.p[0], s.p[1], start[0], start[1]] });
  }
  return serializePath(out);
}

/** Sample a path into a polyline (beziers flattened with fixed subdivisions). */
export function flattenPath(d: string, steps = 16): [number, number][][] {
  const rings: [number, number][][] = [];
  let ring: [number, number][] = [];
  let cur: [number, number] = [0, 0];
  let start: [number, number] = [0, 0];
  for (const k of parsePath(d)) {
    if (k.c === 'M') {
      if (ring.length) rings.push(ring);
      cur = start = [k.p[0], k.p[1]];
      ring = [cur];
    } else if (k.c === 'L') {
      cur = [k.p[0], k.p[1]];
      ring.push(cur);
    } else if (k.c === 'C') {
      const [x1, y1, x2, y2, x, y] = k.p;
      for (let i = 1; i <= steps; i++) {
        const t = i / steps;
        const mt = 1 - t;
        ring.push([
          mt * mt * mt * cur[0] + 3 * mt * mt * t * x1 + 3 * mt * t * t * x2 + t * t * t * x,
          mt * mt * mt * cur[1] + 3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t * t * t * y,
        ]);
      }
      cur = [x, y];
    } else if (k.c === 'Q') {
      const [x1, y1, x, y] = k.p;
      for (let i = 1; i <= steps; i++) {
        const t = i / steps;
        const mt = 1 - t;
        ring.push([mt * mt * cur[0] + 2 * mt * t * x1 + t * t * x, mt * mt * cur[1] + 2 * mt * t * y1 + t * t * y]);
      }
      cur = [x, y];
    } else if (k.c === 'Z') {
      ring.push(start);
      cur = start;
    }
  }
  if (ring.length) rings.push(ring);
  return rings;
}

export function pathBBox(d: string): { x: number; y: number; width: number; height: number } {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  for (const ring of flattenPath(d)) {
    for (const [x, y] of ring) {
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

/** Even-odd point-in-polygon over all rings of a path. */
export function pointInPath(d: string, x: number, y: number): boolean {
  let inside = false;
  for (const ring of flattenPath(d)) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
  }
  return inside;
}

export function polylineLength(pts: { x: number; y: number }[]): number {
  let len = 0;
  for (let i = 1; i < pts.length; i++) len += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  return len;
}

/**
 * Deterministic positions spaced `spacing` apart along a polyline, starting at the first
 * point. Count = floor(length / spacing) + 1.
 */
export function pointsAlongPolyline(pts: { x: number; y: number }[], spacing: number): { x: number; y: number }[] {
  if (pts.length < 2 || spacing <= 0) return pts.slice(0, 1);
  const total = polylineLength(pts);
  // Small epsilon so a path of exactly n*spacing gets n+1 points despite float error.
  const count = Math.floor(total / spacing + 1e-9) + 1;
  const out: { x: number; y: number }[] = [];
  let seg = 1;
  let segStart = 0;
  for (let i = 0; i < count; i++) {
    const target = i * spacing;
    while (seg < pts.length - 1 && segStart + dist(pts[seg - 1], pts[seg]) < target) {
      segStart += dist(pts[seg - 1], pts[seg]);
      seg++;
    }
    const a = pts[seg - 1];
    const b = pts[seg];
    const l = dist(a, b) || 1;
    const t = Math.min(1, Math.max(0, (target - segStart) / l));
    out.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
  }
  return out;
}

function dist(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(b.x - a.x, b.y - a.y);
}
