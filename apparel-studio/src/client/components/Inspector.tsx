import React, { useState } from 'react';
import type { Draft } from 'immer';
import type { ArtworkLayer, Layer, PanelFillLayer, ProjectDoc } from '../../shared/schema/project';
import { DECORATION_METHOD_LABELS, STITCH_STYLE_LABELS, type DecorationMethod, type StitchStyle } from '../../shared/schema/template';
import { componentName, componentsInView, fillLayerFor, getView, layerTypeLabel, resolveFill } from '../../shared/domain/design';
import { applyEnteredPlacement, findAnchor } from '../../shared/domain/placement';
import { makeTextureLayer, makeViewOverride } from '../../shared/domain/layers';
import { embellishmentCount } from '../../shared/domain/bom';
import { newId } from '../../shared/domain/ids';
import { TEXTURES } from '../../shared/catalog/textures';
import { HARDWARE, getHardware } from '../../shared/catalog/hardware';
import { RHINESTONE_FINISHES, RHINESTONE_SIZES, STUD_FINISHES, STUD_SIZES } from '../../shared/catalog/embellishments';
import { useProject } from '../store/project';
import { useUi } from '../store/ui';
import { LengthInput, NumberInput, TextInput } from './common';
import { Icon } from './Icon';
import { findLayer } from './EditorCanvas';

type Update = ReturnType<typeof useProject.getState>['update'];

