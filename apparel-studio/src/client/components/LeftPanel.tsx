import React, { useRef, useState } from 'react';
import type { Draft } from 'immer';
import type { Layer } from '../../shared/schema/project';
import { componentsInView, layerTypeLabel, resolveFill } from '../../shared/domain/design';
import { findAnchor, nearestAnchor } from '../../shared/domain/placement';
import {
  makeArtworkLayer,
  makeEmbellishmentLayer,
  makePatternLayer,
  makeStitchingLayer,
  makeTextureLayer,
} from '../../shared/domain/layers';
import { newId } from '../../shared/domain/ids';
import { HARDWARE } from '../../shared/catalog/hardware';
import { api } from '../api';
import { useProject } from '../store/project';
import { useUi } from '../store/ui';
import { Icon } from './Icon';
import { Modal } from './common';

const LAYER_ICON: Record<Layer['type'], string> = {
  panelFill: '■',
  artwork: '✦',
  pattern: '▦',
  texture: '≋',
  stitching: '┄',
  embellishment: '◆',
  hardware: '⚙',
  annotation: '✎',
};

export function LeftPanel() {
  const { doc, template, update, id } = useProject();
  const ui = useUi();
  const fileArt = useRef<HTMLInputElement>(null);
  const filePat = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [hwOpen, setHwOpen] = useState(false);
  if (!doc || !template) return null;
  const inView = componentsInView(template, ui.view);
  const selComp = ui.selectedComponentId;

  const addLayer = (l: Layer, select = true) => {
    update((d) => {
      d.layers.push(l as Draft<Layer>);
    });
    if (select) ui.set({ selectedLayerId: l.id, selectedComponentId: null, leftTab: ui.leftTab });
  };

  const upload = async (file: File, role: 'artwork' | 'pattern-tile') => {
    if (!id) return;
    setBusy(role === 'artwork' ? 'Uploading artwork…' : 'Uploading pattern tile…');
    try {
      const { asset, warnings } = await api.uploadAsset(id, file, role);
      update((d) => {
        d.assets.push(asset);
      });
      if (role === 'artwork') {
        const comp = selComp && inView.has(selComp) ? selComp : null;
        const anchor =
          (comp && template.views.find((v) => v.id === ui.view)!.anchors.find((a) => a.componentId === comp)) ||
          template.views.find((v) => v.id === ui.view)!.anchors.find((a) => /chest|upper_back|front$|center/.test(a.id)) ||
          template.views.find((v) => v.id === ui.view)!.anchors[0];
        const group = template.components.find((c) => c.id === anchor.componentId)?.group;
        const widthMm = group === 'body' || group === 'leg' ? 220 : 70;
        addLayer(makeArtworkLayer(template, asset, { viewId: ui.view, anchorId: anchor.id, widthMm }));
      } else {
        const targets = selComp ? [selComp] : template.components.filter((c) => c.group === 'body').map((c) => c.id);
        addLayer(makePatternLayer(asset, targets));
      }
      ui.notify(warnings.length ? 'warn' : 'info', warnings.length ? warnings.join(' ') : `Added “${asset.filename}”. Original file kept intact.`);
    } catch (e) {
      ui.notify('error', `Upload failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const tools: { label: string; sub: string; onClick: () => void; testid: string }[] = [
    { label: 'Add logo', sub: 'PNG or SVG artwork', onClick: () => fileArt.current?.click(), testid: 'add-logo' },
    { label: 'Add pattern', sub: 'Upload a repeat tile', onClick: () => filePat.current?.click(), testid: 'add-pattern' },
    {
      label: 'Add texture',
      sub: 'Fabric surface look',
      testid: 'add-texture',
      onClick: () => {
        const targets = selComp ? [selComp] : template.components.map((c) => c.id);
        const mat = selComp ? resolveFill(doc, selComp, ui.view).material : undefined;
        addLayer(makeTextureLayer(template, mat?.textureId ?? 'jersey', targets, mat?.id ?? null));
      },
    },
    {
      label: 'Add stitching',
      sub: 'Style seam stitches',
      testid: 'add-stitching',
      onClick: () => {
        const seams = template.views.flatMap((v) => v.seams);
        // Default to the garment's visible topstitch seams (hems, pocket, rise), never an arbitrary join seam.
        const visible = ['coverstitch', 'double-needle', 'topstitch-contrast'];
        const ids = selComp ? [...new Set(seams.filter((s) => s.componentIds.includes(selComp)).map((s) => s.id))] : [...new Set(seams.filter((s) => visible.includes(s.defaultStyle)).map((s) => s.id))];
        const dark = [...doc.colors].sort((a, b) => lum(a.hex) - lum(b.hex))[0];
        addLayer(makeStitchingLayer(template, ids.length ? ids : [seams[0].id], dark.id));
      },
    },
    {
      label: 'Add rhinestones',
      sub: 'Place or along a path',
      testid: 'add-rhinestones',
      onClick: () => {
        const l = makeEmbellishmentLayer('rhinestone', ui.view, selComp ? [selComp] : []);
        addLayer(l);
        ui.set({ tool: { kind: 'place-embellishment' } });
      },
    },
    {
      label: 'Add studs',
      sub: 'Metal studs',
      testid: 'add-studs',
      onClick: () => {
        const l = makeEmbellishmentLayer('stud', ui.view, selComp ? [selComp] : []);
        addLayer(l);
        ui.set({ tool: { kind: 'place-embellishment' } });
      },
    },
    { label: 'Add hardware', sub: 'Eyelets, snaps, trims', onClick: () => setHwOpen(true), testid: 'add-hardware' },
    { label: 'Add note', sub: 'Callout for tech pack', onClick: () => ui.set({ tool: { kind: 'place-note' }, selectedLayerId: null }), testid: 'add-note' },
  ];

  const move = (layerId: string, dir: -1 | 1) =>
    update((d) => {
      const i = d.layers.findIndex((l) => l.id === layerId);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= d.layers.length) return;
      [d.layers[i], d.layers[j]] = [d.layers[j], d.layers[i]];
    });

  const groups = template.components.reduce<Record<string, typeof template.components>>((acc, c) => {
    (acc[c.group] ??= []).push(c);
    return acc;
  }, {});

  return (
    <aside className="side left" aria-label="Garment parts and tools">
      <div className="section">
        <div className="seg" role="tablist" aria-label="Left panel" style={{ width: '100%' }}>
          <button role="tab" aria-selected={ui.leftTab === 'parts'} style={{ flex: 1 }} onClick={() => ui.set({ leftTab: 'parts' })}>
            Parts
          </button>
          <button role="tab" aria-selected={ui.leftTab === 'layers'} style={{ flex: 1 }} onClick={() => ui.set({ leftTab: 'layers' })} data-testid="layers-tab">
            Layers ({doc.layers.length})
          </button>
        </div>
      </div>

      {ui.leftTab === 'parts' ? (
        <div className="section">
          <div className="section-title">Garment parts</div>
          <p className="hint" style={{ marginBottom: 8 }}>
            Click a part (here or on the garment) to change just that part.
          </p>
          {Object.entries(groups).map(([g, comps]) => (
            <div key={g} style={{ marginBottom: 6 }}>
              {comps.map((c) => {
                const f = resolveFill(doc, c.id, inView.has(c.id) ? ui.view : ui.view === 'front' ? 'back' : 'front', ui.colorwayId);
                return (
                  <button key={c.id} className="part-row" aria-pressed={selComp === c.id} onClick={() => ui.selectComponent(c.id)} data-testid={`part-${c.id}`}>
                    <span className="swatch" style={{ background: f.hex }} />
                    <span style={{ flex: 1 }}>{c.name}</span>
                    {!inView.has(c.id) && <span className="badge" title="Not visible in this view">{ui.view === 'front' ? 'back' : 'front'}</span>}
                    {f.isViewOverride && <span className="badge warn">{ui.view} only</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      ) : (
        <div className="section">
          <div className="section-title">Layers (top first)</div>
          {doc.layers.length === 0 && <p className="hint">No layers.</p>}
          <ul role="list" aria-label="Layers" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {[...doc.layers].reverse().map((l) => (
              <LayerRow key={l.id} layer={l} index={doc.layers.indexOf(l)} count={doc.layers.length} onMove={move} />
            ))}
          </ul>
          <p className="hint" style={{ marginTop: 8 }}>Rename with the pencil button, a double-click, or F2. Panel colors always sit under decorations of the same part.</p>
        </div>
      )}

      <div className="section">
        <div className="section-title">Add design</div>
        {busy && <div className="callout info" style={{ marginBottom: 8 }}>{busy}</div>}
        <div className="tool-grid">
          {tools.map((t) => (
            <button key={t.label} className="tool-btn" onClick={t.onClick} data-testid={t.testid} disabled={!!busy}>
              {t.label}
              <span>{t.sub}</span>
            </button>
          ))}
        </div>
        <input ref={fileArt} type="file" accept=".png,.svg,image/png,image/svg+xml" hidden data-testid="file-artwork" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void upload(f, 'artwork'); }} />
        <input ref={filePat} type="file" accept=".png,.svg,image/png,image/svg+xml" hidden data-testid="file-pattern" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void upload(f, 'pattern-tile'); }} />
        <p className="hint" style={{ marginTop: 8 }}>
          {selComp ? `New patterns, textures and stitching target the selected part.` : 'Tip: select a part first to target it.'}
        </p>
      </div>

      {hwOpen && (
        <Modal title="Add hardware" onClose={() => setHwOpen(false)} width={560}>
          <p className="hint" style={{ marginBottom: 10 }}>
            Hardware is placed visually and counted in the BOM. It does not change the garment’s construction — a {template.structure.closure} stays a {template.structure.closure}.
          </p>
          <div className="tool-grid">
            {HARDWARE.map((h) => (
              <button
                key={h.id}
                className="tool-btn"
                onClick={() => {
                  setHwOpen(false);
                  ui.set({ tool: { kind: 'place-hardware', hardwareId: h.id }, selectedLayerId: null });
                }}
                data-testid={`hw-${h.id}`}
              >
                <span style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>
                  <svg width="22" height="22" viewBox={`0 0 100 ${100 / h.aspect}`} style={{ color: '#888' }} dangerouslySetInnerHTML={{ __html: h.svg }} />
                  {h.name}
                </span>
                <span>{h.structuralNote}</span>
              </button>
            ))}
          </div>
        </Modal>
      )}
    </aside>
  );
}

function LayerRow({ layer: l, index, count, onMove }: { layer: Layer; index: number; count: number; onMove: (id: string, dir: -1 | 1) => void }) {
  const update = useProject((s) => s.update);
  const ui = useUi();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(l.name);
  const selected = ui.selectedLayerId === l.id;
  const set = (fn: (x: Draft<Layer>) => void) =>
    update((d) => {
      const x = d.layers.find((y) => y.id === l.id);
      if (x) fn(x);
    });
  const startEdit = () => {
    setDraft(l.name);
    setEditing(true);
  };
  const commit = () => {
    const n = draft.trim().slice(0, 120);
    if (n && n !== l.name) set((x) => void (x.name = n));
    setEditing(false);
  };
  const where = l.view === 'all' ? 'all views' : `${l.view} view`;
  return (
    <li className="layer-row" data-selected={selected} data-testid="layer-row" data-layer-type={l.type} data-layer-id={l.id}>
      <span aria-hidden style={{ width: 16, textAlign: 'center', color: 'var(--ink-3)' }}>
        {LAYER_ICON[l.type]}
      </span>
      {editing ? (
        <input
          className="input sm"
          style={{ flex: 1, minWidth: 0 }}
          autoFocus
          value={draft}
          aria-label={`New name for layer ${l.name}`}
          data-testid="layer-rename-input"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') setEditing(false);
          }}
        />
      ) : (
        <button
          className="name"
          style={{ border: 0, background: 'none', textAlign: 'left', cursor: 'pointer', padding: 0, font: 'inherit', color: 'inherit' }}
          aria-pressed={selected}
          aria-label={`${l.name}, ${layerTypeLabel(l.type)}, ${where}${l.visible ? '' : ', hidden'}${l.locked ? ', locked' : ''}`}
          title={`${layerTypeLabel(l.type)} · ${where}`}
          onClick={() => ui.selectLayer(l.id)}
          onDoubleClick={startEdit}
          onKeyDown={(e) => {
            if (e.key === 'F2') {
              e.preventDefault();
              startEdit();
            }
          }}
        >
          {l.name}
          {l.view !== 'all' && <span className="small muted"> · {l.view}</span>}
        </button>
      )}
      <button className="ico" aria-label={`Rename layer ${l.name}`} title="Rename" data-testid="layer-rename" onClick={startEdit}>
        ✎
      </button>
      <button className="ico" aria-label={`${l.visible ? 'Hide' : 'Show'} layer ${l.name}`} title={l.visible ? 'Hide' : 'Show'} onClick={() => set((x) => void (x.visible = !x.visible))}>
        <Icon name={l.visible ? 'eye' : 'eyeOff'} size={14} />
      </button>
      <button className="ico" aria-label={`${l.locked ? 'Unlock' : 'Lock'} layer ${l.name}`} title={l.locked ? 'Unlock' : 'Lock'} onClick={() => set((x) => void (x.locked = !x.locked))}>
        <Icon name={l.locked ? 'lock' : 'unlock'} size={14} />
      </button>
      <button className="ico" aria-label={`Bring layer ${l.name} forward`} title="Bring forward" disabled={index === count - 1} onClick={() => onMove(l.id, 1)}>
        <Icon name="up" size={14} />
      </button>
      <button className="ico" aria-label={`Send layer ${l.name} backward`} title="Send backward" disabled={index === 0} onClick={() => onMove(l.id, -1)}>
        <Icon name="down" size={14} />
      </button>
    </li>
  );
}

function lum(hex: string) {
  const n = parseInt(hex.slice(1), 16);
  return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
}

// Re-exported helpers for the inspector.
export { findAnchor, nearestAnchor, newId };
