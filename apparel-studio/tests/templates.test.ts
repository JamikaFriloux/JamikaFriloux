import { describe, expect, it } from 'vitest';
import { listTemplates } from '../src/shared/templates';
import { garmentTemplateSchema } from '../src/shared/schema/template';
import { pointInPath, parsePath } from '../src/shared/geometry';
import { createProjectDoc } from '../src/shared/domain/factory';
import { projectDocSchema } from '../src/shared/schema/project';

const templates = listTemplates();

describe('garment library', () => {
  it('ships the three V1 garments', () => {
    expect(templates.map((t) => t.id).sort()).toEqual(['hoodie-pullover', 'sweatpants-straight', 'tshirt-boxy']);
  });

  for (const t of templates) {
    describe(t.name, () => {
      it('validates against the template schema and parses every path', () => {
        expect(() => garmentTemplateSchema.parse(t)).not.toThrow();
        for (const v of t.views) {
          for (const p of v.panels) expect(parsePath(p.d).length).toBeGreaterThan(2);
          for (const s of v.seams) expect(parsePath(s.d).length).toBeGreaterThan(1);
        }
      });

      it('has front and back views and shared component ids', () => {
        expect(t.views.map((v) => v.id).sort()).toEqual(['back', 'front']);
        const comps = new Set(t.components.map((c) => c.id));
        for (const v of t.views) {
          for (const p of v.panels) expect(comps.has(p.componentId)).toBe(true);
          for (const s of v.seams) s.componentIds.forEach((c) => expect(comps.has(c)).toBe(true));
        }
        // Every component appears in at least one view; components shared between views keep the same id.
        for (const c of comps) expect(t.views.some((v) => v.panels.some((p) => p.componentId === c))).toBe(true);
        const front = new Set(t.views[0].panels.map((p) => p.componentId));
        const back = new Set(t.views[1].panels.map((p) => p.componentId));
        expect([...front].filter((c) => back.has(c)).length).toBeGreaterThan(0);
      });

      it('places every anchor inside a panel of its component', () => {
        for (const v of t.views) {
          for (const a of v.anchors) {
            const inside = v.panels.filter((p) => p.componentId === a.componentId).some((p) => pointInPath(p.d, a.x, a.y));
            expect(inside, `${t.id}/${v.id}/${a.id}`).toBe(true);
          }
        }
      });

      it('draws measurement lines that match the template default values (nominal scale)', () => {
        const k = t.calibration?.mmPerUnit ?? 1;
        for (const v of t.views) {
          for (const ml of v.measurementLines) {
            const pom = t.poms.find((p) => p.id === ml.pomId);
            expect(pom, `${t.id} line ${ml.pomId}`).toBeTruthy();
            if (pom?.defaultMm == null) continue;
            const len = Math.hypot(ml.to[0] - ml.from[0], ml.to[1] - ml.from[1]) * k;
            expect(Math.abs(len - pom.defaultMm), `${t.id} ${pom.code}: drawn ${len.toFixed(1)} vs ${pom.defaultMm}`).toBeLessThanOrEqual(3);
          }
        }
        // Every POM has a diagram line or an explicit no-default reason.
        for (const p of t.poms) {
          const drawn = t.views.some((v) => v.measurementLines.some((m) => m.pomId === p.id));
          expect(drawn || p.defaultMm === null, `${t.id} ${p.code} has no diagram line`).toBe(true);
        }
      });

      it('has matched ghost assets covering both views with a full mesh', () => {
        expect(t.ghost).not.toBeNull();
        for (const v of t.views) {
          const g = t.ghost!.views[v.id]!;
          expect(g.mesh.dst).toHaveLength(g.mesh.cols * g.mesh.rows);
          expect(g.mesh.bounds).toEqual(v.viewBox);
          for (const fg of g.foregroundComponents) expect(t.components.some((c) => c.id === fg)).toBe(true);
        }
      });

      it('creates a valid new project with unconfirmed template defaults', () => {
        const doc = createProjectDoc(t, { name: 'x', styleNumber: 'x' });
        expect(() => projectDocSchema.parse(doc)).not.toThrow();
        expect(doc.measurements.every((p) => !p.confirmed)).toBe(true);
        expect(doc.layers.filter((l) => l.type === 'panelFill').map((l) => l.targets[0]).sort()).toEqual(t.components.map((c) => c.id).sort());
      });
    });
  }

  it('keeps pullover garments structurally pullover regardless of decorations', () => {
    const hoodie = templates.find((t) => t.id === 'hoodie-pullover')!;
    expect(hoodie.structure.closure).toBe('pullover');
    expect(hoodie.components.some((c) => /zip/.test(c.id))).toBe(false);
  });
});
