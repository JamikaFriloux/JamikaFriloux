import React, { useMemo, useState } from 'react';
import type { Draft } from 'immer';
import type { BomItem, Color, Material, PanelFillLayer, ProjectDoc } from '../../shared/schema/project';
import { computeBom, colorwayNames } from '../../shared/domain/bom';
import { resolveFill } from '../../shared/domain/design';
import { newId } from '../../shared/domain/ids';
import { TEXTURES } from '../../shared/catalog/textures';
import { useProject } from '../store/project';
import { useUi } from '../store/ui';
import { NumberInput, TextInput } from '../components/common';
import { Icon } from '../components/Icon';

function usedColorIds(doc: ProjectDoc): Set<string> {
  const s = new Set<string>();
  for (const l of doc.layers) {
    if (l.type === 'panelFill' || l.type === 'stitching') s.add(l.colorId);
    if (l.type === 'embellishment' && l.colorId) s.add(l.colorId);
    if (l.type === 'artwork') l.decoration.colorIds.forEach((c) => s.add(c));
  }
  for (const cw of doc.colorways) Object.entries(cw.colorSubs).forEach(([a, b]) => (s.add(a), s.add(b)));
  return s;
}
function usedMaterialIds(doc: ProjectDoc): Set<string> {
  const s = new Set<string>();
  for (const l of doc.layers) {
    if (l.type === 'panelFill' && l.materialId) s.add(l.materialId);
    if (l.type === 'texture' && l.materialId) s.add(l.materialId);
    if (l.type === 'stitching' && l.threadMaterialId) s.add(l.threadMaterialId);
  }
  for (const b of doc.bomItems) if (b.materialId) s.add(b.materialId);
  for (const lb of doc.labels) if (lb.materialId) s.add(lb.materialId);
  for (const cw of doc.colorways) Object.entries(cw.materialSubs).forEach(([a, b]) => (s.add(a), s.add(b)));
  return s;
}

