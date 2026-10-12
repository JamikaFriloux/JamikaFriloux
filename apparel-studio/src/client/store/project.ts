import { create } from 'zustand';
import { produce, type Draft } from 'immer';
import type { ProjectDoc, ProjectRecord } from '../../shared/schema/project';
import { projectDocSchema } from '../../shared/schema/project';
import type { GarmentTemplate } from '../../shared/schema/template';
import { requireTemplate } from '../../shared/templates';
import { api, ApiError } from '../api';

export type SaveState = 'saved' | 'dirty' | 'saving' | 'error' | 'conflict';

interface HistoryEntry {
  doc: ProjectDoc;
  key?: string;
  at: number;
}

interface ProjectState {
  id: string | null;
  doc: ProjectDoc | null;
  template: GarmentTemplate | null;
  version: number;
  loadError: string | null;
  past: HistoryEntry[];
  future: ProjectDoc[];
  saveState: SaveState;
  saveError: string | null;
  lastSavedAt: string | null;
  load: (id: string) => Promise<void>;
  /** Apply a change. Changes sharing a `coalesce` key within 1.2 s form one undo step. */
  update: (recipe: (d: Draft<ProjectDoc>) => void, opts?: { coalesce?: string }) => void;
  undo: () => void;
  redo: () => void;
  /** Save immediately (await before exporting). */
  flush: () => Promise<boolean>;
  retrySave: () => void;
  reset: () => void;
}

const HISTORY_LIMIT = 200;
const SAVE_DELAY = 500;
let saveTimer: ReturnType<typeof setTimeout> | null = null;
let saving: Promise<boolean> | null = null;

export const useProject = create<ProjectState>((set, get) => {
  const schedule = () => {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => void doSave(), SAVE_DELAY);
  };

  async function doSave(): Promise<boolean> {
    if (saving) {
      await saving;
      if (get().saveState === 'dirty') return doSave();
      return get().saveState === 'saved';
    }
    const { id, doc, version, saveState } = get();
    if (!id || !doc || saveState === 'saved' || saveState === 'conflict') return saveState === 'saved';
    // Validate locally first so bad data never leaves the editor silently.
    const parsed = projectDocSchema.safeParse(doc);
    if (!parsed.success) {
      set({ saveState: 'error', saveError: `Not saved: ${parsed.error.issues[0]?.path.join('.')} — ${parsed.error.issues[0]?.message}` });
      return false;
    }
    set({ saveState: 'saving', saveError: null });
    const sent = doc;
    saving = (async () => {
      try {
        const r = await api.saveProject(id, sent, version);
        const changedMeanwhile = get().doc !== sent;
        set({ version: r.version, lastSavedAt: r.updatedAt, saveState: changedMeanwhile ? 'dirty' : 'saved' });
        return true;
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) set({ saveState: 'conflict', saveError: e.message });
        else {
          const details = e instanceof ApiError && Array.isArray(e.details) ? ` (${(e.details as unknown[]).slice(0, 2).map((d) => (typeof d === 'string' ? d : JSON.stringify(d))).join('; ')})` : '';
          set({ saveState: 'error', saveError: `${(e as Error).message}${details}` });
        }
        return false;
      } finally {
        saving = null;
      }
    })();
    const ok = await saving;
    if (ok && get().saveState === 'dirty') schedule();
    return ok;
  }

  return {
    id: null,
    doc: null,
    template: null,
    version: 0,
    loadError: null,
    past: [],
    future: [],
    saveState: 'saved',
    saveError: null,
    lastSavedAt: null,

    load: async (id) => {
      if (get().id === id && get().doc) return;
      set({ id, doc: null, template: null, loadError: null, past: [], future: [], saveState: 'saved', saveError: null });
      try {
        const rec: ProjectRecord = await api.getProject(id);
        const template = requireTemplate(rec.doc.template.id, rec.doc.template.version);
        set({ doc: rec.doc, template, version: rec.version, lastSavedAt: rec.updatedAt });
      } catch (e) {
        set({ loadError: (e as Error).message });
      }
    },

    update: (recipe, opts) => {
      const { doc, past } = get();
      if (!doc) return;
      const next = produce(doc, recipe);
      if (next === doc) return;
      const now = Date.now();
      const last = past[past.length - 1];
      const coalesce = opts?.coalesce && last && last.key === opts.coalesce && now - last.at < 1200;
      const newPast = coalesce ? [...past.slice(0, -1), { ...last, at: now }] : [...past, { doc, key: opts?.coalesce, at: now }].slice(-HISTORY_LIMIT);
      set({ doc: next, past: newPast, future: [], saveState: get().saveState === 'conflict' ? 'conflict' : 'dirty' });
      schedule();
    },

    undo: () => {
      const { past, doc, future } = get();
      if (!past.length || !doc) return;
      const prev = past[past.length - 1];
      set({ doc: prev.doc, past: past.slice(0, -1), future: [doc, ...future], saveState: 'dirty' });
      schedule();
    },

    redo: () => {
      const { past, doc, future } = get();
      if (!future.length || !doc) return;
      set({ doc: future[0], past: [...past, { doc, at: 0 }], future: future.slice(1), saveState: 'dirty' });
      schedule();
    },

    flush: async () => {
      if (saveTimer) clearTimeout(saveTimer);
      if (get().saveState === 'saved') return true;
      return doSave();
    },

    retrySave: () => {
      if (get().saveState === 'error') set({ saveState: 'dirty' });
      void doSave();
    },

    reset: () => set({ id: null, doc: null, template: null, past: [], future: [] }),
  };
});

// Warn before closing the tab with unsaved work.
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', (e) => {
    const s = useProject.getState().saveState;
    if (s === 'dirty' || s === 'saving' || s === 'error') {
      e.preventDefault();
      e.returnValue = '';
    }
  });
}
