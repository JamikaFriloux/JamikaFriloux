import { customAlphabet } from 'nanoid';

const gen = customAlphabet('0123456789abcdefghijklmnopqrstuvwxyz', 10);

/** Stable short ids with a readable type prefix, e.g. `lyr_k3j9x0a1bc`. */
export function newId(prefix: string): string {
  return `${prefix}_${gen()}`;
}