export function MaterialsPage() {
  const { doc, template, update } = useProject();
  const ui = useUi();
  const bom = useMemo(() => (doc && template ? computeBom(doc, template) : []), [doc, template]);
  const [tab, setTab] = useState<'palette' | 'materials' | 'assign' | 'colorways' | 'bom'>('assign');
  if (!doc || !template) return null;
  const usedC = usedColorIds(doc);
  const usedM = usedMaterialIds(doc);

  const setColor = (id: string, patch: Partial<Color>, coalesce?: string) =>
    update((d) => void Object.assign(d.colors.find((c) => c.id === id)!, patch), { coalesce });
  const setMat = (id: string, patch: Partial<Material>, coalesce?: string) =>
    update((d) => void Object.assign(d.materials.find((m) => m.id === id)!, patch), { coalesce });

  const tabs = [
    ['assign', 'Component assignments'],
    ['palette', `Palette (${doc.colors.length})`],
    ['materials', `Materials (${doc.materials.length})`],
    ['colorways', `Colorways (${doc.colorways.length})`],
    ['bom', `BOM (${bom.length})`],
  ] as const;

  return (
    <main className="page">
      <div className="page-inner" style={{ maxWidth: 1400 }}>
        <div className="title-row">
          <h1>Materials &amp; Colors</h1>
          <div className="seg" role="tablist">
            {tabs.map(([k, label]) => (
              <button key={k} role="tab" aria-pressed={tab === k} aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`mc-tab-${k}`}>
                {label}
              </button>
            ))}
          </div>
        </div>

        {tab === 'assign' && (
          <div className="card">
            <div className="section">
              <h2>Component assignments</h2>
              <p className="hint">The same assignments drive the design canvas, the BOM, and the tech pack. Change a part’s color or material here or in the Design Studio.</p>
            </div>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Part</th>
                    <th>Color (base design)</th>
                    <th>Material</th>
                    {doc.colorways.slice(1).map((cw) => (
                      <th key={cw.id}>{cw.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {template.components.map((c) => {
                    const fill = doc.layers.find((l): l is PanelFillLayer => l.type === 'panelFill' && l.view === 'all' && l.targets[0] === c.id);
                    const overrides = doc.layers.filter((l): l is PanelFillLayer => l.type === 'panelFill' && l.view !== 'all' && l.targets[0] === c.id);
                    return (
                      <tr key={c.id}>
                        <td>
                          <strong>{c.name}</strong>
                          {overrides.map((o) => (
                            <div key={o.id} className="small" style={{ color: 'var(--warn)' }}>
                              Differs on {o.view}: {doc.colors.find((x) => x.id === o.colorId)?.name}
                            </div>
                          ))}
                        </td>
                        <td>
                          <div className="row">
                            <span className="swatch" style={{ background: doc.colors.find((x) => x.id === fill?.colorId)?.hex }} />
                            <select className="input sm" value={fill?.colorId ?? ''} onChange={(e) => update((d) => { const l = d.layers.find((x) => x.id === fill?.id); if (l?.type === 'panelFill') l.colorId = e.target.value; })} aria-label={`${c.name} color`}>
                              {doc.colors.map((col) => (
                                <option key={col.id} value={col.id}>
                                  {col.name}
                                </option>
                              ))}
                            </select>
                          </div>
                        </td>
                        <td>
                          <select className="input sm" value={fill?.materialId ?? ''} onChange={(e) => update((d) => { const l = d.layers.find((x) => x.id === fill?.id); if (l?.type === 'panelFill') l.materialId = e.target.value || null; })} aria-label={`${c.name} material`} data-testid={`assign-mat-${c.id}`}>
                            <option value="">— none —</option>
                            {doc.materials.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        {doc.colorways.slice(1).map((cw) => {
                          const view = template.views.find((v) => v.panels.some((p) => p.componentId === c.id))!.id;
                          const f = resolveFill(doc, c.id, view, cw.id);
                          return (
                            <td key={cw.id}>
                              <div className="row small">
                                <span className="swatch" style={{ background: f.hex }} />
                                {f.color?.name} · {f.material?.name ?? '—'}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'palette' && (
          <div className="card">
            <div className="section row">
              <div style={{ flex: 1 }}>
                <h2>Palette</h2>
                <p className="hint">Screen colors are display approximations. Record your own color-standard reference (e.g. a lab-dip or color-system code you have verified); none is generated automatically.</p>
              </div>
              <button className="btn primary sm" onClick={() => update((d) => void d.colors.push({ id: newId('col'), name: `Color ${d.colors.length + 1}`, hex: '#888888', standard: null, approval: 'not-submitted' }))}>
                <Icon name="plus" size={14} /> Add color
              </button>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Screen value</th>
                  <th>Name</th>
                  <th>Standard system</th>
                  <th>Standard code</th>
                  <th>Approval status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {doc.colors.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <div className="row">
                        <input type="color" value={c.hex} onChange={(e) => setColor(c.id, { hex: e.target.value }, `hex-${c.id}`)} aria-label={`${c.name} screen color`} />
                        <span className="mono small">{c.hex.toUpperCase()}</span>
                      </div>
                    </td>
                    <td>
                      <TextInput value={c.name} onCommit={(name) => name.trim() && setColor(c.id, { name: name.trim() })} ariaLabel="Color name" />
                    </td>
                    <td>
                      <TextInput value={c.standard?.system ?? ''} placeholder="e.g. your lab dip / color system" onCommit={(system) => setColor(c.id, { standard: system.trim() || c.standard?.code ? { system: system.trim(), code: c.standard?.code ?? '' } : null })} ariaLabel="Color standard system" />
                    </td>
                    <td>
                      <TextInput value={c.standard?.code ?? ''} placeholder="Code you supply" onCommit={(code) => setColor(c.id, { standard: code.trim() || c.standard?.system ? { system: c.standard?.system ?? '', code: code.trim() } : null })} ariaLabel="Color standard code" />
                    </td>
                    <td>
                      <select className="input sm" value={c.approval} onChange={(e) => setColor(c.id, { approval: e.target.value as Color['approval'] })} aria-label="Approval status">
                        <option value="not-submitted">Not submitted</option>
                        <option value="submitted">Submitted</option>
                        <option value="approved">Approved (by you)</option>
                        <option value="rejected">Rejected</option>
                      </select>
                    </td>
                    <td>
                      <button className="btn sm icon ghost" aria-label={`Delete ${c.name}`} disabled={usedC.has(c.id) || doc.colors.length === 1} title={usedC.has(c.id) ? 'In use — reassign before deleting' : 'Delete'} onClick={() => update((d) => void (d.colors = d.colors.filter((x) => x.id !== c.id)))}>
                        <Icon name="trash" size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === 'materials' && (
          <div className="card">
            <div className="section row">
              <div style={{ flex: 1 }}>
                <h2>Materials</h2>
                <p className="hint">Composition and weight are required for a manufacturer-review export when a material is used on the garment.</p>
              </div>
              <button className="btn primary sm" onClick={() => update((d) => void d.materials.push({ id: newId('mat'), name: 'New material', kind: 'fabric', composition: '', weight: null, finish: '', supplier: '', supplierRef: '', textureId: null, notes: '' }))}>
                <Icon name="plus" size={14} /> Add material
              </button>
            </div>
            {doc.materials.map((m) => (
              <div className="section" key={m.id} data-testid={`material-${m.id}`}>
                <div className="grid3">
                  <div className="field">
                    <span className="label">Name</span>
                    <TextInput value={m.name} onCommit={(name) => name.trim() && setMat(m.id, { name: name.trim() })} ariaLabel="Material name" />
                  </div>
                  <div className="field">
                    <span className="label">Type</span>
                    <select className="input" value={m.kind} onChange={(e) => setMat(m.id, { kind: e.target.value as Material['kind'] })}>
                      {['fabric', 'rib', 'trim', 'thread', 'label', 'packaging', 'other'].map((k) => (
                        <option key={k}>{k}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <span className="label">Composition</span>
                    <TextInput value={m.composition} placeholder="e.g. 100% cotton" onCommit={(composition) => setMat(m.id, { composition })} ariaLabel="Composition" />
                  </div>
                  <div className="field">
                    <span className="label">Weight</span>
                    <div className="row">
                      <input
                        className="input"
                        type="number"
                        min={0}
                        defaultValue={m.weight?.value ?? ''}
                        key={`${m.id}-${m.weight?.value}`}
                        aria-label="Fabric weight"
                        onBlur={(e) => {
                          const v = Number(e.target.value);
                          setMat(m.id, { weight: e.target.value && v > 0 ? { value: v, unit: m.weight?.unit ?? 'gsm' } : null });
                        }}
                      />
                      <select className="input" style={{ width: 100 }} value={m.weight?.unit ?? 'gsm'} onChange={(e) => m.weight && setMat(m.id, { weight: { ...m.weight, unit: e.target.value as 'gsm' | 'oz/yd2' } })} aria-label="Weight unit">
                        <option value="gsm">g/m²</option>
                        <option value="oz/yd2">oz/yd²</option>
                      </select>
                    </div>
                  </div>
                  <div className="field">
                    <span className="label">Finish</span>
                    <TextInput value={m.finish} placeholder="e.g. enzyme wash" onCommit={(finish) => setMat(m.id, { finish })} ariaLabel="Finish" />
                  </div>
                  <div className="field">
                    <span className="label">Appearance texture</span>
                    <select className="input" value={m.textureId ?? ''} onChange={(e) => setMat(m.id, { textureId: e.target.value || null })}>
                      <option value="">None</option>
                      {TEXTURES.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <span className="label">Supplier</span>
                    <TextInput value={m.supplier} onCommit={(supplier) => setMat(m.id, { supplier })} ariaLabel="Supplier" />
                  </div>
                  <div className="field">
                    <span className="label">Supplier reference</span>
                    <TextInput value={m.supplierRef} onCommit={(supplierRef) => setMat(m.id, { supplierRef })} ariaLabel="Supplier reference" />
                  </div>
                  <div className="field">
                    <span className="label">Notes</span>
                    <TextInput value={m.notes} onCommit={(notes) => setMat(m.id, { notes })} ariaLabel="Material notes" />
                  </div>
                </div>
                <div className="row">
                  {usedM.has(m.id) ? <span className="badge info">In use</span> : <span className="badge">Not used</span>}
                  <div className="spacer" />
                  <button className="btn sm danger" disabled={usedM.has(m.id)} title={usedM.has(m.id) ? 'Reassign parts before deleting' : 'Delete'} onClick={() => update((d) => void (d.materials = d.materials.filter((x) => x.id !== m.id)))}>
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'colorways' && <ColorwaysEditor />}
        {tab === 'bom' && <BomEditor />}
        <p className="hint" style={{ marginTop: 10 }}>
          Currently previewing colorway: {doc.colorways.find((c) => c.id === ui.colorwayId)?.name ?? doc.colorways[0].name}.
        </p>
      </div>
    </main>
  );
}

function ColorwaysEditor() {
  const { doc, update } = useProject();
  const ui = useUi();
  if (!doc) return null;
  const baseColors = new Set<string>();
  const baseMats = new Set<string>();
  for (const l of doc.layers) {
    if (l.type === 'panelFill') {
      baseColors.add(l.colorId);
      if (l.materialId) baseMats.add(l.materialId);
    }
    if (l.type === 'stitching') baseColors.add(l.colorId);
  }
  return (
    <div className="card">
      <div className="section row">
        <div style={{ flex: 1 }}>
          <h2>Colorways</h2>
          <p className="hint">Every colorway reuses this style. Define explicit substitutions of base colors and materials; anything not substituted stays as designed.</p>
        </div>
        <button
          className="btn primary sm"
          data-testid="add-colorway"
          onClick={() => {
            const id = newId('cw');
            update((d) => void d.colorways.push({ id, name: `Colorway ${d.colorways.length + 1}`, code: '', colorSubs: {}, materialSubs: {}, notes: '' }));
            ui.set({ colorwayId: id });
          }}
        >
          <Icon name="plus" size={14} /> Add colorway
        </button>
      </div>
      {doc.colorways.map((cw, i) => (
        <div className="section" key={cw.id}>
          <div className="row" style={{ marginBottom: 8 }}>
            <div style={{ width: 220 }}>
              <TextInput value={cw.name} onCommit={(name) => name.trim() && update((d) => void (d.colorways[i].name = name.trim()))} ariaLabel="Colorway name" />
            </div>
            <div style={{ width: 120 }}>
              <TextInput value={cw.code} placeholder="Code" onCommit={(code) => update((d) => void (d.colorways[i].code = code))} ariaLabel="Colorway code" />
            </div>
            {i === 0 ? <span className="badge info">Base design</span> : null}
            <div className="spacer" />
            <button className="btn sm" onClick={() => ui.set({ colorwayId: cw.id })} aria-pressed={ui.colorwayId === cw.id}>
              Preview
            </button>
            {i > 0 && (
              <button className="btn sm danger" onClick={() => update((d) => void (d.colorways = d.colorways.filter((x) => x.id !== cw.id)))}>
                Delete
              </button>
            )}
          </div>
          {i === 0 ? (
            <p className="hint">The base colorway shows the design exactly as drawn.</p>
          ) : (
            <div className="grid2">
              <div>
                <div className="label" style={{ marginBottom: 6 }}>Color substitutions</div>
                {[...baseColors].map((cid) => {
                  const base = doc.colors.find((c) => c.id === cid);
                  if (!base) return null;
                  return (
                    <div key={cid} className="row small" style={{ marginBottom: 4 }}>
                      <span className="swatch" style={{ background: base.hex }} />
                      <span style={{ width: 130 }}>{base.name} →</span>
                      <select className="input sm" value={cw.colorSubs[cid] ?? ''} aria-label={`Substitute for ${base.name}`} onChange={(e) => update((d) => {
                        const subs = d.colorways[i].colorSubs;
                        if (e.target.value) subs[cid] = e.target.value;
                        else delete subs[cid];
                      })}>
                        <option value="">(same)</option>
                        {doc.colors.filter((c) => c.id !== cid).map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>
              <div>
                <div className="label" style={{ marginBottom: 6 }}>Material substitutions</div>
                {[...baseMats].map((mid) => {
                  const base = doc.materials.find((m) => m.id === mid);
                  if (!base) return null;
                  return (
                    <div key={mid} className="row small" style={{ marginBottom: 4 }}>
                      <span style={{ width: 170 }}>{base.name} →</span>
                      <select className="input sm" value={cw.materialSubs[mid] ?? ''} aria-label={`Substitute for ${base.name}`} onChange={(e) => update((d) => {
                        const subs = d.colorways[i].materialSubs;
                        if (e.target.value) subs[mid] = e.target.value;
                        else delete subs[mid];
                      })}>
                        <option value="">(same)</option>
                        {doc.materials.filter((m) => m.id !== mid).map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function BomEditor() {
  const { doc, template, update } = useProject();
  if (!doc || !template) return null;
  const rows = computeBom(doc, template);
  const setDerived = (key: string, patch: Partial<ProjectDoc['bomDerived'][string]>) =>
    update((d: Draft<ProjectDoc>) => {
      const cur = d.bomDerived[key] ?? { quantity: null, unit: '', quantityType: 'entered', supplierRef: '', notes: '' };
      d.bomDerived[key] = { ...cur, ...patch };
    });
  const setManual = (id: string, patch: Partial<BomItem>) => update((d) => void Object.assign(d.bomItems.find((b) => b.id === id)!, patch));
  return (
    <div className="card">
      <div className="section row">
        <div style={{ flex: 1 }}>
          <h2>Bill of materials</h2>
          <p className="hint">
            Rows marked <span className="badge info">from design</span> update automatically when you change parts, stitching, embellishments, or hardware. Fabric consumption is never inferred from the drawing — enter it from your marker or factory. <span className="badge ok">counted</span> quantities come from placed items.
          </p>
        </div>
        <button className="btn primary sm" data-testid="add-bom" onClick={() => update((d) => void d.bomItems.push({ id: newId('bom'), category: 'trim', component: '', materialId: null, description: 'New item', quantity: null, unit: 'pcs', quantityType: 'entered', colorwayIds: [], supplierRef: '', notes: '' }))}>
          <Icon name="plus" size={14} /> Add item
        </button>
      </div>
      <div className="table-scroll">
        <table className="table" data-testid="bom-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Category</th>
              <th>Component</th>
              <th>Material / trim</th>
              <th>Qty</th>
              <th>Unit</th>
              <th>Qty type</th>
              <th>Colorways</th>
              <th>Supplier ref</th>
              <th>Notes</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const manual = doc.bomItems.find((b) => b.id === r.key);
              return (
                <tr key={r.key} data-testid="bom-row" data-key={r.key}>
                  <td>{r.derived ? <span className="badge info">from design</span> : <span className="badge">manual</span>}</td>
                  <td>
                    {manual ? (
                      <select className="input sm" value={manual.category} onChange={(e) => setManual(manual.id, { category: e.target.value as BomItem['category'] })}>
                        {['fabric', 'trim', 'thread', 'label', 'packaging', 'embellishment', 'hardware', 'other'].map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    ) : (
                      r.category
                    )}
                  </td>
                  <td style={{ minWidth: 140 }}>{manual ? <TextInput value={manual.component} onCommit={(component) => setManual(manual.id, { component })} ariaLabel="Component" /> : r.component}</td>
                  <td style={{ minWidth: 180 }} data-testid="bom-material">
                    {manual ? (
                      <>
                        <select className="input sm" value={manual.materialId ?? ''} onChange={(e) => setManual(manual.id, { materialId: e.target.value || null })} aria-label="Material">
                          <option value="">— free text —</option>
                          {doc.materials.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.name}
                            </option>
                          ))}
                        </select>
                        <TextInput value={manual.description} onCommit={(description) => setManual(manual.id, { description })} ariaLabel="Description" />
                      </>
                    ) : (
                      <>
                        <strong>{r.materialName}</strong>
                        {r.description && <div className="small muted">{r.description}</div>}
                      </>
                    )}
                  </td>
                  <td>
                    {r.quantityType === 'counted' ? (
                      <strong data-testid="bom-counted-qty">{r.quantity}</strong>
                    ) : manual ? (
                      <div style={{ width: 80 }}>
                        <NumberInput value={manual.quantity ?? 0} min={0} step={0.01} onCommit={(q) => setManual(manual.id, { quantity: q })} ariaLabel="Quantity" />
                      </div>
                    ) : (
                      <input className="input sm" style={{ width: 80 }} type="number" min={0} step={0.01} defaultValue={r.quantity ?? ''} key={`${r.key}-${r.quantity}`} aria-label={`${r.materialName} quantity`} onBlur={(e) => setDerived(r.key, { quantity: e.target.value === '' ? null : Math.max(0, Number(e.target.value)) })} />
                    )}
                  </td>
                  <td style={{ width: 70 }}>
                    {r.quantityType === 'counted' ? r.unit : manual ? <TextInput value={manual.unit} onCommit={(unit) => setManual(manual.id, { unit })} ariaLabel="Unit" /> : <TextInput value={r.unit} onCommit={(unit) => setDerived(r.key, { unit })} ariaLabel="Unit" />}
                  </td>
                  <td style={{ minWidth: 118 }}>
                    {r.quantityType === 'counted' ? (
                      <span className="badge ok">counted</span>
                    ) : (
                      <select className="input sm" value={manual ? manual.quantityType : doc.bomDerived[r.key]?.quantityType ?? 'entered'} onChange={(e) => (manual ? setManual(manual.id, { quantityType: e.target.value as 'entered' | 'estimated' }) : setDerived(r.key, { quantityType: e.target.value as 'entered' | 'estimated' }))} aria-label="Quantity type">
                        <option value="entered">entered</option>
                        <option value="estimated">estimated</option>
                      </select>
                    )}
                    {r.quantityType === 'missing' && <div className="small" style={{ color: 'var(--warn)' }}>not entered</div>}
                  </td>
                  <td className="small">{colorwayNames(doc, r.colorwayIds)}</td>
                  <td style={{ minWidth: 110 }}>{manual ? <TextInput value={manual.supplierRef} onCommit={(supplierRef) => setManual(manual.id, { supplierRef })} ariaLabel="Supplier ref" /> : <TextInput value={doc.bomDerived[r.key]?.supplierRef ?? r.supplierRef} onCommit={(supplierRef) => setDerived(r.key, { supplierRef })} ariaLabel="Supplier ref" />}</td>
                  <td style={{ minWidth: 140 }}>{manual ? <TextInput value={manual.notes} onCommit={(notes) => setManual(manual.id, { notes })} ariaLabel="Notes" /> : <TextInput value={doc.bomDerived[r.key]?.notes ?? ''} onCommit={(notes) => setDerived(r.key, { notes })} ariaLabel="Notes" />}</td>
                  <td>
                    {manual && (
                      <button className="btn sm icon ghost" aria-label="Delete BOM item" onClick={() => update((d) => void (d.bomItems = d.bomItems.filter((b) => b.id !== manual.id)))}>
                        <Icon name="trash" size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
