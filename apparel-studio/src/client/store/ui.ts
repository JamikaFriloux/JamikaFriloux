import { create } from 'zustand';
import type { ViewId } from '../../shared/schema/template';

export type Tool =
  | { kind: 'select' }
  | { kind: 'pan' }
  | { kind: 'erase'; mode: 'erase' | 'restore'; size: number }
  | { kind: 'place-embellishment' }
  | { kind: 'draw-path'; points: { x: number; y: number }[] }
  | { kind: 'place-hardware'; hardwareId: string }
  | { kind: 'place-note' };

interface UiState {
  view: ViewId;
  preview: 'technical' | 'realistic';
  colorwayId: string | null;
  selectedComponentId: string | null;
  selectedLayerId: string | null;
  leftTab: 'parts' | 'layers';
  tool: Tool;
  zoom: number;
  pan: { x: number; y: number };
  showAnchors: boolean;
  toast: { kind: 'info' | 'warn' | 'error'; text: string; id: number } | null;
  set: (p: Partial<Omit<UiState, 'set' | 'notify'>>) => void;
  selectComponent: (id: string | null) => void;
  selectLayer: (id: string | null) => void;
  notify: (kind: 'info' | 'warn' | 'error', text: string) => void;
}

export const useUi = create<UiState>((set) => ({
  view: 'front',
  preview: 'technical',
  colorwayId: null,
  selectedComponentId: null,
  selectedLayerId: null,
  leftTab: 'parts',
  tool: { kind: 'select' },
  zoom: 1,
  pan: { x: 0, y: 0 },
  showAnchors: false,
  toast: null,
  set: (p) => set(p),
  selectComponent: (id) => set({ selectedComponentId: id, selectedLayerId: null, tool: { kind: 'select' } }),
  selectLayer: (id) => set({ selectedLayerId: id, selectedComponentId: null }),
  notify: (kind, text) => set({ toast: { kind, text, id: Date.now() } }),
}));
