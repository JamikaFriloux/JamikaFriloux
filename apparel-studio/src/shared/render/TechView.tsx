import React from 'react';
import type { GarmentTemplate, TemplatePanel, ViewId } from '../schema/template';
import type { ArtworkLayer, Layer, MaskStroke, PatternLayer, ProjectDoc, TextureLayer } from '../schema/project';
import { getView, layerAppliesToView, resolveColor, resolveFill } from '../domain/design';
import { embellishmentPositions, mmPerUnit } from '../domain/bom';
import { getHardware, FINISH_COLORS } from '../catalog/hardware';
import { EMBELLISHMENT_FINISH_COLORS } from '../catalog/embellishments';
import { getTexture, type TextureDef } from '../catalog/textures';
import { STITCH_DASH } from './stitch';

/** How an asset is drawn: an href (browser) or inline sanitized SVG markup (PDF). */
export type AssetDraw =
  | { kind: 'href'; href: string }
  | { kind: 'inline-svg'; markup: string; viewBox: string }
  | { kind: 'missing' };

export type AssetResolver = (assetId: string) => AssetDraw;

export interface Callout {
  n: number;
  x: number;
  y: number;
}

export interface TechViewProps {
  template: GarmentTemplate;
  doc: ProjectDoc;
  viewId: ViewId;
  colorwayId?: string | null;
  resolveAsset: AssetResolver;
  /** Unique prefix for ids (several views can share a page). */
  idPrefix?: string;
  /** Rendering parts. */
  fills?: boolean;
  textures?: boolean;
  decorations?: boolean;
  /** Filter for which decoration layers (artwork/pattern) are drawn. */
  decorationFilter?: (l: ArtworkLayer | PatternLayer) => boolean;
  /** When fills are off, hide decorations that are covered by higher panels. */
  occludeDecorations?: boolean;
  outlines?: boolean;
  seams?: boolean;
  stitching?: boolean;
  embellishments?: boolean;
  hardware?: boolean;
  annotations?: boolean;
  anchors?: boolean;
  /** Measurement lines to draw; `highlight` is drawn emphasised. */
  measurements?: { pomCodes: Record<string, string>; highlight?: string | null; onlyHighlight?: boolean };
  callouts?: Callout[];
  /** Darken inner (inside-garment) panels. */
  shadeInner?: boolean;
  /** Override viewBox (e.g. padded for print). */
  viewBox?: [number, number, number, number];
  width?: number | string;
  height?: number | string;
  className?: string;
  style?: React.CSSProperties;
  /** Extra children drawn on top inside the same coordinate system (editor overlays). */
  children?: React.ReactNode;
  /** Pointer handlers for panels (editor). */
  onPanelPointerDown?: (e: React.PointerEvent, panel: TemplatePanel) => void;
  onLayerPointerDown?: (e: React.PointerEvent, layer: Layer) => void;
  selectedComponentId?: string | null;
  hoverComponentId?: string | null;
  interactiveLayers?: boolean;
}

const OUTLINE = '#1f2328';

function maskPath(s: MaskStroke): string {
  const p = s.points;
  let d = `M${p[0]},${p[1]}`;
  if (p.length === 2) d += ` L${p[0] + 0.01},${p[1]}`;
  for (let i = 2; i < p.length; i += 2) d += ` L${p[i]},${p[i + 1]}`;
  return d;
}

