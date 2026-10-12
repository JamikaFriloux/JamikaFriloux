import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

/**
 * Replaceable blob storage. Keys are content addresses (sha256), so stored files are
 * immutable and safely shared between a live project and its issued revisions.
 * Swap `LocalFsStorage` for an S3/GCS adapter implementing the same interface.
 */
export interface StorageAdapter {
  put(data: Buffer): Promise<{ key: string; sha256: string }>;
  get(key: string): Promise<Buffer>;
  exists(key: string): Promise<boolean>;
}

export function sha256(data: Buffer): string {
  return crypto.createHash('sha256').update(data).digest('hex');
}

export class LocalFsStorage implements StorageAdapter {
  constructor(private root: string) {
    fs.mkdirSync(root, { recursive: true });
  }
  private file(key: string) {
    if (!/^[0-9a-f]{64}$/.test(key)) throw new Error('Invalid storage key');
    return path.join(this.root, key.slice(0, 2), key);
  }
  async put(data: Buffer) {
    const key = sha256(data);
    const f = this.file(key);
    if (!fs.existsSync(f)) {
      fs.mkdirSync(path.dirname(f), { recursive: true });
      const tmp = `${f}.${process.pid}.tmp`;
      fs.writeFileSync(tmp, data);
      fs.renameSync(tmp, f);
    }
    return { key, sha256: key };
  }
  async get(key: string) {
    return fs.promises.readFile(this.file(key));
  }
  async exists(key: string) {
    try {
      return fs.existsSync(this.file(key));
    } catch {
      return false;
    }
  }
}
