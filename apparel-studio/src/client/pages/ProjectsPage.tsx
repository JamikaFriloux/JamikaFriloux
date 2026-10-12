import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { ProjectSummary, ProjectRecord } from '../../shared/schema/project';
import { getTemplate } from '../../shared/templates';
import { TechView } from '../../shared/render/TechView';
import { api } from '../api';
import { Icon } from '../components/Icon';
import { Modal, useAssetResolver } from '../components/common';
import { useUi } from '../store/ui';

function Thumb({ id }: { id: string }) {
  const [rec, setRec] = useState<ProjectRecord | null>(null);
  useEffect(() => {
    let live = true;
    api.getProject(id).then((r) => live && setRec(r)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [id]);
  const resolve = useAssetResolver(rec?.doc ?? null);
  if (!rec) return null;
  const t = getTemplate(rec.doc.template.id, rec.doc.template.version);
  if (!t) return <span className="badge err">Template missing</span>;
  return <TechView template={t} doc={rec.doc} viewId="front" resolveAsset={resolve} seams={false} idPrefix={`th-${id}`} />;
}

export function ProjectsPage() {
  const [items, setItems] = useState<ProjectSummary[] | null>(null);
  const [archived, setArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dup, setDup] = useState<ProjectSummary | null>(null);
  const [filter, setFilter] = useState('');
  const navigate = useNavigate();
  const notify = useUi((s) => s.notify);

  const refresh = () =>
    api
      .listProjects(archived)
      .then((r) => {
        setItems(r);
        setError(null);
      })
      .catch((e) => setError(e.message));
  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [archived]);

  const groups = useMemo(() => {
    const m = new Map<string, ProjectSummary[]>();
    for (const p of items ?? []) {
      if (filter && !`${p.name} ${p.styleNumber} ${p.collection}`.toLowerCase().includes(filter.toLowerCase())) continue;
      const k = p.collection || '';
      m.set(k, [...(m.get(k) ?? []), p]);
    }
    return [...m.entries()].sort(([a], [b]) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)));
  }, [items, filter]);

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          <span className="brand-mark">
            <Icon name="shirt" size={16} />
          </span>
          Apparel Studio
        </span>
        <div className="spacer" />
        <Link className="btn primary" to="/new">
          <Icon name="plus" /> New style
        </Link>
      </header>
      <main className="page">
        <div className="page-inner">
          <div className="title-row">
            <h1>Styles</h1>
            <div className="seg" role="group" aria-label="Show">
              <button aria-pressed={!archived} onClick={() => setArchived(false)}>
                Active
              </button>
              <button aria-pressed={archived} onClick={() => setArchived(true)}>
                Archived
              </button>
            </div>
            <div className="spacer" />
            <input className="input" style={{ maxWidth: 260 }} placeholder="Search name, style #, collection" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Search styles" />
          </div>
          {error && <div className="callout err">{error}</div>}
          {items && items.length === 0 && (
            <div className="card empty">
              <h3>{archived ? 'No archived styles' : 'No styles yet'}</h3>
              <p>{archived ? 'Archived styles appear here.' : 'Create a style to start designing. Pick a garment, customize its parts, and export a tech pack.'}</p>
              {!archived && (
                <Link className="btn primary" to="/new" style={{ marginTop: 12 }}>
                  Create your first style
                </Link>
              )}
            </div>
          )}
          {groups.map(([collection, list]) => (
            <section key={collection || '_none'}>
              <div className="collection-head">
                <h2>{collection || 'No collection'}</h2>
                <span className="badge">{list.length} style{list.length === 1 ? '' : 's'}</span>
                {collection && <span className="small muted">Each style keeps its own specification and tech pack.</span>}
              </div>
              <div className="project-grid">
                {list.map((p) => (
                  <article key={p.id} className="card project-card" data-testid="project-card">
                    <div className="thumb" onClick={() => navigate(`/p/${p.id}`)} role="link" aria-label={`Open ${p.name}`} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && navigate(`/p/${p.id}`)}>
                      <Thumb id={p.id} />
                    </div>
                    <div className="body">
                      <Link to={`/p/${p.id}`} style={{ fontWeight: 600, color: 'var(--ink)', textDecoration: 'none' }}>
                        {p.name}
                      </Link>
                      <div className="small muted">
                        {p.styleNumber} · {getTemplate(p.templateId, p.templateVersion)?.name ?? p.templateId}
                      </div>
                      <div className="row small muted">
                        <span>Edited {new Date(p.updatedAt).toLocaleDateString()}</span>
                        {p.revisionCount > 0 && <span className="badge info">{p.revisionCount} revision{p.revisionCount === 1 ? '' : 's'}</span>}
                      </div>
                      <div className="row" style={{ marginTop: 6 }}>
                        <button className="btn sm" onClick={() => setDup(p)}>
                          <Icon name="copy" size={14} /> Duplicate
                        </button>
                        <button
                          className="btn sm"
                          onClick={async () => {
                            await api.setArchived(p.id, !archived);
                            notify('info', archived ? `Restored “${p.name}”.` : `Archived “${p.name}”.`);
                            void refresh();
                          }}
                        >
                          <Icon name="archive" size={14} /> {archived ? 'Restore' : 'Archive'}
                        </button>
                        {archived && (
                          <button
                            className="btn sm danger"
                            onClick={async () => {
                              if (!confirm(`Permanently delete “${p.name}” and its revisions? This cannot be undone.`)) return;
                              await api.deleteProject(p.id);
                              void refresh();
                            }}
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      </main>
      {dup && <DuplicateDialog source={dup} onClose={() => setDup(null)} onDone={(id) => navigate(`/p/${id}`)} />}
    </div>
  );
}

function DuplicateDialog({ source, onClose, onDone }: { source: ProjectSummary; onClose: () => void; onDone: (id: string) => void }) {
  const [name, setName] = useState(`${source.name} (copy)`);
  const [style, setStyle] = useState(`${source.styleNumber}-B`);
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal
      title="Duplicate style"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn primary"
            disabled={!name.trim() || !style.trim()}
            onClick={async () => {
              try {
                const r = await api.duplicate(source.id, name.trim(), style.trim());
                onDone(r.id);
              } catch (e) {
                setErr((e as Error).message);
              }
            }}
          >
            Duplicate
          </button>
        </>
      }
    >
      <p className="hint" style={{ marginBottom: 10 }}>
        Copies the design, specifications, and uploaded artwork. Revisions stay with the original.
      </p>
      <div className="field">
        <label htmlFor="dn">Style name</label>
        <input id="dn" className="input" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="ds">Style number</label>
        <input id="ds" className="input" value={style} onChange={(e) => setStyle(e.target.value)} />
      </div>
      {err && <div className="callout err">{err}</div>}
    </Modal>
  );
}