/** Palette picker with inline "new colour". */
export function ColorPicker({ doc, value, onPick, label }: { doc: ProjectDoc; value: string | null; onPick: (colorId: string) => void; label?: string }) {
  const update = useProject((s) => s.update);
  const [adding, setAdding] = useState(false);
  const [hex, setHex] = useState('#3b82f6');
  const [name, setName] = useState('');
  return (
    <div>
      <div className="row wrap" role="radiogroup" aria-label={label ?? 'Color'} style={{ gap: 4 }}>
        {doc.colors.map((c) => (
          <button key={c.id} className="swatch-btn" role="radio" aria-checked={value === c.id} aria-pressed={value === c.id} title={c.name} aria-label={c.name} onClick={() => onPick(c.id)} data-testid={`color-${c.name}`}>
            <span className="swatch lg" style={{ background: c.hex }} />
          </button>
        ))}
        <button className="btn sm" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>
          <Icon name="plus" size={14} /> New
        </button>
      </div>
      {value && <div className="small muted" style={{ marginTop: 4 }}>{doc.colors.find((c) => c.id === value)?.name}</div>}
      {adding && (
        <div className="row" style={{ marginTop: 8 }}>
          <input type="color" value={hex} onChange={(e) => setHex(e.target.value)} aria-label="Screen color" data-testid="new-color-hex" />
          <input className="input sm" placeholder="Color name" value={name} onChange={(e) => setName(e.target.value)} aria-label="New color name" data-testid="new-color-name" />
          <button
            className="btn sm primary"
            disabled={!name.trim()}
            data-testid="new-color-add"
            onClick={() => {
              const id = newId('col');
              update((d) => {
                d.colors.push({ id, name: name.trim(), hex, standard: null, approval: 'not-submitted' });
              });
              onPick(id);
              setAdding(false);
              setName('');
            }}
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className="field">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

function ComponentInspector({ componentId }: { componentId: string }) {
  const { doc, template, update } = useProject();
  const ui = useUi();
  if (!doc || !template) return null;
  const comp = template.components.find((c) => c.id === componentId)!;
  const fill = resolveFill(doc, componentId, ui.view, ui.colorwayId);
  const shared = doc.layers.find((l): l is PanelFillLayer => l.type === 'panelFill' && l.view === 'all' && l.targets[0] === componentId);
  const target = fillLayerFor(doc, componentId, ui.view);
  const otherViews = template.views.filter((v) => v.id !== ui.view && v.panels.some((p) => p.componentId === componentId));
  const inView = componentsInView(template, ui.view).has(componentId);
  const textureLayer = [...doc.layers].reverse().find((l) => l.type === 'texture' && l.targets.includes(componentId));
  const decos = doc.layers.filter((l) => l.type !== 'panelFill' && l.targets.includes(componentId));
  const isBaseColorway = ui.colorwayId === doc.colorways[0].id || !ui.colorwayId;

  const setFill = (patch: Partial<PanelFillLayer>, coalesce: string) =>
    update(
      (d) => {
        const l = target ? d.layers.find((x) => x.id === target.id) : undefined;
        if (l && l.type === 'panelFill') Object.assign(l, patch);
      },
      { coalesce },
    );

  return (
    <>
      <div className="section">
        <div className="section-title">Selected part</div>
        <h2>{comp.name}</h2>
        {!inView && <p className="hint">Not visible in the {ui.view} view.</p>}
      </div>
      <div className="section">
        <h3 style={{ marginBottom: 8 }}>Change {comp.name.toLowerCase()} color</h3>
        {!isBaseColorway && (
          <div className="callout info small" style={{ marginBottom: 8 }}>
            You are previewing colorway “{doc.colorways.find((c) => c.id === ui.colorwayId)?.name}”. Edits here change the base design; set colorway substitutions in Materials &amp; Colors.
          </div>
        )}
        <ColorPicker doc={doc} value={target?.colorId ?? null} onPick={(colorId) => setFill({ colorId }, `fill-${componentId}`)} label={`${comp.name} color`} />
        <div style={{ marginTop: 12 }}>
          {target?.view === 'all' && otherViews.length > 0 && (
            <p className="hint">
              Linked: this color applies to the {comp.name.toLowerCase()} in every view.{' '}
              <button
                className="btn sm"
                style={{ marginTop: 6 }}
                data-testid="make-view-different"
                onClick={() => {
                  if (!shared) return;
                  const o = makeViewOverride(doc, shared, ui.view);
                  update((d) => {
                    d.layers.push(o as Draft<Layer>);
                  });
                }}
              >
                Make different on {ui.view} only
              </button>
            </p>
          )}
          {target && target.view !== 'all' && (
            <div className="callout warn small">
              This part intentionally differs on the {ui.view} view.{' '}
              <button
                className="btn sm"
                onClick={() =>
                  update((d) => {
                    d.layers = d.layers.filter((l) => l.id !== target.id);
                  })
                }
              >
                Re-link to all views
              </button>
            </div>
          )}
        </div>
      </div>
      <div className="section">
        <Field label="Material" hint="Used for the BOM. Changing it updates the BOM reference immediately.">
          <select className="input" value={target?.materialId ?? ''} onChange={(e) => setFill({ materialId: e.target.value || null }, `mat-${componentId}`)} data-testid="part-material">
            <option value="">— No material —</option>
            {doc.materials.filter((m) => m.kind === 'fabric' || m.kind === 'rib' || m.kind === 'other').map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Fabric texture (appearance)" hint={fill.material?.textureId && !textureLayer ? `Using the material’s default look (${TEXTURES.find((t) => t.id === fill.material?.textureId)?.name}).` : undefined}>
          {textureLayer ? (
            <button className="btn sm" onClick={() => ui.selectLayer(textureLayer.id)}>
              Edit texture layer
            </button>
          ) : (
            <button className="btn sm" onClick={() => {
              const l = makeTextureLayer(template, fill.material?.textureId ?? 'jersey', [componentId], fill.material?.id ?? null);
              update((d) => { d.layers.push(l as Draft<Layer>); });
              ui.selectLayer(l.id);
            }}>
              Customize texture
            </button>
          )}
        </Field>
        <div className="small muted">Decoration methods supported here: {comp.decorationMethods.map((m) => DECORATION_METHOD_LABELS[m]).join(', ') || 'none'}</div>
      </div>
      {decos.length > 0 && (
        <div className="section">
          <div className="section-title">On this part</div>
          {decos.map((l) => (
            <button key={l.id} className="part-row" onClick={() => ui.selectLayer(l.id)}>
              <span className="badge">{layerTypeLabel(l.type)}</span>
              <span style={{ flex: 1 }}>{l.name}</span>
            </button>
          ))}
        </div>
      )}
    </>
  );
}

function CommonLayerControls({ layer, update }: { layer: Layer; update: Update }) {
  const ui = useUi();
  const set = (patch: Partial<Layer>, coalesce?: string) =>
    update(
      (d) => {
        const l = findLayer(d, layer.id);
        if (l) Object.assign(l, patch);
      },
      { coalesce },
    );
  return (
    <div className="section">
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="badge info">{layerTypeLabel(layer.type)}</span>
        <span className="small muted">{layer.view === 'all' ? 'All views' : `${layer.view} view`}</span>
        <div className="spacer" />
        <button className="btn sm icon" aria-label={layer.visible ? 'Hide' : 'Show'} title={layer.visible ? 'Hide' : 'Show'} onClick={() => set({ visible: !layer.visible })}>
          <Icon name={layer.visible ? 'eye' : 'eyeOff'} size={14} />
        </button>
        <button className="btn sm icon" aria-label={layer.locked ? 'Unlock' : 'Lock'} title={layer.locked ? 'Unlock' : 'Lock'} onClick={() => set({ locked: !layer.locked })}>
          <Icon name={layer.locked ? 'lock' : 'unlock'} size={14} />
        </button>
        {layer.type !== 'panelFill' && (
          <>
            <button
              className="btn sm icon"
              aria-label="Duplicate"
              title="Duplicate (Ctrl/⌘+D)"
              onClick={() => {
                const copy = { ...JSON.parse(JSON.stringify(layer)), id: newId('lyr'), name: `${layer.name} copy` } as Layer;
                if (copy.type === 'artwork' || copy.type === 'hardware') {
                  copy.transform.x += 20;
                  copy.transform.y += 20;
                }
                update((d) => {
                  const i = d.layers.findIndex((l) => l.id === layer.id);
                  d.layers.splice(i + 1, 0, copy as Draft<Layer>);
                });
                ui.selectLayer(copy.id);
              }}
            >
              <Icon name="copy" size={14} />
            </button>
            <button
              className="btn sm icon danger"
              aria-label="Delete layer"
              title="Delete"
              data-testid="delete-layer"
              onClick={() => {
                update((d) => {
                  d.layers = d.layers.filter((l) => l.id !== layer.id);
                });
                ui.selectLayer(null);
              }}
            >
              <Icon name="trash" size={14} />
            </button>
          </>
        )}
      </div>
      <Field label="Name">
        <TextInput value={layer.name} onCommit={(name) => name.trim() && set({ name: name.trim() })} ariaLabel="Layer name" />
      </Field>
      {layer.type !== 'panelFill' && (
        <Field label={`Opacity ${Math.round(layer.opacity * 100)}%`}>
          <input type="range" min={0} max={1} step={0.01} value={layer.opacity} onChange={(e) => set({ opacity: Number(e.target.value) }, `op-${layer.id}`)} aria-label="Opacity" />
        </Field>
      )}
      {layer.locked && <div className="callout info small">Locked — unlock to move or edit on the canvas.</div>}
    </div>
  );
}

function TargetsPicker({ layer, update, viewOnly }: { layer: Layer; update: Update; viewOnly?: boolean }) {
  const { template } = useProject();
  const ui = useUi();
  const comps = viewOnly ? template!.components.filter((c) => componentsInView(template!, layer.view === 'all' ? ui.view : layer.view).has(c.id)) : template!.components;
  return (
    <div className="field">
      <span className="label">Panels</span>
      {comps.map((c) => (
        <label key={c.id} className="row small" style={{ gap: 6 }}>
          <input
            type="checkbox"
            checked={layer.targets.includes(c.id)}
            onChange={(e) =>
              update((d) => {
                const l = findLayer(d, layer.id);
                if (!l) return;
                l.targets = e.target.checked ? [...l.targets, c.id] : l.targets.filter((t) => t !== c.id);
              })
            }
          />
          {c.name}
        </label>
      ))}
    </div>
  );
}

function MaskControls({ layer, update }: { layer: Extract<Layer, { mask: unknown[] }>; update: Update }) {
  const ui = useUi();
  const tool = ui.tool;
  const erasing = tool.kind === 'erase';
  const noun = layer.type === 'pattern' ? 'pattern' : layer.type === 'texture' ? 'texture' : 'artwork';
  return (
    <div className="section">
      <div className="section-title">Erase (non-destructive)</div>
      <div className="row wrap">
        <button className={`btn sm${erasing && tool.mode === 'erase' ? ' active' : ''}`} data-testid="erase-tool" onClick={() => ui.set({ tool: erasing && tool.mode === 'erase' ? { kind: 'select' } : { kind: 'erase', mode: 'erase', size: erasing ? tool.size : 30 } })}>
          Erase from this {noun}
        </button>
        <button className={`btn sm${erasing && tool.mode === 'restore' ? ' active' : ''}`} onClick={() => ui.set({ tool: erasing && tool.mode === 'restore' ? { kind: 'select' } : { kind: 'erase', mode: 'restore', size: erasing ? tool.size : 30 } })}>
          Restore
        </button>
      </div>
      {erasing && (
        <div className="field" style={{ marginTop: 8 }}>
          <span className="label">Brush size</span>
          <input type="range" min={6} max={120} value={tool.size} onChange={(e) => ui.set({ tool: { ...tool, size: Number(e.target.value) } })} aria-label="Brush size" />
        </div>
      )}
      <p className="hint" style={{ margin: '6px 0' }}>
        Only this {noun} is affected. The garment color and other layers are never erased. {layer.mask.length} edit{layer.mask.length === 1 ? '' : 's'} stored.
      </p>
      <button
        className="btn sm"
        disabled={!layer.mask.length}
        data-testid="reset-mask"
        onClick={() =>
          update((d) => {
            const l = findLayer(d, layer.id);
            if (l && 'mask' in l) l.mask = [];
          })
        }
      >
        Reset erased areas
      </button>
    </div>
  );
}

function ArtworkInspector({ layer }: { layer: ArtworkLayer }) {
  const { doc, template, update } = useProject();
  const unit = doc!.displayUnit;
  const view = getView(template!, layer.view === 'all' ? 'front' : layer.view);
  const anchor = findAnchor(template!, layer.placement.anchorId);
  const asset = doc!.assets.find((a) => a.id === layer.assetId);
  const setPlacement = (patch: Partial<ArtworkLayer['placement']>) =>
    update((d) => {
      const i = d.layers.findIndex((l) => l.id === layer.id);
      d.layers[i] = applyEnteredPlacement(template!, d.layers[i] as ArtworkLayer, patch) as Draft<Layer>;
    });
  const setDeco = (patch: Partial<ArtworkLayer['decoration']>, coalesce?: string) =>
    update(
      (d) => {
        const l = findLayer(d, layer.id);
        if (l?.type === 'artwork') Object.assign(l.decoration, patch);
      },
      { coalesce },
    );
  const unsupported = layer.targets.filter((t) => !template!.components.find((c) => c.id === t)?.decorationMethods.includes(layer.decoration.method));
  return (
    <>
      <div className="section">
        <div className="section-title">Source file</div>
        {asset ? (
          <div className="small">
            {asset.filename} · {asset.kind.toUpperCase()} · {Math.round(asset.width)}×{Math.round(asset.height)}
            <div className="hint">Kept intact — edits are stored separately and never flatten the file.</div>
          </div>
        ) : (
          <div className="callout err small">The source file is missing. Re-upload the artwork (Add logo) and delete this layer.</div>
        )}
      </div>
      <div className="section" data-testid="placement-section">
        <div className="row" style={{ marginBottom: 8 }}>
          <h3 style={{ flex: 1 }}>Manufacturing placement</h3>
          {layer.placement.source === 'entered' ? <span className="badge ok">Entered</span> : <span className="badge warn" data-testid="visual-estimate">Visual estimate</span>}
        </div>
        {layer.placement.source !== 'entered' && (
          <p className="hint" style={{ marginBottom: 8 }}>
            Values below are estimated from the drawing ({template!.calibration ? `nominal scale, size ${template!.calibration.baseSize}` : 'uncalibrated'}). Type or confirm the finished size to make them a manufacturing spec.
          </p>
        )}
        <div className="grid2">
          <Field label={`Finished width (${unit})`}>
            <LengthInput mm={layer.placement.widthMm} unit={unit} min={1} onCommit={(v) => v !== null && setPlacement({ widthMm: v })} ariaLabel="Finished width" />
          </Field>
          <Field label={`Finished height (${unit})`}>
            <LengthInput mm={layer.placement.heightMm} unit={unit} min={1} onCommit={(v) => v !== null && setPlacement({ heightMm: v })} ariaLabel="Finished height" />
          </Field>
        </div>
        <Field label="Measured from">
          <select className="input" value={layer.placement.anchorId ?? ''} onChange={(e) => setPlacement({ anchorId: e.target.value || null })} aria-label="Reference point">
            {view.anchors.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Point on artwork">
          <select className="input" value={layer.placement.reference} onChange={(e) => setPlacement({ reference: e.target.value as 'center' | 'top-center' })}>
            <option value="top-center">Top edge (center)</option>
            <option value="center">Center</option>
          </select>
        </Field>
        <div className="grid2">
          <Field label={`Down from point (${unit})`} hint="Negative = above">
            <LengthInput mm={layer.placement.offsetYmm} unit={unit} onCommit={(v) => v !== null && setPlacement({ offsetYmm: v })} ariaLabel="Vertical offset" />
          </Field>
          <Field label={`Toward wearer’s left (${unit})`} hint="Negative = wearer’s right">
            <LengthInput mm={layer.placement.offsetXmm} unit={unit} onCommit={(v) => v !== null && setPlacement({ offsetXmm: v })} ariaLabel="Horizontal offset" />
          </Field>
        </div>
        <Field label={`Placement tolerance ± (${unit})`}>
          <LengthInput mm={layer.placement.toleranceMm} unit={unit} allowEmpty min={0} onCommit={(v) => setPlacement({ toleranceMm: v })} ariaLabel="Placement tolerance" />
        </Field>
        {layer.placement.source !== 'entered' && (
          <button className="btn sm primary" onClick={() => setPlacement({})} data-testid="confirm-placement">
            Use these values for manufacturing
          </button>
        )}
        {anchor && <p className="hint" style={{ marginTop: 6 }}>{anchor.description}</p>}
        <div className="row" style={{ marginTop: 8 }}>
          <span className="small muted">Rotation</span>
          <NumberInput value={layer.transform.rotation} step={1} min={-180} max={180} suffix="°" ariaLabel="Rotation" onCommit={(rotation) => update((d) => { const l = findLayer(d, layer.id); if (l?.type === 'artwork') l.transform.rotation = rotation; })} />
        </div>
        <label className="row small" style={{ marginTop: 8 }}>
          <input type="checkbox" checked={layer.lockAspect} onChange={(e) => update((d) => { const l = findLayer(d, layer.id); if (l?.type === 'artwork') l.lockAspect = e.target.checked; })} />
          Keep proportions
        </label>
      </div>
      <div className="section">
        <h3 style={{ marginBottom: 8 }}>Clipping</h3>
        <label className="row small" style={{ marginBottom: 6 }}>
          <input type="checkbox" checked={layer.clipToTargets} onChange={(e) => update((d) => { const l = findLayer(d, layer.id); if (l?.type === 'artwork') l.clipToTargets = e.target.checked; })} />
          Clip to the panels below (outlined in purple)
        </label>
        <TargetsPicker layer={layer} update={update} viewOnly />
        {layer.targets.length > 1 && <p className="hint">This graphic spans {layer.targets.length} panels and is cut at their seams.</p>}
      </div>
      <div className="section">
        <h3 style={{ marginBottom: 8 }}>Decoration</h3>
        <Field label="Method">
          <select className="input" value={layer.decoration.method} onChange={(e) => setDeco({ method: e.target.value as DecorationMethod })} data-testid="decoration-method">
            {Object.entries(DECORATION_METHOD_LABELS)
              .filter(([k]) => k !== 'rhinestone' && k !== 'stud')
              .map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
          </select>
        </Field>
        {unsupported.length > 0 && <div className="callout warn small" style={{ marginBottom: 8 }}>{DECORATION_METHOD_LABELS[layer.decoration.method]} isn’t supported on {unsupported.map((t) => componentName(template!, t)).join(', ')} for this garment.</div>}
        <Field label="Artwork ID">
          <TextInput value={layer.decoration.artworkCode} onCommit={(artworkCode) => setDeco({ artworkCode })} ariaLabel="Artwork ID" placeholder="e.g. ART-001" />
        </Field>
        <Field label="Ink / thread colors">
          <div className="row wrap" style={{ gap: 4 }}>
            {doc!.colors.map((c) => (
              <label key={c.id} className="row small" style={{ gap: 4, marginRight: 8 }}>
                <input type="checkbox" checked={layer.decoration.colorIds.includes(c.id)} onChange={(e) => setDeco({ colorIds: e.target.checked ? [...layer.decoration.colorIds, c.id] : layer.decoration.colorIds.filter((x) => x !== c.id) })} />
                <span className="swatch" style={{ background: c.hex }} /> {c.name}
              </label>
            ))}
          </div>
        </Field>
        <Field label="Artwork notes">
          <TextInput multiline value={layer.decoration.notes} onCommit={(notes) => setDeco({ notes })} ariaLabel="Artwork notes" />
        </Field>
      </div>
      <MaskControls layer={layer} update={update} />
    </>
  );
}

function PatternInspector({ layer }: { layer: Extract<Layer, { type: 'pattern' }> }) {
  const { doc, update } = useProject();
  const unit = doc!.displayUnit;
  const set = (patch: Partial<typeof layer>, coalesce?: string) =>
    update(
      (d) => {
        const l = findLayer(d, layer.id);
        if (l) Object.assign(l, patch);
      },
      { coalesce },
    );
  return (
    <>
      <div className="section">
        <h3 style={{ marginBottom: 8 }}>Pattern repeat</h3>
        <Field label={`Repeat width (${unit})`} hint="Physical width of one tile on the finished garment.">
          <LengthInput mm={layer.tileWidthMm} unit={unit} min={2} onCommit={(v) => v && set({ tileWidthMm: v })} ariaLabel="Repeat width" />
        </Field>
        <Field label={`Rotation ${layer.rotation}°`}>
          <input type="range" min={-180} max={180} value={layer.rotation} onChange={(e) => set({ rotation: Number(e.target.value) }, `prot-${layer.id}`)} aria-label="Pattern rotation" />
        </Field>
        <div className="grid2">
          <Field label={`Horizontal offset (${unit})`}>
            <LengthInput mm={layer.offsetXmm} unit={unit} onCommit={(v) => v !== null && set({ offsetXmm: v })} ariaLabel="Horizontal offset" />
          </Field>
          <Field label={`Vertical offset (${unit})`}>
            <LengthInput mm={layer.offsetYmm} unit={unit} onCommit={(v) => v !== null && set({ offsetYmm: v })} ariaLabel="Vertical offset" />
          </Field>
        </div>
        <Field label="Print method">
          <select className="input" value={layer.method} onChange={(e) => set({ method: e.target.value as DecorationMethod })}>
            {(['sublimation', 'screen-print', 'dtg', 'heat-transfer'] as DecorationMethod[]).map((m) => (
              <option key={m} value={m}>
                {DECORATION_METHOD_LABELS[m]}
              </option>
            ))}
          </select>
        </Field>
        <TargetsPicker layer={layer} update={update} />
        <Field label="Notes">
          <TextInput multiline value={layer.notes} onCommit={(notes) => set({ notes })} ariaLabel="Pattern notes" />
        </Field>
      </div>
      <MaskControls layer={layer} update={update} />
    </>
  );
}

function TextureInspector({ layer }: { layer: Extract<Layer, { type: 'texture' }> }) {
  const { doc, update } = useProject();
  const set = (patch: Partial<typeof layer>, coalesce?: string) =>
    update(
      (d) => {
        const l = findLayer(d, layer.id);
        if (l) Object.assign(l, patch);
      },
      { coalesce },
    );
  return (
    <>
      <div className="section">
        <Field label="Texture">
          <select className="input" value={layer.textureId} onChange={(e) => set({ textureId: e.target.value })}>
            {TEXTURES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label={`Appearance scale ×${layer.scale.toFixed(1)}`}>
          <input type="range" min={0.3} max={4} step={0.1} value={layer.scale} onChange={(e) => set({ scale: Number(e.target.value) }, `ts-${layer.id}`)} aria-label="Texture scale" />
        </Field>
        <Field label={`Strength ${Math.round(layer.strength * 100)}%`}>
          <input type="range" min={0} max={1} step={0.05} value={layer.strength} onChange={(e) => set({ strength: Number(e.target.value) }, `tst-${layer.id}`)} aria-label="Texture strength" />
        </Field>
        <Field label="Represents material" hint="Links this look to the material specification used in the BOM.">
          <select className="input" value={layer.materialId ?? ''} onChange={(e) => set({ materialId: e.target.value || null })}>
            <option value="">— Appearance only —</option>
            {doc!.materials.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>
        <TargetsPicker layer={layer} update={update} />
        <p className="hint">Textures are appearance previews; the material record is the specification.</p>
      </div>
      <MaskControls layer={layer} update={update} />
    </>
  );
}

function StitchingInspector({ layer }: { layer: Extract<Layer, { type: 'stitching' }> }) {
  const { doc, template, update } = useProject();
  const set = (patch: Partial<typeof layer>) =>
    update((d) => {
      const l = findLayer(d, layer.id);
      if (l) Object.assign(l, patch);
    });
  const seams = new Map<string, string>();
  for (const v of template!.views) for (const s of v.seams) if (!seams.has(s.id)) seams.set(s.id, s.name);
  return (
    <div className="section">
      <div className="callout info small" style={{ marginBottom: 10 }}>
        The dashed line is an illustration. Stitch type, SPI and seam construction are specified only by the manufacturing notes below.
      </div>
      <Field label="Thread color">
        <ColorPicker doc={doc!} value={layer.colorId} onPick={(colorId) => set({ colorId })} label="Thread color" />
      </Field>
      <Field label="Visual style">
        <select className="input" value={layer.style} onChange={(e) => set({ style: e.target.value as StitchStyle })}>
          {Object.entries(STITCH_STYLE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Seams">
        <div style={{ maxHeight: 180, overflow: 'auto' }}>
          {[...seams].map(([id, name]) => (
            <label key={id} className="row small" style={{ gap: 6 }}>
              <input
                type="checkbox"
                checked={layer.seamIds.includes(id)}
                onChange={(e) => {
                  const next = e.target.checked ? [...layer.seamIds, id] : layer.seamIds.filter((s) => s !== id);
                  if (next.length) set({ seamIds: next });
                }}
              />
              {name}
            </label>
          ))}
        </div>
      </Field>
      <Field label="Manufacturing notes" hint="e.g. 2-needle coverstitch, 6 mm gauge, 12 SPI">
        <TextInput multiline value={layer.notes} onCommit={(notes) => set({ notes })} ariaLabel="Stitching manufacturing notes" />
      </Field>
    </div>
  );
}

function EmbellishmentInspector({ layer }: { layer: Extract<Layer, { type: 'embellishment' }> }) {
  const { doc, template, update } = useProject();
  const ui = useUi();
  const unit = doc!.displayUnit;
  const set = (patch: Partial<typeof layer>, coalesce?: string) =>
    update(
      (d) => {
        const l = findLayer(d, layer.id);
        if (l) Object.assign(l, patch);
      },
      { coalesce },
    );
  const sizes = layer.kind === 'rhinestone' ? RHINESTONE_SIZES : STUD_SIZES;
  const finishes = layer.kind === 'rhinestone' ? RHINESTONE_FINISHES : STUD_FINISHES;
  const count = embellishmentCount(layer, template!);
  const placing = ui.tool.kind === 'place-embellishment';
  const drawing = ui.tool.kind === 'draw-path';
  return (
    <>
      <div className="section">
        <div className="row" style={{ marginBottom: 8 }}>
          <h3 style={{ flex: 1 }}>{layer.kind === 'rhinestone' ? 'Rhinestones' : 'Studs'}</h3>
          <span className="badge info" data-testid="emb-count-badge">
            {count} placed · counted in BOM
          </span>
        </div>
        <div className="row wrap" style={{ marginBottom: 8 }}>
          <button className={`btn sm${placing ? ' active' : ''}`} data-testid="place-individually" onClick={() => ui.set({ tool: placing ? { kind: 'select' } : { kind: 'place-embellishment' } })}>
            Place individually
          </button>
          <button className={`btn sm${drawing ? ' active' : ''}`} data-testid="draw-path" onClick={() => ui.set({ tool: drawing ? { kind: 'select' } : { kind: 'draw-path', points: [] } })}>
            Draw a path
          </button>
        </div>
        {drawing && ui.tool.kind === 'draw-path' && (
          <div className="row" style={{ marginBottom: 8 }}>
            <span className="small muted">{ui.tool.points.length} point(s)</span>
            <button className="btn sm primary" disabled={ui.tool.points.length < 2} data-testid="finish-path" onClick={() => {
              const t = ui.tool;
              if (t.kind !== 'draw-path') return;
              update((d) => {
                const l = findLayer(d, layer.id);
                if (l?.type === 'embellishment') {
                  l.paths.push({ id: newId('pth'), points: t.points, spacingMm: Math.max(l.diameterMm * 2, 6) });
                  if (l.view !== ui.view) l.view = ui.view;
                }
              });
              ui.set({ tool: { kind: 'select' } });
            }}>
              Finish path
            </button>
          </div>
        )}
        <Field label="Size">
          <select className="input" value={sizes.find((s) => Math.abs(s.diameterMm - layer.diameterMm) < 0.05)?.label ?? 'custom'} onChange={(e) => {
            const s = sizes.find((x) => x.label === e.target.value);
            if (s) set({ diameterMm: s.diameterMm });
          }}>
            {sizes.map((s) => (
              <option key={s.label} value={s.label}>
                {s.label} ({s.diameterMm} mm)
              </option>
            ))}
            <option value="custom" disabled>
              Custom
            </option>
          </select>
        </Field>
        <Field label={`Diameter (${unit})`}>
          <LengthInput mm={layer.diameterMm} unit={unit} min={0.5} onCommit={(v) => v && set({ diameterMm: v })} ariaLabel="Diameter" />
        </Field>
        <Field label="Finish">
          <select className="input" value={layer.finish} onChange={(e) => set({ finish: e.target.value })}>
            {finishes.map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
        </Field>
        <Field label="Attachment">
          <select className="input" value={layer.attachment} onChange={(e) => set({ attachment: e.target.value as typeof layer.attachment })}>
            <option value="hotfix">Hotfix (heat applied)</option>
            <option value="prong-set">Prong set</option>
            <option value="sew-on">Sew-on</option>
            <option value="glue-on">Glue-on</option>
          </select>
        </Field>
        {layer.paths.map((p, i) => (
          <div key={p.id} className="row" style={{ marginBottom: 6 }}>
            <span className="small" style={{ flex: 1 }}>Path {i + 1} spacing ({unit})</span>
            <div style={{ width: 90 }}>
              <LengthInput mm={p.spacingMm} unit={unit} min={0.5} onCommit={(v) => v && update((d) => { const l = findLayer(d, layer.id); if (l?.type === 'embellishment') l.paths[i].spacingMm = v; })} ariaLabel={`Path ${i + 1} spacing`} />
            </div>
            <button className="btn sm icon" aria-label={`Delete path ${i + 1}`} onClick={() => update((d) => { const l = findLayer(d, layer.id); if (l?.type === 'embellishment') l.paths.splice(i, 1); })}>
              <Icon name="trash" size={14} />
            </button>
          </div>
        ))}
        <div className="row wrap">
          <button className="btn sm" disabled={!layer.points.length} onClick={() => set({ points: layer.points.slice(0, -1) })}>
            Remove last placed
          </button>
          <button className="btn sm" disabled={!layer.points.length && !layer.paths.length} onClick={() => set({ points: [], paths: [] })}>
            Clear all
          </button>
        </div>
        <Field label="Notes">
          <TextInput multiline value={layer.notes} onCommit={(notes) => set({ notes })} ariaLabel="Embellishment notes" />
        </Field>
        <p className="hint">Placements stay editable. Alt+click a placed item to remove it. This is an appearance preview, not a machine file.</p>
      </div>
    </>
  );
}

function HardwareInspector({ layer }: { layer: Extract<Layer, { type: 'hardware' }> }) {
  const { doc, template, update } = useProject();
  const def = getHardware(layer.hardwareId);
  const unit = doc!.displayUnit;
  const set = (patch: Partial<typeof layer>) =>
    update((d) => {
      const l = findLayer(d, layer.id);
      if (l) Object.assign(l, patch);
    });
  return (
    <div className="section">
      <div className="callout warn small" style={{ marginBottom: 10 }}>
        {def?.structuralNote ?? 'Visual placement only.'} Garment construction remains: {template!.structure.closure}.
      </div>
      <Field label="Component">
        <select className="input" value={layer.hardwareId} onChange={(e) => {
          const nd = getHardware(e.target.value)!;
          set({ hardwareId: nd.id, finish: nd.finishes[0], name: nd.name });
        }}>
          {HARDWARE.map((h) => (
            <option key={h.id} value={h.id}>
              {h.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Finish">
        <select className="input" value={layer.finish} onChange={(e) => set({ finish: e.target.value })}>
          {(def?.finishes ?? [layer.finish]).map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
      </Field>
      <Field label={`Size (${unit})`} hint="Longest dimension. Updates the drawing.">
        <LengthInput mm={layer.sizeMm} unit={unit} min={1} onCommit={(v) => {
          if (!v || !def) return;
          const k = template!.calibration?.mmPerUnit ?? 1;
          const h = v / k;
          update((d) => {
            const l = findLayer(d, layer.id);
            if (l?.type !== 'hardware') return;
            l.sizeMm = v;
            l.transform.width = def.aspect >= 1 ? h : h * def.aspect;
            l.transform.height = def.aspect >= 1 ? h / def.aspect : h;
          });
        }} ariaLabel="Hardware size" />
      </Field>
      <Field label="Notes">
        <TextInput multiline value={layer.notes} onCommit={(notes) => set({ notes })} ariaLabel="Hardware notes" />
      </Field>
    </div>
  );
}

function AnnotationInspector({ layer }: { layer: Extract<Layer, { type: 'annotation' }> }) {
  const { update } = useProject();
  return (
    <div className="section">
      <Field label="Note text" hint="Appears on the canvas and as a numbered callout in the tech pack.">
        <TextInput multiline value={layer.text} onCommit={(text) => text.trim() && update((d) => { const l = findLayer(d, layer.id); if (l?.type === 'annotation') { l.text = text.trim(); l.name = text.trim().slice(0, 40); } })} ariaLabel="Note text" />
      </Field>
    </div>
  );
}

function PanelFillInspector({ layer }: { layer: PanelFillLayer }) {
  const { doc, update } = useProject();
  return (
    <div className="section">
      <Field label="Color">
        <ColorPicker doc={doc!} value={layer.colorId} onPick={(colorId) => update((d) => { const l = findLayer(d, layer.id); if (l?.type === 'panelFill') l.colorId = colorId; })} />
      </Field>
    </div>
  );
}

export function Inspector() {
  const { doc, template, update } = useProject();
  const ui = useUi();
  if (!doc || !template) return null;
  const layer = doc.layers.find((l) => l.id === ui.selectedLayerId);
  let body: React.ReactNode;
  if (layer) {
    body = (
      <>
        <CommonLayerControls layer={layer} update={update} />
        {layer.type === 'artwork' && <ArtworkInspector layer={layer} />}
        {layer.type === 'pattern' && <PatternInspector layer={layer} />}
        {layer.type === 'texture' && <TextureInspector layer={layer} />}
        {layer.type === 'stitching' && <StitchingInspector layer={layer} />}
        {layer.type === 'embellishment' && <EmbellishmentInspector layer={layer} />}
        {layer.type === 'hardware' && <HardwareInspector layer={layer} />}
        {layer.type === 'annotation' && <AnnotationInspector layer={layer} />}
        {layer.type === 'panelFill' && <PanelFillInspector layer={layer} />}
      </>
    );
  } else if (ui.selectedComponentId) {
    body = <ComponentInspector componentId={ui.selectedComponentId} />;
  } else {
    body = (
      <div className="section">
        <h3 style={{ marginBottom: 6 }}>Nothing selected</h3>
        <p className="hint" style={{ marginBottom: 10 }}>
          Click a part of the garment to change its color or material, or click a graphic to move, resize, and specify it.
        </p>
        <div className="callout info small">
          Garment structure: {template.structure.closure} · {template.structure.features.join(', ')}. Decorations never change this construction.
        </div>
      </div>
    );
  }
  return (
    <aside className="side right" aria-label="Selected item settings" data-testid="inspector">
      {body}
    </aside>
  );
}
