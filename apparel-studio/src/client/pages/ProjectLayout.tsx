import React, { useEffect } from 'react';
import { Link, NavLink, Outlet, useParams } from 'react-router-dom';
import { useProject } from '../store/project';
import { useUi } from '../store/ui';
import { SaveStatus } from '../components/common';
import { Icon } from '../components/Icon';

export function ProjectLayout() {
  const { id } = useParams();
  const { load, doc, template, loadError, undo, redo, past, future } = useProject();
  const ui = useUi();
  useEffect(() => {
    if (id) void load(id);
  }, [id, load]);
  useEffect(() => {
    if (doc && (!ui.colorwayId || !doc.colorways.some((c) => c.id === ui.colorwayId))) ui.set({ colorwayId: doc.colorways[0].id });
  }, [doc, ui]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [undo, redo]);

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand" aria-label="All styles">
          <span className="brand-mark">
            <Icon name="shirt" size={16} />
          </span>
        </Link>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 260 }} data-testid="style-name">
            {doc?.name ?? 'Loading…'}
          </div>
          <div className="small muted">
            {doc ? `${doc.styleNumber} · ${template?.name}` : ''}
          </div>
        </div>
        <nav className="tabs" aria-label="Project sections">
          <NavLink to={`/p/${id}`} end>
            Design Studio
          </NavLink>
          <NavLink to={`/p/${id}/measurements`}>Measurements</NavLink>
          <NavLink to={`/p/${id}/materials`}>Materials &amp; Colors</NavLink>
          <NavLink to={`/p/${id}/techpack`}>Tech Pack</NavLink>
        </nav>
        <div className="spacer" />
        <button className="btn sm icon" onClick={undo} disabled={!past.length} aria-label="Undo" title="Undo (Ctrl/⌘+Z)">
          <Icon name="undo" />
        </button>
        <button className="btn sm icon" onClick={redo} disabled={!future.length} aria-label="Redo" title="Redo (Ctrl/⌘+Shift+Z)">
          <Icon name="redo" />
        </button>
        <SaveStatus />
      </header>
      {loadError ? (
        <div className="page">
          <div className="page-inner">
            <div className="callout err">
              <strong>Could not open this style.</strong> {loadError} <Link to="/">Back to all styles</Link>
            </div>
          </div>
        </div>
      ) : doc && template ? (
        <Outlet />
      ) : (
        <div className="empty">Loading style…</div>
      )}
    </div>
  );
}
