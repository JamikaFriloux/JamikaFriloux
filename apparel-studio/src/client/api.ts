import type { AssetRef, ProjectDoc, ProjectRecord, ProjectSummary, RevisionSummary } from '../shared/schema/project';
import type { Check } from '../shared/domain/validation';

export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
  }
}

async function call<T>(method: string, url: string, body?: unknown, raw = false): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: body instanceof FormData || body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Cannot reach the Apparel Studio server. Check that `npm run dev` is running, then try again.');
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    let details: unknown;
    try {
      const j = await res.json();
      msg = j.error ?? msg;
      details = j.details;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg, details);
  }
  if (res.status === 204) return undefined as T;
  return (raw ? res.blob() : res.json()) as Promise<T>;
}

export const api = {
  listProjects: (archived = false) => call<ProjectSummary[]>('GET', `/api/projects${archived ? '?archived=1' : ''}`),
  createProject: (input: { templateId: string; name: string; styleNumber: string; collection?: string; season?: string }) =>
    call<ProjectRecord>('POST', '/api/projects', input),
  getProject: (id: string) => call<ProjectRecord>('GET', `/api/projects/${id}`),
  saveProject: (id: string, doc: ProjectDoc, version: number) => call<{ version: number; updatedAt: string }>('PUT', `/api/projects/${id}`, { doc, version }),
  setArchived: (id: string, archived: boolean) => call<ProjectRecord>('PATCH', `/api/projects/${id}`, { archived }),
  deleteProject: (id: string) => call<void>('DELETE', `/api/projects/${id}`),
  duplicate: (id: string, name?: string, styleNumber?: string) => call<ProjectRecord>('POST', `/api/projects/${id}/duplicate`, { name, styleNumber }),
  uploadAsset: (id: string, file: File, role: AssetRef['role']) => {
    const fd = new FormData();
    fd.append('role', role);
    fd.append('file', file);
    return call<{ asset: AssetRef; warnings: string[] }>('POST', `/api/projects/${id}/assets`, fd);
  },
  uploadMockup: (id: string, png: Blob) => {
    const fd = new FormData();
    fd.append('file', png, 'mockup.png');
    return call<{ sha256: string }>('POST', `/api/projects/${id}/mockups`, fd);
  },
  revisions: (id: string) => call<RevisionSummary[]>('GET', `/api/projects/${id}/revisions`),
  issueRevision: (id: string, body: { kind: 'draft' | 'review'; notes: string; expectedVersion?: number; mockups?: { front?: string; back?: string } }) =>
    call<RevisionSummary>('POST', `/api/projects/${id}/revisions`, body),
  retryExports: (revisionId: string) => call<unknown>('POST', `/api/revisions/${revisionId}/exports/retry`),
  previewPdf: (id: string) => call<Blob>('POST', `/api/projects/${id}/techpack/preview`, {}, true),
  validation: (id: string) => call<{ checks: Check[] }>('GET', `/api/projects/${id}/validation`),
};

export const blobUrl = (sha256: string) => `/api/blobs/${sha256}`;
export const exportUrl = (exportId: string, inline = false) => `/api/exports/${exportId}/download${inline ? '?inline=1' : ''}`;
