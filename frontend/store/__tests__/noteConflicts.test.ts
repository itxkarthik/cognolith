import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { APIRequestError, apiClient, processOfflineQueue } from "@/lib/api/client";
import { loadConflictDraft, saveConflictDraft } from "@/lib/utils/conflictDrafts";
import { requestQueue } from "@/lib/utils/requestQueue";
import { useAuthStore } from "@/store/authStore";
import type { NoteResponse, NoteUpdate, User } from "@/types";

const originalAdapter = apiClient.defaults.adapter;

const updateNote = vi.fn<(id: number, payload: NoteUpdate) => Promise<NoteResponse>>();
const getNoteById = vi.fn<(id: number) => Promise<NoteResponse>>();

vi.mock("@/lib/api/notes", () => ({
  updateNote: (id: number, payload: NoteUpdate) => updateNote(id, payload),
  getNoteById: (id: number) => getNoteById(id),
  createFolder: vi.fn(),
  createNote: vi.fn(),
  createTag: vi.fn(),
  deleteNote: vi.fn(),
  listFolders: vi.fn(),
  listNotes: vi.fn(),
  listTags: vi.fn(),
}));

const { NoteConflictError, useNoteStore } = await import("../noteStore");

function note(revision: number, content = "text"): NoteResponse {
  return { id: 1, title: "Note", content, revision } as NoteResponse;
}

const conflict = () => new APIRequestError("changed elsewhere", { statusCode: 409, errorCode: "conflict" });

describe("note draft saves", () => {
  beforeEach(() => {
    updateNote.mockReset();
    getNoteById.mockReset();
    useNoteStore.setState({ notes: [note(1)], selectedNote: note(1), noteConflict: null, error: null });
  });

  it("sends the revision each previous save returned", async () => {
    updateNote.mockImplementation(async (_id, payload) =>
      note((payload.expected_revision ?? 0) + 1, payload.content),
    );

    await Promise.all([
      useNoteStore.getState().saveNoteDraft(1, { content: "a" }),
      useNoteStore.getState().saveNoteDraft(1, { content: "ab" }),
    ]);

    expect(updateNote.mock.calls.map(([, payload]) => payload.expected_revision)).toEqual([1, 2]);
    expect(useNoteStore.getState().selectedNote?.revision).toBe(3);
  });

  it("records the server copy when the note changed elsewhere", async () => {
    updateNote.mockRejectedValueOnce(conflict());
    getNoteById.mockResolvedValueOnce(note(5, "theirs"));

    await expect(useNoteStore.getState().saveNoteDraft(1, { content: "mine" })).rejects.toBeInstanceOf(NoteConflictError);

    expect(useNoteStore.getState().noteConflict).toEqual({ noteId: 1, latest: note(5, "theirs") });
    // Further autosaves wait for the user's choice instead of sending stale writes
    await expect(useNoteStore.getState().saveNoteDraft(1, { content: "mine 2" })).rejects.toBeInstanceOf(NoteConflictError);
    expect(updateNote).toHaveBeenCalledTimes(1);
  });

  it("keeping mine overwrites from the server revision", async () => {
    useNoteStore.setState({ noteConflict: { noteId: 1, latest: note(5, "theirs") } });
    updateNote.mockResolvedValueOnce(note(6, "mine"));

    await useNoteStore.getState().resolveNoteConflict("mine", { content: "mine" });

    expect(updateNote).toHaveBeenCalledWith(1, { content: "mine", expected_revision: 5 });
    expect(useNoteStore.getState().noteConflict).toBeNull();
    expect(useNoteStore.getState().selectedNote?.content).toBe("mine");
  });

  it("loading theirs discards the draft without writing", async () => {
    useNoteStore.setState({ noteConflict: { noteId: 1, latest: note(5, "theirs") } });

    const latest = await useNoteStore.getState().resolveNoteConflict("theirs");

    expect(latest?.content).toBe("theirs");
    expect(updateNote).not.toHaveBeenCalled();
    expect(useNoteStore.getState().selectedNote?.revision).toBe(5);
  });
});

describe("offline edits refused on replay", () => {
  const OWNER = 7;

  beforeEach(() => {
    updateNote.mockReset();
    getNoteById.mockReset();
    const stored = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => void stored.set(key, value),
      removeItem: (key: string) => void stored.delete(key),
    });
    useAuthStore.setState({ user: { id: OWNER } as User, isAuthenticated: true });
    useNoteStore.setState({ notes: [note(1)], selectedNote: note(1), noteConflict: null, error: null });
  });

  afterEach(async () => {
    apiClient.defaults.adapter = originalAdapter;
    await requestQueue.clear();
    vi.unstubAllGlobals();
  });

  it("keep the typed text across a reload until a version is chosen", async () => {
    requestQueue.add(OWNER, "PATCH", "/notes/1", { data: { content: "typed offline", expected_revision: 1 } });
    apiClient.defaults.adapter = async (config) => {
      const isMe = config.url === "/users/me";
      const response = { data: isMe ? { id: OWNER } : {}, status: isMe ? 200 : 409, statusText: "", headers: {}, config };
      if (isMe) return response;
      throw Object.assign(new Error("HTTP 409"), { isAxiosError: true, response, config });
    };
    getNoteById.mockResolvedValue(note(2, "changed elsewhere"));

    await processOfflineQueue();
    await vi.waitFor(() => expect(useNoteStore.getState().noteConflict?.draft?.content).toBe("typed offline"));
    expect(requestQueue.isEmpty()).toBe(true);

    // A reload loses the store, not the refused edits
    useNoteStore.setState({ noteConflict: null });
    await useNoteStore.getState().restoreNoteConflict(1);
    expect(useNoteStore.getState().noteConflict?.draft?.content).toBe("typed offline");

    updateNote.mockImplementation(async (_id, payload) => note(3, payload.content));
    await useNoteStore.getState().resolveNoteConflict("mine", { content: "typed offline" });
    expect(updateNote).toHaveBeenLastCalledWith(1, { content: "typed offline", expected_revision: 2 });
    expect(loadConflictDraft(1, OWNER)).toBeNull();
  });

  it("are not offered to another account", async () => {
    saveConflictDraft(1, OWNER, { content: "private" });
    useAuthStore.setState({ user: { id: 8 } as User });

    await useNoteStore.getState().restoreNoteConflict(1);

    expect(useNoteStore.getState().noteConflict).toBeNull();
    expect(getNoteById).not.toHaveBeenCalled();
  });
});