function LayerMask({ id, strokes, vb }: { id: string; strokes: MaskStroke[]; vb: number[] }) {
  return (
    <mask id={id} maskUnits="userSpaceOnUse" x={vb[0] - 500} y={vb[1] - 500} width={vb[2] + 1000} height={vb[3] + 1000}>
      <rect x={vb[0] - 500} y={vb[1] - 500} width={vb[2] + 1000} height={vb[3] + 1000} fill="#fff" />
      {strokes.map((s, i) => (
        <path
          key={i}
          d={maskPath(s)}
          fill="none"
          stroke={s.mode === 'erase' ? '#000' : '#fff'}
          strokeWidth={s.width}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </mask>
  );
}

/** Procedural vector texture tile (for technical/print views). */
function TexturePattern({ id, def, tile, strength }: { id: string; def: TextureDef; tile: number; strength: number }) {
  const t = tile;
  const op = Math.min(1, 0.12 + strength * 0.35);
  const ink = '#000';
  let body: React.ReactNode;
  switch (def.kind) {
    case 'rib':
      body = <rect x={0} y={0} width={t / 2} height={t} fill={ink} opacity={op * 0.5} />;
      break;
    case 'pique':
      body = (
        <>
          <circle cx={t / 4} cy={t / 4} r={t / 7} fill={ink} opacity={op * 0.6} />
          <circle cx={(3 * t) / 4} cy={(3 * t) / 4} r={t / 7} fill={ink} opacity={op * 0.6} />
        </>
      );
      break;
    case 'waffle':
      body = <path d={`M0,0 H${t} V${t} H0 Z M${t * 0.15},${t * 0.15} V${t * 0.85} H${t * 0.85} V${t * 0.15} Z`} fill={ink} fillRule="evenodd" opacity={op * 0.5} />;
      break;
    case 'twill':
      body = <path d={`M0,${t} L${t},0`} stroke={ink} strokeWidth={t * 0.25} opacity={op * 0.6} />;
      break;
    case 'slub':
      body = (
        <>
          <rect x={0} y={t * 0.2} width={t * 0.6} height={t * 0.04} fill={ink} opacity={op * 0.5} />
          <rect x={t * 0.4} y={t * 0.62} width={t * 0.5} height={t * 0.03} fill={ink} opacity={op * 0.4} />
        </>
      );
      break;
    case 'fleece':
    case 'terry':
      body = (
        <>
          <circle cx={t * 0.2} cy={t * 0.3} r={t * 0.04} fill={ink} opacity={op * 0.5} />
          <circle cx={t * 0.7} cy={t * 0.15} r={t * 0.03} fill={ink} opacity={op * 0.4} />
          <circle cx={t * 0.55} cy={t * 0.75} r={t * 0.035} fill={ink} opacity={op * 0.45} />
        </>
      );
      break;
    default:
      body = <path d={`M0,0 L${t / 2},${t / 2} L${t},0`} fill="none" stroke={ink} strokeWidth={t * 0.12} opacity={op * 0.5} />;
  }
  return (
    <pattern id={id} patternUnits="userSpaceOnUse" width={t} height={t}>
      {body}
    </pattern>
  );
}

function prefixSvgIds(markup: string, prefix: string): string {
  return markup
    .replace(/\bid="([^"]+)"/g, (_m, g) => `id="${prefix}${g}"`)
    .replace(/url\(#([^)]+)\)/g, (_m, g) => `url(#${prefix}${g})`)
    .replace(/(xlink:href|href)="#([^"]+)"/g, (_m, a, g) => `${a}="#${prefix}${g}"`);
}

function AssetImage({ draw, x, y, width, height, prefix, preserve = 'none' }: { draw: AssetDraw; x: number; y: number; width: number; height: number; prefix: string; preserve?: string }) {
  if (draw.kind === 'href') {
    return <image href={draw.href} x={x} y={y} width={width} height={height} preserveAspectRatio={preserve} />;
  }
  if (draw.kind === 'inline-svg') {
    return (
      <svg
        x={x}
        y={y}
        width={width}
        height={height}
        viewBox={draw.viewBox}
        preserveAspectRatio={preserve}
        dangerouslySetInnerHTML={{ __html: prefixSvgIds(draw.markup, prefix) }}
      />
    );
  }
  // Missing asset: visible, explicit placeholder (never silently dropped).
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill="#fff4f4" stroke="#c62828" strokeDasharray="6 4" strokeWidth={2} />
      <text x={x + width / 2} y={y + height / 2} fontSize={Math.max(10, Math.min(28, width / 8))} textAnchor="middle" fill="#c62828" fontFamily="DejaVu Sans, sans-serif">
        Missing file
      </text>
    </g>
  );
}

export function TechView(props: TechViewProps) {
  const {
    template,
    doc,
    viewId,
    colorwayId,
    resolveAsset,
    idPrefix = 'tv',
    fills = true,
    textures = true,
    decorations = true,
    decorationFilter,
    occludeDecorations = false,
    outlines = true,
    seams = true,
    stitching = true,
    embellishments = true,
    hardware = true,
    annotations = true,
    anchors = false,
    measurements,
    callouts,
    shadeInner = true,
  } = props;
  const view = getView(template, viewId);
  const vb = props.viewBox ?? view.viewBox;
  const k = mmPerUnit(template);
  const P = `${idPrefix}-${viewId}`;
  const panels = [...view.panels].sort((a, b) => a.z - b.z);
  const layers = doc.layers.filter((l) => l.visible && layerAppliesToView(l, viewId));

  const decoLayers = layers.filter(
    (l): l is ArtworkLayer | PatternLayer => (l.type === 'artwork' || l.type === 'pattern') && (!decorationFilter || decorationFilter(l)),
  );
  const textureLayers = layers.filter((l): l is TextureLayer => l.type === 'texture');

  // Effective texture per component: explicit texture layer, else the assigned material's texture.
  const textureFor = (componentId: string): { def: TextureDef; scale: number; strength: number; layer?: TextureLayer } | null => {
    const tl = [...textureLayers].reverse().find((l) => l.targets.includes(componentId));
    if (tl) {
      const def = getTexture(tl.textureId);
      return def ? { def, scale: tl.scale, strength: tl.strength * tl.opacity, layer: tl } : null;
    }
    const mat = resolveFill(doc, componentId, viewId, colorwayId).material;
    const def = mat?.textureId ? getTexture(mat.textureId) : undefined;
    return def ? { def, scale: 1, strength: 0.35 } : null;
  };

  const defs: React.ReactNode[] = [];
  // Clip per outer panel.
  for (const p of panels) {
    defs.push(
      <clipPath id={`${P}-clip-${p.id}`} key={`c-${p.id}`}>
        <path d={p.d} />
      </clipPath>,
    );
  }
  // Occlusion masks: a panel minus every higher panel (used when fills are not drawn).
  if (occludeDecorations) {
    panels.forEach((p, i) => {
      const above = panels.slice(i + 1).filter((q) => q.z > p.z);
      defs.push(
        <mask id={`${P}-occ-${p.id}`} key={`o-${p.id}`} maskUnits="userSpaceOnUse" x={vb[0]} y={vb[1]} width={vb[2]} height={vb[3]}>
          <path d={p.d} fill="#fff" />
          {above.map((q) => (
            <path key={q.id} d={q.d} fill="#000" />
          ))}
        </mask>,
      );
    });
  }
  // Layer masks (nondestructive erase).
  const viewMask = (l: { mask: MaskStroke[] }) => l.mask.filter((s) => s.view === viewId);
  for (const l of [...decoLayers, ...textureLayers]) {
    const strokes = viewMask(l);
    if (strokes.length) defs.push(<LayerMask key={`m-${l.id}`} id={`${P}-mask-${l.id}`} strokes={strokes} vb={vb} />);
  }
  // Pattern tiles.
  for (const l of decoLayers) {
    if (l.type !== 'pattern') continue;
    const asset = doc.assets.find((a) => a.id === l.assetId);
    const tw = l.tileWidthMm / k;
    const th = asset ? (tw * asset.height) / asset.width : tw;
    const draw = asset ? resolveAsset(asset.id) : ({ kind: 'missing' } as AssetDraw);
    defs.push(
      <pattern
        key={`p-${l.id}`}
        id={`${P}-pat-${l.id}`}
        patternUnits="userSpaceOnUse"
        width={tw}
        height={th}
        patternTransform={`translate(${l.offsetXmm / k},${l.offsetYmm / k}) rotate(${l.rotation})`}
      >
        <AssetImage draw={draw} x={0} y={0} width={tw} height={th} prefix={`${P}-pt-${l.id}-`} />
      </pattern>,
    );
  }
  // Texture tiles used in this view.
  const usedTextures = new Map<string, { def: TextureDef; tile: number; strength: number }>();
  if (textures) {
    for (const p of panels) {
      const t = textureFor(p.componentId);
      if (!t) continue;
      const key = `${t.def.id}-${t.scale}-${t.strength.toFixed(2)}`;
      // Tiles are exaggerated 4x on the flat so the structure stays visible at screen scale.
      usedTextures.set(key, { def: t.def, tile: (t.def.tileMm * t.scale * 4) / k, strength: t.strength });
    }
    for (const [key, t] of usedTextures) defs.push(<TexturePattern key={`t-${key}`} id={`${P}-tex-${key}`} def={t.def} tile={t.tile} strength={t.strength} />);
  }

  // Embellishment gradients.
  defs.push(
    <radialGradient id={`${P}-stone`} key="g-stone" cx="35%" cy="30%" r="75%">
      <stop offset="0%" stopColor="#ffffff" stopOpacity={0.95} />
      <stop offset="45%" stopColor="#ffffff" stopOpacity={0.15} />
      <stop offset="100%" stopColor="#000000" stopOpacity={0.35} />
    </radialGradient>,
    <radialGradient id={`${P}-stud`} key="g-stud" cx="40%" cy="35%" r="70%">
      <stop offset="0%" stopColor="#ffffff" stopOpacity={0.85} />
      <stop offset="60%" stopColor="#ffffff" stopOpacity={0} />
      <stop offset="100%" stopColor="#000000" stopOpacity={0.45} />
    </radialGradient>,
  );

  const renderDeco = (l: ArtworkLayer | PatternLayer, keySuffix: string, clipPanelId: string | null) => {
    const maskAttr = viewMask(l).length ? `url(#${P}-mask-${l.id})` : undefined;
    let content: React.ReactNode;
    if (l.type === 'pattern') {
      content = <rect x={vb[0]} y={vb[1]} width={vb[2]} height={vb[3]} fill={`url(#${P}-pat-${l.id})`} />;
    } else {
      const t = l.transform;
      const asset = doc.assets.find((a) => a.id === l.assetId);
      const draw = asset ? resolveAsset(asset.id) : ({ kind: 'missing' } as AssetDraw);
      content = (
        <g transform={`rotate(${t.rotation} ${t.x} ${t.y})`}>
          <AssetImage draw={draw} x={t.x - t.width / 2} y={t.y - t.height / 2} width={t.width} height={t.height} prefix={`${P}-a-${l.id}-${keySuffix}-`} />
        </g>
      );
    }
    const interactive = props.interactiveLayers && !l.locked;
    return (
      <g
        key={`${l.id}-${keySuffix}`}
        opacity={l.opacity}
        clipPath={clipPanelId ? `url(#${P}-clip-${clipPanelId})` : undefined}
        data-layer-id={l.id}
        style={interactive ? { cursor: 'move' } : undefined}
        onPointerDown={interactive && props.onLayerPointerDown ? (e) => props.onLayerPointerDown!(e, l) : undefined}
      >
        <g mask={maskAttr}>{content}</g>
      </g>
    );
  };

  const panelNodes: React.ReactNode[] = [];
  for (const p of panels) {
    const fill = resolveFill(doc, p.componentId, viewId, colorwayId);
    const tex = textures ? textureFor(p.componentId) : null;
    const texKey = tex ? `${tex.def.id}-${tex.scale}-${tex.strength.toFixed(2)}` : null;
    const selected = props.selectedComponentId === p.componentId;
    const hovered = props.hoverComponentId === p.componentId;
    const group: React.ReactNode[] = [];
    if (fills) {
      group.push(
        <path
          key="fill"
          d={p.d}
          fill={fill.hex}
          data-panel-id={p.id}
          data-component-id={p.componentId}
          data-fill={fill.hex}
          onPointerDown={props.onPanelPointerDown ? (e) => props.onPanelPointerDown!(e, p) : undefined}
          style={props.onPanelPointerDown ? { cursor: 'pointer' } : undefined}
        />,
      );
      if (texKey && tex) {
        const tl = tex.layer;
        group.push(
          <g key="tex" clipPath={`url(#${P}-clip-${p.id})`} pointerEvents="none" mask={tl && viewMask(tl).length ? `url(#${P}-mask-${tl.id})` : undefined}>
            <rect x={vb[0]} y={vb[1]} width={vb[2]} height={vb[3]} fill={`url(#${P}-tex-${texKey})`} />
          </g>,
        );
      }
      if (p.side === 'inner' && shadeInner) group.push(<path key="inner" d={p.d} fill="#000" opacity={0.18} pointerEvents="none" />);
    }
    if (decorations && p.side === 'outer') {
      const mine = decoLayers.filter((l) => l.targets.includes(p.componentId) && (l.type === 'pattern' || l.clipToTargets));
      const nodes = mine.map((l) => renderDeco(l, p.id, p.id));
      if (nodes.length) {
        group.push(
          <g key="deco" mask={occludeDecorations ? `url(#${P}-occ-${p.id})` : undefined}>
            {nodes}
          </g>,
        );
      }
    }
    if (selected || hovered) {
      group.push(
        <path
          key="sel"
          d={p.d}
          fill={selected ? 'rgba(37,99,235,0.10)' : 'rgba(37,99,235,0.05)'}
          stroke="#2563eb"
          strokeWidth={selected ? 4 : 2}
          strokeDasharray={selected ? undefined : '8 6'}
          pointerEvents="none"
        />,
      );
    }
    panelNodes.push(
      <g key={p.id} data-panel={p.id}>
        {group}
      </g>,
    );
  }

  // Unclipped artwork draws above all panels.
  const unclipped = decorations
    ? decoLayers.filter((l): l is ArtworkLayer => l.type === 'artwork' && !l.clipToTargets).map((l) => renderDeco(l, 'free', null))
    : [];

  // Seams: thin construction lines; template stitch lines (hems) dashed unless restyled.
  const stitchLayers = layers.filter((l): l is Extract<Layer, { type: 'stitching' }> => l.type === 'stitching');
  const restyled = new Set(stitchLayers.flatMap((l) => l.seamIds));
  const seamNodes: React.ReactNode[] = [];
  if (seams) {
    for (const s of view.seams) {
      if (restyled.has(s.id) && stitching) continue;
      const isStitchLine = s.defaultStyle === 'coverstitch' || s.defaultStyle === 'double-needle' || s.defaultStyle === 'single-needle';
      seamNodes.push(
        <path
          key={s.id}
          d={s.d}
          fill="none"
          stroke={OUTLINE}
          strokeWidth={isStitchLine ? 1.1 : 1.3}
          strokeDasharray={isStitchLine ? STITCH_DASH['single-needle'].dash : undefined}
          opacity={isStitchLine ? 0.75 : 0.9}
          pointerEvents="none"
          data-seam-id={s.id}
        />,
      );
      if (s.defaultStyle === 'coverstitch' || s.defaultStyle === 'double-needle') {
        seamNodes.push(
          <path key={`${s.id}-2`} d={s.d} fill="none" stroke={OUTLINE} strokeWidth={1.1} strokeDasharray={STITCH_DASH['single-needle'].dash} opacity={0.75} transform="translate(0,6)" pointerEvents="none" />,
        );
      }
    }
  }
  const stitchNodes: React.ReactNode[] = [];
  if (stitching) {
    for (const l of stitchLayers) {
      const col = resolveColor(doc, l.colorId, colorwayId)?.hex ?? '#333';
      const st = STITCH_DASH[l.style];
      for (const sid of l.seamIds) {
        const s = view.seams.find((x) => x.id === sid);
        if (!s) continue;
        const offsets = st.rows === 2 ? [-3, 3] : [0];
        offsets.forEach((o, i) =>
          stitchNodes.push(
            <path
              key={`${l.id}-${sid}-${i}`}
              d={s.d}
              transform={o ? `translate(0,${o})` : undefined}
              fill="none"
              stroke={col}
              strokeWidth={st.width}
              strokeDasharray={st.dash}
              strokeLinecap="round"
              opacity={l.opacity}
              data-stitch-layer={l.id}
              pointerEvents="none"
            />,
          ),
        );
      }
    }
  }

  const embNodes: React.ReactNode[] = [];
  if (embellishments) {
    for (const l of layers) {
      if (l.type !== 'embellishment') continue;
      const r = l.diameterMm / k / 2;
      const base = (l.colorId && resolveColor(doc, l.colorId, colorwayId)?.hex) || EMBELLISHMENT_FINISH_COLORS[l.finish] || '#ddd';
      const pts = embellishmentPositions(l, template);
      embNodes.push(
        <g
          key={l.id}
          opacity={l.opacity}
          data-emb-layer={l.id}
          data-count={pts.length}
          onPointerDown={props.interactiveLayers && !l.locked && props.onLayerPointerDown ? (e) => props.onLayerPointerDown!(e, l) : undefined}
        >
          {pts.map((p, i) =>
            l.kind === 'rhinestone' ? (
              <g key={i}>
                <circle cx={p.x} cy={p.y} r={r} fill={base} stroke="#555" strokeWidth={Math.max(0.3, r * 0.12)} />
                <circle cx={p.x} cy={p.y} r={r} fill={`url(#${P}-stone)`} />
              </g>
            ) : (
              <g key={i}>
                <circle cx={p.x} cy={p.y} r={r} fill={base} stroke="#333" strokeWidth={Math.max(0.3, r * 0.1)} />
                <circle cx={p.x} cy={p.y} r={r * 0.9} fill={`url(#${P}-stud)`} />
              </g>
            ),
          )}
        </g>,
      );
    }
  }

  const hwNodes: React.ReactNode[] = [];
  if (hardware) {
    for (const l of layers) {
      if (l.type !== 'hardware') continue;
      const def = getHardware(l.hardwareId);
      const t = l.transform;
      const color = FINISH_COLORS[l.finish] ?? '#bbb';
      hwNodes.push(
        <g
          key={l.id}
          transform={`rotate(${t.rotation} ${t.x} ${t.y})`}
          opacity={l.opacity}
          data-hw-layer={l.id}
          onPointerDown={props.interactiveLayers && !l.locked && props.onLayerPointerDown ? (e) => props.onLayerPointerDown!(e, l) : undefined}
          style={props.interactiveLayers && !l.locked ? { cursor: 'move' } : undefined}
        >
          {def ? (
            <svg
              x={t.x - t.width / 2}
              y={t.y - t.height / 2}
              width={t.width}
              height={t.height}
              viewBox={`0 0 100 ${100 / def.aspect}`}
              preserveAspectRatio="none"
              dangerouslySetInnerHTML={{ __html: def.svg.replace(/currentColor/g, color) }}
            />
          ) : (
            <rect x={t.x - t.width / 2} y={t.y - t.height / 2} width={t.width} height={t.height} fill="none" stroke="#c62828" strokeDasharray="4 3" />
          )}
        </g>,
      );
    }
  }

  const annNodes: React.ReactNode[] = [];
  if (annotations) {
    for (const l of layers) {
      if (l.type !== 'annotation') continue;
      annNodes.push(
        <g
          key={l.id}
          opacity={l.opacity}
          data-ann-layer={l.id}
          onPointerDown={props.interactiveLayers && !l.locked && props.onLayerPointerDown ? (e) => props.onLayerPointerDown!(e, l) : undefined}
          style={props.interactiveLayers && !l.locked ? { cursor: 'move' } : undefined}
        >
          {l.target && <line x1={l.x} y1={l.y} x2={l.target.x} y2={l.target.y} stroke="#b45309" strokeWidth={1.5} />}
          {l.target && <circle cx={l.target.x} cy={l.target.y} r={4} fill="#b45309" />}
          <text x={l.x} y={l.y} fontSize={18} fill="#92400e" fontFamily="DejaVu Sans, sans-serif" stroke="#fff" strokeWidth={4} paintOrder="stroke">
            {l.text}
          </text>
        </g>,
      );
    }
  }

  const outlineNodes = outlines
    ? panels.map((p) => <path key={`o-${p.id}`} d={p.d} fill="none" stroke={OUTLINE} strokeWidth={2.2} strokeLinejoin="round" pointerEvents="none" />)
    : [];
  const detailNodes = outlines
    ? view.details.map((d) => (
        <path
          key={d.id}
          d={d.d}
          fill="none"
          stroke={OUTLINE}
          strokeWidth={d.kind === 'rib' ? 0.8 : 1.6}
          opacity={d.kind === 'rib' ? 0.45 : 0.9}
          strokeDasharray={d.kind === 'fold' ? '10 6' : undefined}
          pointerEvents="none"
        />
      ))
    : [];

  const measureNodes: React.ReactNode[] = [];
  if (measurements) {
    for (const ml of view.measurementLines) {
      const code = measurements.pomCodes[ml.pomId];
      if (!code) continue;
      const hi = measurements.highlight === ml.pomId;
      if (measurements.onlyHighlight && !hi) continue;
      const color = hi ? '#d9480f' : '#1d4ed8';
      const [x1, y1] = ml.from;
      const [x2, y2] = ml.to;
      const ang = Math.atan2(y2 - y1, x2 - x1);
      const ah = 12;
      const arrow = (x: number, y: number, a: number) =>
        `M${x},${y} L${x - ah * Math.cos(a - 0.4)},${y - ah * Math.sin(a - 0.4)} M${x},${y} L${x - ah * Math.cos(a + 0.4)},${y - ah * Math.sin(a + 0.4)}`;
      measureNodes.push(
        <g key={ml.pomId} data-pom={ml.pomId} pointerEvents="none">
          <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={hi ? 3.5 : 2} />
          <path d={`${arrow(x2, y2, ang)} ${arrow(x1, y1, ang + Math.PI)}`} stroke={color} strokeWidth={hi ? 3.5 : 2} fill="none" />
          <circle cx={ml.label[0]} cy={ml.label[1]} r={hi ? 17 : 14} fill={color} />
          <text x={ml.label[0]} y={ml.label[1] + (hi ? 6 : 5)} fontSize={hi ? 17 : 14} fontWeight="bold" textAnchor="middle" fill="#fff" fontFamily="DejaVu Sans, sans-serif">
            {code}
          </text>
        </g>,
      );
    }
  }

  const anchorNodes = anchors
    ? view.anchors.map((a) => (
        <g key={a.id} pointerEvents="none" data-anchor={a.id}>
          <circle cx={a.x} cy={a.y} r={6} fill="none" stroke="#7c3aed" strokeWidth={2} />
          <path d={`M${a.x - 10},${a.y} H${a.x + 10} M${a.x},${a.y - 10} V${a.y + 10}`} stroke="#7c3aed" strokeWidth={1.5} />
        </g>
      ))
    : [];

  const calloutNodes = (callouts ?? []).map((c) => (
    <g key={`co-${c.n}`}>
      <circle cx={c.x} cy={c.y} r={15} fill="#111827" stroke="#fff" strokeWidth={2} />
      <text x={c.x} y={c.y + 5.5} fontSize={15} fontWeight="bold" textAnchor="middle" fill="#fff" fontFamily="DejaVu Sans, sans-serif">
        {c.n}
      </text>
    </g>
  ));

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={vb.join(' ')}
      width={props.width}
      height={props.height}
      className={props.className}
      style={props.style}
    >
      <defs>{defs}</defs>
      {panelNodes}
      {unclipped}
      {seamNodes}
      {detailNodes}
      {outlineNodes}
      {stitchNodes}
      {embNodes}
      {hwNodes}
      {annNodes}
      {measureNodes}
      {anchorNodes}
      {calloutNodes}
      {props.children}
    </svg>
  );
}
