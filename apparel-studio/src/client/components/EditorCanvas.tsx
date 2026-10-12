import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { Draft } from 'immer';
import { TechView } from '../../shared/render/TechView';
import type { ArtworkLayer, HardwareLayer, Layer, ProjectDoc, Transform, EmbellishmentLayer } from '../../shared/schema/project';
import { getView } from '../../shared/domain/design';
import { applyCanvasTransform } from '../../shared/domain/placement';
import { componentsAt, makeAnnotationLayer, makeHardwareLayer } from '../../shared/domain/layers';
import { embellishmentPositions } from '../../shared/domain/bom';
import { newId } from '../../shared/domain/ids';
import { useProject } from '../store/project';
import { useUi } from '../store/ui';
import { useAssetResolver } from './common';

type Gesture =
  | { kind: 'pan'; startClient: { x: number; y: number }; startPan: { x: number; y: number }; unitsPerPx: number }
  | { kind: 'move'; layerId: string; start: { x: number; y: number }; startT: Transform; key: string }
  | { kind: 'resize'; layerId: string; sx: number; sy: number; startT: Transform; lockAspect: boolean; key: string }
  | { kind: 'rotate'; layerId: string; startT: Transform; key: string }
  | { kind: 'erase'; layerId: string; key: string; last: { x: number; y: number } }
  | { kind: 'emb-point'; layerId: string; index: number; key: string }
  | { kind: 'emb-path-point'; layerId: string; pathIndex: number; index: number; key: string }
  | { kind: 'note'; layerId: string; part: 'text' | 'target'; start: { x: number; y: number }; startXY: { x: number; y: number }; key: string };

function rot(p: { x: number; y: number }, deg: number) {
  const a = (deg * Math.PI) / 180;
  return { x: p.x * Math.cos(a) - p.y * Math.sin(a), y: p.x * Math.sin(a) + p.y * Math.cos(a) };
}

export function findLayer(d: Draft<ProjectDoc>, id: string) {
  return d.layers.find((l) => l.id === id);
}

