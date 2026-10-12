import React, { useState } from 'react';
import type { Draft } from 'immer';
import type { Pom, ProjectDoc } from '../../shared/schema/project';
import type { ViewId } from '../../shared/schema/template';
import { TechView } from '../../shared/render/TechView';
import { newId } from '../../shared/domain/ids';
import { useProject } from '../store/project';
import { LengthInput, Modal, TextInput, useAssetResolver } from '../components/common';
import { Icon } from '../components/Icon';

export function MeasurementsPage() {
  const { doc, template, update } = useProject();
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<ViewId>('front');
  const [adding, setAdding] = useState(false);
  const resolve = useAssetResolver(doc);
  if (!doc || !template) return null;
  const unit = doc.displayUnit;
  const sizes = doc.sizes.range;
  const pomCodes: Record<string, string> = {};
  for (const p of doc.measurements) if (p.templatePomId) pomCodes[p.templatePomId] = p.code;
  const sel = doc.measurements.find((p) => p.id === selected) ?? null;
  const unconfirmed = doc.measurements.filter((p) => !p.confirmed).length;
  const defaults = doc.measurements.filter((p) => Object.values(p.values).some((v) => v.source === 'template-default')).length;

  const setPom = (id: string, fn: (p: Draft<Pom>) => void, coalesce?: string) =>
    update(
      (d) => {
        const p = d.measurements.find((x) => x.id === id);
        if (p) fn(p);
      },
      { coalesce },
    );

  const select = (p: Pom) => {
    setSelected(p.id);
    setView(p.diagramView);
  };

  const toggleSize = (s: string, on: boolean) =>
    update((d: Draft<ProjectDoc>) => {
      const order = template.sizes.available;
      const next = on ? [...d.sizes.range, s] : d.sizes.range.filter((x) => x !== s);
      if (!next.length || (!on && s === d.sizes.base)) return;
      d.sizes.range = order.filter((x) => next.includes(x));
      for (const p of d.measurements) if (!p.values[s]) p.values[s] = { mm: null, source: 'entered' };
    });

  return (
    <main className="page">
      <div className="page-inner" style={{ maxWidth: 1400 }}>
        <div className="title-row">
          <h1>Measurements</h1>
          <div className="seg" role="group" aria-label="Units">
            {(['cm', 'in'] as const).map((u) => (
              <button key={u} aria-pressed={unit === u} data-testid={`unit-${u}`} onClick={() => update((d) => void (d.displayUnit = u))}>
                {u === 'cm' ? 'Centimetres' : 'Inches'}
              </button>
            ))}
          </div>
          <span className="hint">Values are stored in millimetres; switching units only changes the display.</span>
        </div>
        <div className="callout info" style={{ marginBottom: 14 }}>
          Template values are <strong>defaults until you confirm them</strong> (shown <span style={{ color: 'var(--warn)', fontStyle: 'italic' }}>amber italic*</span>). No grading rules are applied — enter each size’s value. V1 does not simulate fit or drape: changing measurements does not refit the mockup.
          {(unconfirmed > 0 || defaults > 0) && (
            <div style={{ marginTop: 6 }}>
              <span className="badge warn" data-testid="unconfirmed-count">{unconfirmed} unconfirmed POM{unconfirmed === 1 ? '' : 's'}</span>{' '}
              {defaults > 0 && <span className="badge warn">{defaults} with template defaults</span>}
            </div>
          )}
        </div>

        <div className="split">
          <div className="card sticky">
            <div className="section row">
              <h3 style={{ flex: 1 }}>Points of measure</h3>
              <div className="seg" role="group" aria-label="Diagram view">
                {template.views.map((v) => (
                  <button key={v.id} aria-pressed={view === v.id} onClick={() => setView(v.id)}>
                    {v.label}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ padding: 8, background: '#fafbfc' }}>
              <TechView
                template={template}
                doc={doc}
                viewId={view}
                resolveAsset={resolve}
                idPrefix="meas"
                fills={false}
                decorations={false}
                stitching={false}
                embellishments={false}
                hardware={false}
                annotations={false}
                textures={false}
                measurements={{ pomCodes, highlight: sel?.templatePomId ?? null }}
                width="100%"
              />
            </div>
            <div className="section">
              <div className="row wrap" style={{ gap: 4 }}>
                {doc.measurements
                  .filter((p) => p.diagramView === view)
                  .map((p) => (
                    <button key={p.id} className={`btn sm${selected === p.id ? ' active' : ''}`} onClick={() => select(p)} title={p.label}>
                      {p.code}
                    </button>
                  ))}
              </div>
              {sel ? (
                <div style={{ marginTop: 12 }}>
                  <h3>
                    {sel.code} · {sel.label}
                  </h3>
                  <div className="field" style={{ marginTop: 8 }}>
                    <span className="label">How to measure</span>
                    <TextInput multiline value={sel.howToMeasure} onCommit={(howToMeasure) => setPom(sel.id, (p) => void (p.howToMeasure = howToMeasure))} ariaLabel="How to measure" />
                  </div>
                  <div className="field">
                    <span className="label">Source of values</span>
                    <TextInput value={sel.source} onCommit={(source) => setPom(sel.id, (p) => void (p.source = source))} ariaLabel="Source" />
                  </div>
                  {!sel.templatePomId && <p className="hint">Custom POM: no diagram line. Describe the measurement precisely above.</p>}
                </div>
              ) : (
                <p className="hint" style={{ marginTop: 10 }}>Select a POM to highlight it on the diagram.</p>
              )}
            </div>
          </div>

          <div className="card">
            <div className="section">
              <div className="row wrap">
                <div className="field" style={{ margin: 0 }}>
                  <span className="label">Base size</span>
                  <select className="input sm" style={{ width: 90 }} value={doc.sizes.base} onChange={(e) => update((d) => void (d.sizes.base = e.target.value))} aria-label="Base size">
                    {doc.sizes.range.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <div className="field" style={{ margin: 0 }}>
                  <span className="label">Size range</span>
                  <div className="row wrap" style={{ gap: 10 }}>
                    {template.sizes.available.map((s) => (
                      <label key={s} className="row small" style={{ gap: 4 }}>
                        <input type="checkbox" checked={sizes.includes(s)} disabled={s === doc.sizes.base} onChange={(e) => toggleSize(s, e.target.checked)} aria-label={`Include size ${s}`} />
                        {s}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="spacer" />
                <button className="btn sm" onClick={() => setAdding(true)}>
                  <Icon name="plus" size={14} /> Add POM
                </button>
              </div>
            </div>
            <div className="table-scroll">
              <table className="table" data-testid="size-table">
                <thead>
                  <tr>
                    <th>POM</th>
                    <th style={{ minWidth: 170 }}>Description</th>
                    <th style={{ textAlign: 'right' }}>Tol −</th>
                    <th style={{ textAlign: 'right' }}>Tol +</th>
                    {sizes.map((s) => (
                      <th key={s} style={{ textAlign: 'right' }}>
                        {s}
                        {s === doc.sizes.base && <div className="small muted">base</div>}
                      </th>
                    ))}
                    <th>Confirmed</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {doc.measurements.map((p) => (
                    <tr key={p.id} className={selected === p.id ? 'selected' : ''} onClick={() => select(p)} data-testid={`pom-row-${p.code}`}>
                      <td>
                        <strong>{p.code}</strong>
                      </td>
                      <td>{p.label}</td>
                      <td style={{ textAlign: 'right' }}>
                        <LengthInput className="cell-input" mm={p.tolMinusMm} unit={unit} min={0} onCommit={(v) => v !== null && setPom(p.id, (x) => void (x.tolMinusMm = v))} ariaLabel={`${p.code} minus tolerance`} />
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <LengthInput className="cell-input" mm={p.tolPlusMm} unit={unit} min={0} onCommit={(v) => v !== null && setPom(p.id, (x) => void (x.tolPlusMm = v))} ariaLabel={`${p.code} plus tolerance`} />
                      </td>
                      {sizes.map((s) => {
                        const v = p.values[s];
                        const isDefault = v?.source === 'template-default';
                        return (
                          <td key={s} style={{ textAlign: 'right' }}>
                            <LengthInput
                              className="cell-input"
                              mm={v?.mm ?? null}
                              unit={unit}
                              allowEmpty
                              min={0}
                              isDefault={isDefault}
                              onCommit={(mm) =>
                                setPom(p.id, (x) => {
                                  x.values[s] = { mm, source: 'entered' };
                                })
                              }
                              ariaLabel={`${p.code} size ${s}`}
                            />
                            {isDefault && <span className="small" style={{ color: 'var(--warn)' }} title="Template default — not confirmed">*</span>}
                          </td>
                        );
                      })}
                      <td>
                        <label className="row small" style={{ gap: 4 }}>
                          <input type="checkbox" checked={p.confirmed} onChange={(e) => setPom(p.id, (x) => void (x.confirmed = e.target.checked))} aria-label={`Confirm ${p.code}`} data-testid={`confirm-${p.code}`} />
                          {p.confirmed ? <span className="badge ok">Yes</span> : <span className="badge warn">No</span>}
                        </label>
                      </td>
                      <td>
                        {!p.templatePomId && (
                          <button className="btn sm icon ghost" aria-label={`Delete ${p.code}`} onClick={(e) => { e.stopPropagation(); update((d) => void (d.measurements = d.measurements.filter((x) => x.id !== p.id))); }}>
                            <Icon name="trash" size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="section hint">
              Type values in {unit === 'in' ? 'inches — decimals (12.5) or fractions (12 1/2)' : 'centimetres'}. Base-size values in the template are shown for reference only; a POM is “confirmed” when you have checked every size.
            </div>
          </div>
        </div>
      </div>
      {adding && <AddPomDialog onClose={() => setAdding(false)} />}
    </main>
  );
}

function AddPomDialog({ onClose }: { onClose: () => void }) {
  const { doc, update } = useProject();
  const [code, setCode] = useState('');
  const [label, setLabel] = useState('');
  const [how, setHow] = useState('');
  const [view, setView] = useState<ViewId>('front');
  const exists = doc!.measurements.some((p) => p.code.toLowerCase() === code.trim().toLowerCase());
  return (
    <Modal
      title="Add point of measure"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn primary"
            disabled={!code.trim() || !label.trim() || exists}
            onClick={() => {
              update((d) => {
                d.measurements.push({
                  id: newId('pom'),
                  templatePomId: null,
                  code: code.trim().slice(0, 12),
                  label: label.trim(),
                  howToMeasure: how.trim(),
                  diagramView: view,
                  values: Object.fromEntries(d.sizes.range.map((s) => [s, { mm: null, source: 'entered' as const }])),
                  tolPlusMm: 6.4,
                  tolMinusMm: 6.4,
                  source: 'User entered',
                  confirmed: false,
                });
              });
              onClose();
            }}
          >
            Add
          </button>
        </>
      }
    >
      <div className="grid2">
        <div className="field">
          <label htmlFor="pc">Code</label>
          <input id="pc" className={`input${exists ? ' invalid' : ''}`} value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. M" />
          {exists && <span className="err-text">That code is already used.</span>}
        </div>
        <div className="field">
          <label htmlFor="pv">Diagram view</label>
          <select id="pv" className="input" value={view} onChange={(e) => setView(e.target.value as ViewId)}>
            <option value="front">Front</option>
            <option value="back">Back</option>
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="pl">Description</label>
        <input id="pl" className="input" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Hem height" />
      </div>
      <div className="field">
        <label htmlFor="ph">How to measure</label>
        <textarea id="ph" className="input" value={how} onChange={(e) => setHow(e.target.value)} />
      </div>
      <p className="hint">Tolerance defaults to ±6.4 mm (¼″); adjust it in the table.</p>
    </Modal>
  );
}
