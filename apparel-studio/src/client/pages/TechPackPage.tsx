import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { ConstructionNote, LabelItem, RevisionSummary } from '../../shared/schema/project';
import { validateProject, type Check, type CheckSection } from '../../shared/domain/validation';
import { newId } from '../../shared/domain/ids';
import { api, exportUrl } from '../api';
import { useProject } from '../store/project';
import { useUi } from '../store/ui';
import { TextInput } from '../components/common';
import { Icon } from '../components/Icon';
import { renderGhostPng } from '../render/ghost';

const SECTION_LABELS: Record<CheckSection, string> = {
  identity: 'Style identity',
  materials: 'Materials',
  colors: 'Colors',
  bom: 'Bill of materials',
  artwork: 'Artwork placement',
  measurements: 'Measurements',
  construction: 'Construction',
  labels: 'Labels & packaging',
  decoration: 'Embellishments & hardware',
  assets: 'Uploaded files',
};

const LABEL_TYPES: LabelItem['type'][] = ['main-label', 'size-label', 'care-label', 'hang-tag', 'heat-transfer-label', 'polybag', 'folding', 'carton', 'other'];

export function TechPackPage() {
  const { id } = useParams();
  const { doc, template, update, flush, version, saveState } = useProject();
  const ui = useUi();
  const navigate = useNavigate();
  const [revs, setRevs] = useState<RevisionSummary[] | null>(null);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ text: string; checks?: Check[] } | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [withMockups, setWithMockups] = useState(true);
  const validation = useMemo(() => (doc && template ? validateProject(doc, template) : null), [doc, template]);

  const loadRevs = () => id && api.revisions(id).then(setRevs).catch((e) => setError({ text: e.message }));
  useEffect(() => {
    void loadRevs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);
  if (!doc || !template || !validation || !id) return null;

  const failedReq = validation.failedRequired;
  const failedRec = validation.failedRecommended;
  const fix = (c: Check) => {
    const base = `/p/${id}`;
    if (c.fix.screen === 'studio') {
      if (c.fix.focus && doc.layers.some((l) => l.id === c.fix.focus)) {
        const l = doc.layers.find((x) => x.id === c.fix.focus)!;
        ui.set({ selectedLayerId: l.id, selectedComponentId: null, view: l.view === 'all' ? ui.view : l.view, preview: 'technical' });
      }
      navigate(base);
    } else if (c.fix.screen === 'measurements') navigate(`${base}/measurements`);
    else if (c.fix.screen === 'materials') navigate(`${base}/materials`);
    else document.getElementById(c.fix.focus ?? 'style-info')?.scrollIntoView({ behavior: 'smooth' });
  };

  const exportRevision = async (kind: 'draft' | 'review') => {
    setError(null);
    setBusy('Saving latest changes…');
    try {
      const ok = await flush();
      if (!ok) throw new Error('Your latest changes could not be saved, so the export was stopped. Resolve the save error (top right) and try again.');
      const mockups: { front?: string; back?: string } = {};
      if (withMockups && template.ghost) {
        setBusy('Rendering mockups…');
        for (const v of template.views) {
          const png = await renderGhostPng(doc, template, v.id, doc.colorways[0].id, 2);
          mockups[v.id] = (await api.uploadMockup(id, png)).sha256;
        }
      }
      setBusy('Generating tech pack…');
      const rev = await api.issueRevision(id, { kind, notes, expectedVersion: useProject.getState().version, mockups });
      const failed = rev.exports.filter((e) => e.status === 'failed');
      if (failed.length) setError({ text: `Revision ${rev.label} was saved, but ${failed.map((f) => f.kind).join(', ')} failed: ${failed[0].error}. Use “Retry exports”.` });
      else ui.notify('info', `Issued revision ${rev.label} (${kind === 'review' ? 'ready for manufacturer review' : 'draft'}).`);
      setNotes('');
      await loadRevs();
    } catch (e) {
      const err = e as Error & { details?: unknown };
      setError({ text: err.message, checks: Array.isArray(err.details) ? (err.details as Check[]) : undefined });
    } finally {
      setBusy(null);
    }
  };

  const doPreview = async () => {
    setError(null);
    setBusy('Rendering preview…');
    try {
      await flush();
      const blob = await api.previewPdf(id);
      setPreview(URL.createObjectURL(blob));
    } catch (e) {
      setError({ text: `Preview failed: ${(e as Error).message}` });
    } finally {
      setBusy(null);
    }
  };

  const grouped = (list: Check[]) =>
    Object.entries(
      list.reduce<Record<string, Check[]>>((a, c) => {
        (a[c.section] ??= []).push(c);
        return a;
      }, {}),
    );

  const setNote = (nid: string, patch: Partial<ConstructionNote>) => update((d) => void Object.assign(d.constructionNotes.find((n) => n.id === nid)!, patch));
  const setLabel = (lid: string, patch: Partial<LabelItem>) => update((d) => void Object.assign(d.labels.find((n) => n.id === lid)!, patch));
  const allSeams = [...new Map(template.views.flatMap((v) => v.seams).map((s) => [s.id, s.name])).entries()];

  return (
    <main className="page">
      <div className="page-inner" style={{ maxWidth: 1400 }}>
        <div className="title-row">
          <h1>Tech Pack</h1>
          <span className="hint">Generated from this style’s saved design — nothing to re-enter.</span>
        </div>
        <div className="split" style={{ gridTemplateColumns: 'minmax(360px, 1fr) minmax(0, 1.2fr)' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <section className="card" aria-labelledby="checks-h">
              <div className="section">
                <h2 id="checks-h">Completeness</h2>
                <div className="row wrap" style={{ marginTop: 8 }}>
                  {failedReq.length ? <span className="badge err" data-testid="required-open">{failedReq.length} required open</span> : <span className="badge ok" data-testid="required-open">All required complete</span>}
                  <span className="badge warn">{failedRec.length} recommended open</span>
                  <span className="badge">{validation.checks.filter((c) => c.passed).length} passed</span>
                </div>
                <p className="hint" style={{ marginTop: 6 }}>Required items block only the manufacturer-review export. Drafts can be exported anytime and list what’s missing. Sections you don’t use (e.g. labels) don’t block.</p>
              </div>
              {failedReq.length > 0 && (
                <div className="section">
                  <div className="section-title" style={{ color: 'var(--err)' }}>Required</div>
                  {grouped(failedReq).map(([sec, list]) => (
                    <div key={sec} style={{ marginBottom: 8 }}>
                      <div className="label">{SECTION_LABELS[sec as CheckSection]}</div>
                      <ul className="check-list">
                        {list.map((c) => (
                          <li key={c.id} data-testid="check-required">
                            <span style={{ color: 'var(--err)' }}><Icon name="alert" size={14} /></span>
                            <span style={{ flex: 1 }}>{c.message}</span>
                            <button className="btn sm" onClick={() => fix(c)}>Fix</button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
              {failedRec.length > 0 && (
                <div className="section">
                  <details>
                    <summary className="section-title" style={{ cursor: 'pointer' }}>Recommended ({failedRec.length})</summary>
                    <ul className="check-list">
                      {failedRec.map((c) => (
                        <li key={c.id}>
                          <span style={{ color: 'var(--warn)' }}>•</span>
                          <span style={{ flex: 1 }}>{c.message}</span>
                          <button className="btn sm" onClick={() => fix(c)}>Open</button>
                        </li>
                      ))}
                    </ul>
                  </details>
                </div>
              )}
            </section>

            <section className="card">
              <div className="section">
                <h2>Export a revision</h2>
                <p className="hint" style={{ margin: '4px 0 10px' }}>Each export freezes an immutable snapshot (PDF, BOM CSV, measurement CSV{template.ghost ? ', mockup PNGs' : ''}). Later edits never change an issued revision.</p>
                <div className="field">
                  <label htmlFor="revnotes">Revision notes</label>
                  <textarea id="revnotes" className="input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What changed in this revision?" />
                </div>
                {template.ghost && (
                  <label className="row small" style={{ marginBottom: 10 }}>
                    <input type="checkbox" checked={withMockups} onChange={(e) => setWithMockups(e.target.checked)} /> Include realistic mockup PNGs (appearance preview)
                  </label>
                )}
                <div className="row wrap">
                  <button className="btn" onClick={() => exportRevision('draft')} disabled={!!busy} data-testid="export-draft">
                    Export draft
                  </button>
                  <button className="btn primary" onClick={() => exportRevision('review')} disabled={!!busy || failedReq.length > 0} data-testid="export-review" title={failedReq.length ? 'Complete the required items first' : undefined}>
                    Export ready for manufacturer review
                  </button>
                  <button className="btn" onClick={doPreview} disabled={!!busy} data-testid="preview-pdf">
                    <Icon name="file" size={14} /> Preview pages
                  </button>
                </div>
                {failedReq.length > 0 && <p className="hint" style={{ marginTop: 6 }}>Review export unlocks when the {failedReq.length} required item(s) above are complete.</p>}
                {busy && <div className="callout info" style={{ marginTop: 10 }} role="status">{busy}</div>}
                {saveState !== 'saved' && !busy && <p className="hint" style={{ marginTop: 6 }}>Unsaved edits will be saved before exporting (v{version}).</p>}
                {error && (
                  <div className="callout err" style={{ marginTop: 10 }} role="alert" data-testid="export-error">
                    {error.text}
                    {error.checks && (
                      <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                        {error.checks.slice(0, 8).map((c) => (
                          <li key={c.id}>{c.message}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
                <p className="hint" style={{ marginTop: 10 }}>Documents are specifications for review and sampling — never a manufacturer approval.</p>
              </div>
            </section>

            <section className="card">
              <div className="section">
                <h2>Revisions</h2>
              </div>
              {revs && revs.length === 0 && <div className="empty">No revisions issued yet.</div>}
              {revs?.map((r) => (
                <div className="section" key={r.id} data-testid="revision">
                  <div className="row">
                    <strong>{r.label}</strong>
                    {r.kind === 'review' ? <span className="badge ok">Ready for manufacturer review</span> : <span className="badge warn">Draft</span>}
                    <span className="small muted">{new Date(r.createdAt).toLocaleString()}</span>
                  </div>
                  {r.notes && <p className="small" style={{ marginTop: 4 }}>{r.notes}</p>}
                  <div className="row wrap" style={{ marginTop: 6 }}>
                    {r.exports.map((e) =>
                      e.status === 'ok' ? (
                        <a key={e.id} className="btn sm" href={exportUrl(e.id, e.kind === 'pdf')} target={e.kind === 'pdf' ? '_blank' : undefined} rel="noreferrer" data-testid={`dl-${e.kind}`}>
                          <Icon name="download" size={14} /> {e.kind === 'pdf' ? 'PDF' : e.kind === 'bom-csv' ? 'BOM CSV' : e.kind === 'measurements-csv' ? 'Measurements CSV' : e.filename.includes('back') ? 'Mockup back PNG' : 'Mockup front PNG'}
                        </a>
                      ) : (
                        <span key={e.id} className="badge err" title={e.error ?? ''}>
                          {e.kind} failed
                        </span>
                      ),
                    )}
                    {r.exports.some((e) => e.status === 'failed') && (
                      <button className="btn sm" onClick={async () => { await api.retryExports(r.id); await loadRevs(); }}>
                        Retry exports
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </section>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {preview && (
              <section className="card">
                <div className="section row">
                  <h2 style={{ flex: 1 }}>Page preview</h2>
                  <span className="badge warn">Not issued</span>
                  <button className="btn sm ghost icon" aria-label="Close preview" onClick={() => setPreview(null)}>
                    <Icon name="x" />
                  </button>
                </div>
                <iframe title="Tech pack preview" src={preview} style={{ width: '100%', height: 640, border: 0 }} data-testid="preview-frame" />
              </section>
            )}
            <section className="card" id="style-info">
              <div className="section">
                <h2 style={{ marginBottom: 10 }}>Style information</h2>
                <div className="grid2">
                  <div className="field">
                    <span className="label">Style name</span>
                    <TextInput value={doc.name} onCommit={(name) => name.trim() && update((d) => void (d.name = name.trim()))} ariaLabel="Style name" />
                  </div>
                  <div className="field">
                    <span className="label">Style number</span>
                    <TextInput value={doc.styleNumber} onCommit={(s) => s.trim() && update((d) => void (d.styleNumber = s.trim()))} ariaLabel="Style number" />
                  </div>
                  <div className="field">
                    <span className="label">Season</span>
                    <TextInput value={doc.season} onCommit={(season) => update((d) => void (d.season = season))} ariaLabel="Season" />
                  </div>
                  <div className="field">
                    <span className="label">Collection / set</span>
                    <TextInput value={doc.collection} onCommit={(collection) => update((d) => void (d.collection = collection))} ariaLabel="Collection" />
                  </div>
                </div>
                <div className="field">
                  <span className="label">Description</span>
                  <TextInput multiline value={doc.description} onCommit={(description) => update((d) => void (d.description = description))} ariaLabel="Description" />
                </div>
              </div>
            </section>

            <section className="card">
              <div className="section row">
                <div style={{ flex: 1 }}>
                  <h2>Construction notes</h2>
                  <p className="hint">Seam types, finishes and assembly. These are the construction specification; drawn stitches are illustrative.</p>
                </div>
                <button className="btn sm primary" onClick={() => update((d) => void d.constructionNotes.push({ id: newId('cn'), title: 'New note', text: '', componentIds: [], seamIds: [] }))} data-testid="add-construction-note">
                  <Icon name="plus" size={14} /> Add note
                </button>
              </div>
              {doc.constructionNotes.length === 0 && <div className="empty small">No construction notes yet (recommended).</div>}
              {doc.constructionNotes.map((n) => (
                <div className="section" key={n.id}>
                  <div className="row" style={{ marginBottom: 6 }}>
                    <div style={{ flex: 1 }}>
                      <TextInput value={n.title} onCommit={(title) => title.trim() && setNote(n.id, { title: title.trim() })} ariaLabel="Note title" />
                    </div>
                    <button className="btn sm icon ghost" aria-label="Delete note" onClick={() => update((d) => void (d.constructionNotes = d.constructionNotes.filter((x) => x.id !== n.id)))}>
                      <Icon name="trash" size={14} />
                    </button>
                  </div>
                  <TextInput multiline value={n.text} onCommit={(text) => setNote(n.id, { text })} ariaLabel="Note text" />
                  <details style={{ marginTop: 6 }}>
                    <summary className="small muted" style={{ cursor: 'pointer' }}>
                      Applies to {n.componentIds.length + n.seamIds.length} part(s)/seam(s) — shown as detail views
                    </summary>
                    <div className="grid2" style={{ marginTop: 6 }}>
                      <div>
                        {template.components.map((c) => (
                          <label key={c.id} className="row small">
                            <input type="checkbox" checked={n.componentIds.includes(c.id)} onChange={(e) => setNote(n.id, { componentIds: e.target.checked ? [...n.componentIds, c.id] : n.componentIds.filter((x) => x !== c.id) })} /> {c.name}
                          </label>
                        ))}
                      </div>
                      <div>
                        {allSeams.map(([sid, name]) => (
                          <label key={sid} className="row small">
                            <input type="checkbox" checked={n.seamIds.includes(sid)} onChange={(e) => setNote(n.id, { seamIds: e.target.checked ? [...n.seamIds, sid] : n.seamIds.filter((x) => x !== sid) })} /> {name}
                          </label>
                        ))}
                      </div>
                    </div>
                  </details>
                </div>
              ))}
            </section>

            <section className="card">
              <div className="section row">
                <div style={{ flex: 1 }}>
                  <h2>Labels &amp; packaging</h2>
                  <p className="hint">Optional. Included in the tech pack only when specified.</p>
                </div>
                <button className="btn sm primary" onClick={() => update((d) => void d.labels.push({ id: newId('lbl'), type: 'main-label', description: '', placement: '', materialId: null, assetId: null, notes: '' }))}>
                  <Icon name="plus" size={14} /> Add item
                </button>
              </div>
              {doc.labels.map((l) => (
                <div className="section" key={l.id} id={l.id}>
                  <div className="grid2">
                    <div className="field">
                      <span className="label">Type</span>
                      <select aria-label="Label or packaging type" className="input" value={l.type} onChange={(e) => setLabel(l.id, { type: e.target.value as LabelItem['type'] })}>
                        {LABEL_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {t.replace(/-/g, ' ')}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <span className="label">Placement</span>
                      <TextInput value={l.placement} onCommit={(placement) => setLabel(l.id, { placement })} ariaLabel="Label placement" />
                    </div>
                  </div>
                  <div className="field">
                    <span className="label">Description *</span>
                    <TextInput multiline value={l.description} onCommit={(description) => setLabel(l.id, { description })} ariaLabel="Label description" />
                  </div>
                  <div className="grid2">
                    <div className="field">
                      <span className="label">Material</span>
                      <select aria-label="Label material" className="input" value={l.materialId ?? ''} onChange={(e) => setLabel(l.id, { materialId: e.target.value || null })}>
                        <option value="">—</option>
                        {doc.materials.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <span className="label">Artwork file</span>
                      <select aria-label="Label artwork file" className="input" value={l.assetId ?? ''} onChange={(e) => setLabel(l.id, { assetId: e.target.value || null })}>
                        <option value="">—</option>
                        {doc.assets.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.filename}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="row">
                    <div style={{ flex: 1 }}>
                      <TextInput value={l.notes} placeholder="Notes" onCommit={(notes) => setLabel(l.id, { notes })} ariaLabel="Label notes" />
                    </div>
                    <button className="btn sm danger" onClick={() => update((d) => void (d.labels = d.labels.filter((x) => x.id !== l.id)))}>
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </section>
          </div>
        </div>
      </div>
    </main>
  );
}