export function EditorCanvas() {
  const { doc, template, update } = useProject();
  const ui = useUi();
  const wrapRef = useRef<HTMLDivElement>(null);
  const gesture = useRef<Gesture | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null);
  const [hoverComp, setHoverComp] = useState<string | null>(null);
  const [spaceDown, setSpaceDown] = useState(false);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const resolve = useAssetResolver(doc);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const view = getView(template!, ui.view);
  const [vx, vy, vw, vh] = view.viewBox;
  const pad = 30;
  const aspect = size.w / Math.max(1, size.h);
  let bw = vw + pad * 2;
  let bh = vh + pad * 2;
  if (bw / bh < aspect) bw = bh * aspect;
  else bh = bw / aspect;
  const w = bw / ui.zoom;
  const h = bh / ui.zoom;
  const cx = vx + vw / 2 + ui.pan.x;
  const cy = vy + vh / 2 + ui.pan.y;
  const vb: [number, number, number, number] = [cx - w / 2, cy - h / 2, w, h];
  const upp = w / Math.max(1, size.w); // svg units per screen px
  const handleR = 6 * upp;

  const selected = doc?.layers.find((l) => l.id === ui.selectedLayerId) ?? null;

  const toSvg = useCallback((clientX: number, clientY: number) => {
    const svg = wrapRef.current?.querySelector('svg.stage') as SVGSVGElement | null;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return { x: 0, y: 0 };
    const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }, []);

  // Keyboard: delete, duplicate, nudge, escape, space-to-pan.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === ' ') {
        setSpaceDown(e.type === 'keydown');
        if (e.type === 'keydown') e.preventDefault();
        return;
      }
      if (e.type !== 'keydown') return;
      const st = useUi.getState();
      if (e.key === 'Escape') {
        if (st.tool.kind !== 'select') st.set({ tool: { kind: 'select' } });
        else st.set({ selectedLayerId: null, selectedComponentId: null });
        return;
      }
      if (st.tool.kind === 'draw-path' && e.key === 'Enter') {
        commitPath();
        return;
      }
      const layer = useProject.getState().doc?.layers.find((l) => l.id === st.selectedLayerId);
      if (!layer || layer.locked) return;
      if ((e.key === 'Delete' || e.key === 'Backspace') && layer.type !== 'panelFill') {
        e.preventDefault();
        update((d) => {
          d.layers = d.layers.filter((l) => l.id !== layer.id);
        });
        st.set({ selectedLayerId: null });
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        duplicateLayer(layer.id);
      } else if (e.key.startsWith('Arrow')) {
        // Keyboard move: 1 unit (= 1 mm at nominal scale), Shift = 10.
        const step = e.shiftKey ? 10 : 1;
        const dx = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0;
        const dy = e.key === 'ArrowUp' ? -step : e.key === 'ArrowDown' ? step : 0;
        if (layer.type === 'artwork' || layer.type === 'hardware') {
          e.preventDefault();
          setTransform(layer.id, { ...layer.transform, x: layer.transform.x + dx, y: layer.transform.y + dy }, `nudge-${layer.id}`);
        } else if (layer.type === 'embellishment' || layer.type === 'annotation') {
          e.preventDefault();
          update(
            (d) => {
              const l = findLayer(d, layer.id);
              if (l?.type === 'embellishment') {
                l.points = l.points.map((p) => ({ x: p.x + dx, y: p.y + dy }));
                l.paths.forEach((p) => (p.points = p.points.map((q) => ({ x: q.x + dx, y: q.y + dy }))));
              } else if (l?.type === 'annotation') {
                l.x += dx;
                l.y += dy;
              }
            },
            { coalesce: `nudge-${layer.id}` },
          );
        }
      } else if ((e.key === '+' || e.key === '=' || e.key === '-' || e.key === '_') && (layer.type === 'artwork' || layer.type === 'hardware')) {
        // Keyboard resize about the centre, proportions kept: 2% steps, Shift = 10%.
        e.preventDefault();
        const grow = e.key === '+' || e.key === '=';
        const f = grow ? (e.shiftKey ? 1.1 : 1.02) : e.shiftKey ? 1 / 1.1 : 1 / 1.02;
        const t = layer.transform;
        if (t.width * f < 4 || t.height * f < 4) return;
        if (layer.type === 'hardware') {
          update(
            (d) => {
              const l = findLayer(d, layer.id);
              if (l?.type !== 'hardware') return;
              l.transform.width *= f;
              l.transform.height *= f;
              l.sizeMm = Math.round(l.sizeMm * f * 10) / 10;
            },
            { coalesce: `size-${layer.id}` },
          );
        } else setTransform(layer.id, { ...t, width: t.width * f, height: t.height * f }, `size-${layer.id}`);
      } else if ((e.key === '[' || e.key === ']' || e.key === '{' || e.key === '}') && (layer.type === 'artwork' || layer.type === 'hardware')) {
        // Keyboard rotate: 1°, Shift = 15°.
        e.preventDefault();
        const step = (e.shiftKey ? 15 : 1) * (e.key === ']' || e.key === '}' ? 1 : -1);
        const r = ((layer.transform.rotation + step + 540) % 360) - 180;
        setTransform(layer.id, { ...layer.transform, rotation: r }, `rot-${layer.id}`);
      }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('keyup', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('keyup', onKey);
    };
  });

  const setTransform = (layerId: string, t: Transform, key: string) => {
    update(
      (d) => {
        const i = d.layers.findIndex((l) => l.id === layerId);
        const l = d.layers[i];
        if (!l) return;
        if (l.type === 'artwork') d.layers[i] = applyCanvasTransform(template!, l as ArtworkLayer, t) as Draft<Layer>;
        else if (l.type === 'hardware') l.transform = t;
      },
      { coalesce: key },
    );
  };

  const duplicateLayer = (id: string) => {
    let newIdV = '';
    update((d) => {
      const i = d.layers.findIndex((l) => l.id === id);
      if (i < 0) return;
      const copy = JSON.parse(JSON.stringify(d.layers[i])) as Layer;
      copy.id = newId('lyr');
      copy.name = `${copy.name} copy`;
      if (copy.type === 'artwork' || copy.type === 'hardware') {
        copy.transform.x += 20;
        copy.transform.y += 20;
      }
      newIdV = copy.id;
      d.layers.splice(i + 1, 0, copy as Draft<Layer>);
    });
    if (newIdV) useUi.getState().selectLayer(newIdV);
  };

  const commitPath = () => {
    const st = useUi.getState();
    if (st.tool.kind !== 'draw-path') return;
    const pts = st.tool.points;
    const lid = st.selectedLayerId;
    if (pts.length >= 2 && lid) {
      update((d) => {
        const l = findLayer(d, lid);
        if (l?.type === 'embellishment') l.paths.push({ id: newId('pth'), points: pts, spacingMm: Math.max(l.diameterMm * 2, 6) });
      });
    }
    st.set({ tool: { kind: 'select' } });
  };

  // ---- Pointer handling
  const onPointerDownStage = (e: React.PointerEvent) => {
    if (e.button === 1 || spaceDown || ui.tool.kind === 'pan') {
      gesture.current = { kind: 'pan', startClient: { x: e.clientX, y: e.clientY }, startPan: ui.pan, unitsPerPx: upp };
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      return;
    }
    const p = toSvg(e.clientX, e.clientY);
    const tool = ui.tool;
    if (tool.kind === 'erase' && selected && (selected.type === 'pattern' || selected.type === 'artwork' || selected.type === 'texture')) {
      if (selected.locked) return ui.notify('warn', 'Unlock this layer to erase from it.');
      const key = `erase-${Date.now()}`;
      update(
        (d) => {
          const l = findLayer(d, selected.id);
          if (l && (l.type === 'pattern' || l.type === 'artwork' || l.type === 'texture')) l.mask.push({ mode: tool.mode, view: ui.view, width: tool.size, points: [p.x, p.y] });
        },
        { coalesce: key },
      );
      gesture.current = { kind: 'erase', layerId: selected.id, key, last: p };
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      return;
    }
    if (tool.kind === 'place-embellishment' && selected?.type === 'embellishment') {
      update((d) => {
        const l = findLayer(d, selected.id);
        if (l?.type === 'embellishment') {
          l.points.push(p);
          if (l.view !== ui.view) l.view = ui.view;
          const comps = componentsAt(template!, ui.view, p.x, p.y);
          if (comps[0] && !l.targets.includes(comps[0])) l.targets.push(comps[0]);
        }
      });
      return;
    }
    if (tool.kind === 'draw-path') {
      if (e.detail >= 2) return commitPath();
      ui.set({ tool: { ...tool, points: [...tool.points, p] } });
      return;
    }
    if (tool.kind === 'place-hardware') {
      const comps = componentsAt(template!, ui.view, p.x, p.y);
      const l = makeHardwareLayer(template!, tool.hardwareId, ui.view, p.x, p.y, comps.slice(0, 1));
      update((d) => {
        d.layers.push(l as Draft<Layer>);
      });
      ui.set({ tool: { kind: 'select' }, selectedLayerId: l.id, selectedComponentId: null });
      return;
    }
    if (tool.kind === 'place-note') {
      const l = makeAnnotationLayer(ui.view, p.x, p.y, 'Note');
      update((d) => {
        d.layers.push(l as Draft<Layer>);
      });
      ui.set({ tool: { kind: 'select' }, selectedLayerId: l.id, selectedComponentId: null });
      return;
    }
    // Background click: deselect.
    ui.set({ selectedLayerId: null, selectedComponentId: null });
  };

  const onPanelPointerDown = (e: React.PointerEvent, panel: { componentId: string; side: string }) => {
    if (ui.tool.kind !== 'select' || spaceDown || e.button !== 0) return;
    e.stopPropagation();
    ui.selectComponent(panel.componentId);
  };

  const onLayerPointerDown = (e: React.PointerEvent, layer: Layer) => {
    if (ui.tool.kind !== 'select' || spaceDown || e.button !== 0) return;
    if (layer.type !== 'artwork' && layer.type !== 'hardware' && layer.type !== 'annotation' && layer.type !== 'embellishment') return;
    e.stopPropagation();
    ui.selectLayer(layer.id);
    if (layer.locked) return;
    const p = toSvg(e.clientX, e.clientY);
    const key = `move-${layer.id}-${Date.now()}`;
    if (layer.type === 'artwork' || layer.type === 'hardware') {
      gesture.current = { kind: 'move', layerId: layer.id, start: p, startT: layer.transform, key };
    } else if (layer.type === 'annotation') {
      gesture.current = { kind: 'note', layerId: layer.id, part: 'text', start: p, startXY: { x: layer.x, y: layer.y }, key };
    }
    wrapRef.current?.setPointerCapture(e.pointerId);
  };

  const startHandle = (e: React.PointerEvent, g: Gesture) => {
    e.stopPropagation();
    gesture.current = g;
    wrapRef.current?.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const p = toSvg(e.clientX, e.clientY);
    setHover(p);
    const g = gesture.current;
    if (!g) {
      if (ui.tool.kind === 'select') setHoverComp(null);
      return;
    }
    if (g.kind === 'pan') {
      const dx = (e.clientX - g.startClient.x) * g.unitsPerPx;
      const dy = (e.clientY - g.startClient.y) * g.unitsPerPx;
      ui.set({ pan: { x: g.startPan.x - dx, y: g.startPan.y - dy } });
    } else if (g.kind === 'move') {
      setTransform(g.layerId, { ...g.startT, x: g.startT.x + p.x - g.start.x, y: g.startT.y + p.y - g.start.y }, g.key);
    } else if (g.kind === 'resize') {
      const t = g.startT;
      const local = rot({ x: p.x - t.x, y: p.y - t.y }, -t.rotation);
      const o = { x: (-g.sx * t.width) / 2, y: (-g.sy * t.height) / 2 };
      let nw = Math.max(4, Math.abs(local.x - o.x));
      let nh = Math.max(4, Math.abs(local.y - o.y));
      if (g.lockAspect) {
        const s = Math.max(nw / t.width, nh / t.height);
        nw = t.width * s;
        nh = t.height * s;
      }
      const lc = { x: o.x + (g.sx * nw) / 2, y: o.y + (g.sy * nh) / 2 };
      const wc = rot(lc, t.rotation);
      setTransform(g.layerId, { ...t, x: t.x + wc.x, y: t.y + wc.y, width: nw, height: nh }, g.key);
    } else if (g.kind === 'rotate') {
      const t = g.startT;
      let a = (Math.atan2(p.y - t.y, p.x - t.x) * 180) / Math.PI + 90;
      if (e.shiftKey) a = Math.round(a / 15) * 15;
      a = ((a + 540) % 360) - 180;
      setTransform(g.layerId, { ...t, rotation: Math.round(a * 10) / 10 }, g.key);
    } else if (g.kind === 'erase') {
      if (Math.hypot(p.x - g.last.x, p.y - g.last.y) < 2) return;
      g.last = p;
      update(
        (d) => {
          const l = findLayer(d, g.layerId);
          if (l && (l.type === 'pattern' || l.type === 'artwork' || l.type === 'texture')) l.mask[l.mask.length - 1].points.push(p.x, p.y);
        },
        { coalesce: g.key },
      );
    } else if (g.kind === 'emb-point') {
      update(
        (d) => {
          const l = findLayer(d, g.layerId);
          if (l?.type === 'embellishment') l.points[g.index] = p;
        },
        { coalesce: g.key },
      );
    } else if (g.kind === 'emb-path-point') {
      update(
        (d) => {
          const l = findLayer(d, g.layerId);
          if (l?.type === 'embellishment') l.paths[g.pathIndex].points[g.index] = p;
        },
        { coalesce: g.key },
      );
    } else if (g.kind === 'note') {
      update(
        (d) => {
          const l = findLayer(d, g.layerId);
          if (l?.type !== 'annotation') return;
          if (g.part === 'text') {
            l.x = g.startXY.x + p.x - g.start.x;
            l.y = g.startXY.y + p.y - g.start.y;
          } else l.target = p;
        },
        { coalesce: g.key },
      );
    }
  };

  const onPointerUp = () => {
    gesture.current = null;
  };

  const onWheel = (e: React.WheelEvent) => {
    const p = toSvg(e.clientX, e.clientY);
    const factor = Math.exp(-e.deltaY * 0.0015);
    const zoom = Math.min(12, Math.max(0.4, ui.zoom * factor));
    // Keep the point under the cursor fixed.
    const k = ui.zoom / zoom;
    const ncx = p.x - (p.x - cx) * k;
    const ncy = p.y - (p.y - cy) * k;
    ui.set({ zoom, pan: { x: ncx - (vx + vw / 2), y: ncy - (vy + vh / 2) } });
  };

  // ---- Overlays
  const overlays: React.ReactNode[] = [];
  if (selected && (selected.view === ui.view || selected.view === 'all')) {
    if (selected.type === 'artwork' || selected.type === 'hardware') {
      const t = selected.transform;
      if (selected.type === 'artwork') {
        // Show the clip region explicitly.
        for (const p of view.panels.filter((x) => selected.targets.includes(x.componentId) && x.side === 'outer')) {
          overlays.push(<path key={`clip-${p.id}`} d={p.d} fill="none" stroke="#7c3aed" strokeWidth={2 * upp} strokeDasharray={`${6 * upp} ${4 * upp}`} pointerEvents="none" />);
        }
      }
      const corners = [
        [-1, -1],
        [1, -1],
        [1, 1],
        [-1, 1],
      ];
      overlays.push(
        <g key="sel" transform={`rotate(${t.rotation} ${t.x} ${t.y})`} data-testid="selection-box">
          <rect x={t.x - t.width / 2} y={t.y - t.height / 2} width={t.width} height={t.height} fill="none" stroke="#2563eb" strokeWidth={1.5 * upp} strokeDasharray={selected.locked ? `${4 * upp} ${3 * upp}` : undefined} pointerEvents="none" />
          {!selected.locked && (
            <>
              <line x1={t.x} y1={t.y - t.height / 2} x2={t.x} y2={t.y - t.height / 2 - 28 * upp} stroke="#2563eb" strokeWidth={1.5 * upp} />
              <circle
                cx={t.x}
                cy={t.y - t.height / 2 - 28 * upp}
                r={handleR}
                fill="#fff"
                stroke="#2563eb"
                strokeWidth={2 * upp}
                style={{ cursor: 'grab' }}
                data-handle="rotate"
                onPointerDown={(e) => startHandle(e, { kind: 'rotate', layerId: selected.id, startT: t, key: `rot-${Date.now()}` })}
              />
              {corners.map(([sx, sy]) => (
                <rect
                  key={`${sx}${sy}`}
                  x={t.x + (sx * t.width) / 2 - handleR}
                  y={t.y + (sy * t.height) / 2 - handleR}
                  width={handleR * 2}
                  height={handleR * 2}
                  fill="#fff"
                  stroke="#2563eb"
                  strokeWidth={2 * upp}
                  style={{ cursor: sx === sy ? 'nwse-resize' : 'nesw-resize' }}
                  data-handle={`resize-${sx}-${sy}`}
                  onPointerDown={(e) =>
                    startHandle(e, { kind: 'resize', layerId: selected.id, sx, sy, startT: t, lockAspect: selected.type === 'hardware' || (selected as ArtworkLayer).lockAspect, key: `rs-${Date.now()}` })
                  }
                />
              ))}
            </>
          )}
        </g>,
      );
    }
    if (selected.type === 'embellishment') {
      const e = selected as EmbellishmentLayer;
      const r = Math.max(handleR * 0.8, e.diameterMm / 2 + 2 * upp);
      e.points.forEach((pt, i) =>
        overlays.push(
          <circle
            key={`ep-${i}`}
            cx={pt.x}
            cy={pt.y}
            r={r}
            fill="rgba(37,99,235,0.12)"
            stroke="#2563eb"
            strokeWidth={1.5 * upp}
            style={{ cursor: 'move' }}
            data-handle="emb-point"
            onPointerDown={(ev) => {
              if (e.locked) return;
              if (ev.altKey) {
                ev.stopPropagation();
                return update((d) => {
                  const l = findLayer(d, e.id);
                  if (l?.type === 'embellishment') l.points.splice(i, 1);
                });
              }
              startHandle(ev, { kind: 'emb-point', layerId: e.id, index: i, key: `ep-${Date.now()}` });
            }}
          />,
        ),
      );
      e.paths.forEach((path, pi) => {
        overlays.push(<polyline key={`pl-${pi}`} points={path.points.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="#2563eb" strokeWidth={1.2 * upp} strokeDasharray={`${4 * upp} ${3 * upp}`} pointerEvents="none" />);
        path.points.forEach((pt, i) =>
          overlays.push(
            <rect
              key={`pp-${pi}-${i}`}
              x={pt.x - handleR * 0.8}
              y={pt.y - handleR * 0.8}
              width={handleR * 1.6}
              height={handleR * 1.6}
              fill="#fff"
              stroke="#2563eb"
              strokeWidth={1.5 * upp}
              style={{ cursor: 'move' }}
              data-handle="path-point"
              aria-label={`Path ${pi + 1} point ${i + 1}`}
              onPointerDown={(ev) => {
                if (e.locked) return;
                if (ev.altKey) {
                  // Alt+click removes a point (a path keeps at least two).
                  ev.stopPropagation();
                  if (path.points.length <= 2) return ui.notify('warn', 'A path needs at least two points. Delete the whole path from the right panel instead.');
                  return update((d) => {
                    const l = findLayer(d, e.id);
                    if (l?.type === 'embellishment') l.paths[pi].points.splice(i, 1);
                  });
                }
                startHandle(ev, { kind: 'emb-path-point', layerId: e.id, pathIndex: pi, index: i, key: `pp-${Date.now()}` });
              }}
            />,
          ),
        );
        // Midpoint "+" handles insert a new point into the existing path and start dragging it.
        if (!e.locked) {
          path.points.slice(1).forEach((b, i) => {
            const a = path.points[i];
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2;
            overlays.push(
              <g
                key={`ins-${pi}-${i}`}
                data-handle="path-insert"
                data-testid="path-insert"
                role="button"
                aria-label={`Insert point between path ${pi + 1} points ${i + 1} and ${i + 2}`}
                style={{ cursor: 'copy' }}
                onPointerDown={(ev) => {
                  const key = `ins-${Date.now()}`;
                  update(
                    (d) => {
                      const l = findLayer(d, e.id);
                      if (l?.type === 'embellishment') l.paths[pi].points.splice(i + 1, 0, { x: mx, y: my });
                    },
                    { coalesce: key },
                  );
                  startHandle(ev, { kind: 'emb-path-point', layerId: e.id, pathIndex: pi, index: i + 1, key });
                }}
              >
                <circle cx={mx} cy={my} r={handleR * 0.75} fill="#2563eb" fillOpacity={0.85} stroke="#fff" strokeWidth={1.2 * upp} />
                <path d={`M${mx - handleR * 0.4},${my} H${mx + handleR * 0.4} M${mx},${my - handleR * 0.4} V${my + handleR * 0.4}`} stroke="#fff" strokeWidth={1.4 * upp} />
              </g>,
            );
          });
        }
      });
      if (!e.points.length && !e.paths.length) {
        overlays.push(
          <text key="hint" x={vx + vw / 2} y={vy + 40} textAnchor="middle" fontSize={16 * upp} fill="#2563eb">
            Use “Place individually” or “Draw a path” in the right panel
          </text>,
        );
      }
      const count = embellishmentPositions(e, template!).length;
      overlays.push(<g key="count" data-testid="emb-count" data-count={count} />);
    }
    if (selected.type === 'annotation' && selected.target && !selected.locked) {
      overlays.push(
        <circle
          key="note-target"
          cx={selected.target.x}
          cy={selected.target.y}
          r={handleR}
          fill="#fff"
          stroke="#b45309"
          strokeWidth={2 * upp}
          style={{ cursor: 'move' }}
          onPointerDown={(ev) => startHandle(ev, { kind: 'note', layerId: selected.id, part: 'target', start: { x: 0, y: 0 }, startXY: { x: 0, y: 0 }, key: `nt-${Date.now()}` })}
        />,
      );
    }
  }
  if (ui.tool.kind === 'draw-path') {
    const pts = ui.tool.points;
    overlays.push(
      <g key="draw" pointerEvents="none">
        <polyline points={[...pts, ...(hover ? [hover] : [])].map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="#db2777" strokeWidth={2 * upp} strokeDasharray={`${5 * upp} ${3 * upp}`} />
        {pts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={4 * upp} fill="#db2777" />
        ))}
      </g>,
    );
  }
  if (ui.tool.kind === 'erase' && hover) {
    overlays.push(<circle key="brush" cx={hover.x} cy={hover.y} r={ui.tool.size / 2} fill={ui.tool.mode === 'erase' ? 'rgba(220,38,38,0.12)' : 'rgba(22,163,74,0.12)'} stroke={ui.tool.mode === 'erase' ? '#dc2626' : '#16a34a'} strokeWidth={1.5 * upp} pointerEvents="none" />);
  }

  const toolHint: Record<string, string> = {
    erase: ui.tool.kind === 'erase' && ui.tool.mode === 'erase' ? `Drag to erase from “${selected?.name ?? 'the selected layer'}” only. Other layers and the garment stay untouched. Esc to finish.` : 'Drag to restore previously erased areas. Esc to finish.',
    'place-embellishment': 'Click to place one at a time. Drag placed items to adjust; Alt+click removes one. Esc to finish.',
    'draw-path': 'Click to add path points; double-click or Enter to finish. Items are spaced evenly along the path.',
    'place-hardware': 'Click on the garment to place the component. It is a visual placement and does not change the garment’s construction.',
    'place-note': 'Click to add a note for the tech pack.',
    pan: 'Drag to pan.',
  };

  if (!doc || !template) return null;
  return (
    <div
      ref={wrapRef}
      className="canvas"
      onPointerDown={onPointerDownStage}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onPointerLeave={() => setHover(null)}
      onWheel={onWheel}
      style={{ cursor: spaceDown || ui.tool.kind === 'pan' ? 'grab' : ui.tool.kind === 'select' ? 'default' : 'crosshair' }}
      data-testid="canvas"
      data-view={ui.view}
      tabIndex={0}
      role="region"
      aria-label={`Design canvas, ${ui.view} view. Select parts and layers with the mouse or from the Parts and Layers lists; move or resize the selected item with the keyboard (arrows, + and −, [ and ]).`}
    >
      <TechView
        template={template}
        doc={doc}
        viewId={ui.view}
        colorwayId={ui.colorwayId}
        resolveAsset={resolve}
        viewBox={vb}
        className="stage"
        idPrefix="ed"
        anchors={ui.showAnchors}
        interactiveLayers={ui.tool.kind === 'select'}
        onPanelPointerDown={onPanelPointerDown}
        onLayerPointerDown={onLayerPointerDown}
        selectedComponentId={ui.selectedComponentId}
        hoverComponentId={hoverComp}
      >
        {overlays}
      </TechView>
      {ui.tool.kind !== 'select' && <div className="canvas-hint">{toolHint[ui.tool.kind]}</div>}
    </div>
  );
}
