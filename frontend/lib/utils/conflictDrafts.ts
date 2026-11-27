/**
 * Offline note edits the server refused because the note changed meanwhile.
 *
 * A replayed save is removed from the offline queue whatever its outcome, and after a
 * reload it may be the only copy of what was typed offline. It is kept here until the
 * user picks a version, so "Keep mine" still has the text to save.
 */

import type { NoteUpdate } from "@/types";

export type ConflictDraft = Omit<NoteUpdate, "expected_revision">;

interface StoredDraft {
  ownerId: number;
  draft: ConflictDraft;
}

const STORAGE_KEY = "cognolith-note-conflict-drafts";

// Storage can be missing (server rendering) or throw (blocked in some private modes)
function read(): Record<string, StoredDraft> {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? (parsed as Record<string, StoredDraft>) : {};
  } catch {
    return {};
  }
}

function write(drafts: Record<string, StoredDraft>): void {
  try {
    if (Object.keys(drafts).length === 0) globalThis.localStorage?.removeItem(STORAGE_KEY);
    else globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(drafts));
  } catch {
    // Kept in memory by the caller for this session only
  }
}

export function saveConflictDraft(noteId: number, ownerId: number, draft: ConflictDraft): void {
  write({ ...read(), [noteId]: { ownerId, draft } });
}

/** The draft kept for `noteId`, if `ownerId` is the account that wrote it. */
export function loadConflictDraft(noteId: number, ownerId: number): ConflictDraft | null {
  const stored = read()[noteId];
  return stored && stored.ownerId === ownerId ? stored.draft : null;
}

export function removeConflictDraft(noteId: number): void {
  const drafts = read();
  if (!(noteId in drafts)) return;
  delete drafts[noteId];
  write(drafts);
}

/** On logout: the drafts hold this account's content. */
export function clearConflictDrafts(): void {
  write({});
}
