import { create } from "zustand";

import { APIRequestError, onOfflineReplay } from "@/lib/api/client";
import {
	loadConflictDraft,
	removeConflictDraft,
	saveConflictDraft,
	type ConflictDraft,
} from "@/lib/utils/conflictDrafts";
import {
	createFolder as createFolderRequest,
	createNote as createNoteRequest,
	createTag as createTagRequest,
	deleteNote as deleteNoteRequest,
	getNoteById,
	listFolders as listFoldersRequest,
	listNotes,
	listTags as listTagsRequest,
	updateNote as updateNoteRequest,
	type ListNotesParams,
} from "@/lib/api/notes";
import type {
	FolderCreate,
	NoteCreate,
	NoteFolder,
	NoteResponse,
	NoteTag,
	NoteUpdate,
	TagCreate,
} from "@/types";
import { useAuthStore } from "@/store/authStore";

type NotesViewMode = "grid" | "list";

export type NoteDraftUpdate = ConflictDraft;

// The note changed elsewhere after this editor loaded it; `latest` is the server copy
export interface NoteConflict {
	noteId: number;
	latest: NoteResponse;
	// Edits made offline that the server refused; the editor shows them until resolved
	draft?: NoteDraftUpdate;
}

export class NoteConflictError extends Error {
	constructor() {
		super("This note was changed in another tab or device.");
		this.name = "NoteConflictError";
	}
}

// Draft saves per note, chained so each one sends the revision the previous returned
const draftSaves = new Map<number, Promise<unknown>>();

interface NoteFilters {
	search: string;
	folderId: number | null;
	tagId: number | null;
	viewMode: NotesViewMode;
	skip: number;
	limit: number;
}

interface NoteState {
	notes: NoteResponse[];
	total: number;
	selectedNote: NoteResponse | null;
	folders: NoteFolder[];
	tags: NoteTag[];
	filters: NoteFilters;
	isLoading: boolean;
	isSaving: boolean;
	isDeleting: boolean;
	error: string | null;
	fetchNotes: (params?: Partial<ListNotesParams>) => Promise<void>;
	fetchNoteById: (id: number) => Promise<void>;
	createNote: (payload: NoteCreate) => Promise<NoteResponse>;
	updateNoteById: (id: number, payload: NoteUpdate) => Promise<NoteResponse>;
	noteConflict: NoteConflict | null;
	// Save editor content based on the last revision this tab saw
	saveNoteDraft: (id: number, payload: NoteDraftUpdate) => Promise<NoteResponse>;
	// "mine" overwrites the newer server copy with `draft`; "theirs" discards the draft
	resolveNoteConflict: (choice: "mine" | "theirs", draft?: NoteDraftUpdate) => Promise<NoteResponse | null>;
	// Raise the conflict again for offline edits refused in an earlier session
	restoreNoteConflict: (id: number) => Promise<void>;
	deleteNoteById: (id: number) => Promise<void>;
	fetchFolders: () => Promise<void>;
	fetchTags: () => Promise<void>;
	createFolder: (payload: FolderCreate) => Promise<NoteFolder>;
	createTag: (payload: TagCreate) => Promise<NoteTag>;
	setSelectedNote: (note: NoteResponse | null) => void;
	setSearch: (search: string) => void;
	setFolderFilter: (folderId: number | null) => void;
	setTagFilter: (tagId: number | null) => void;
	setViewMode: (mode: NotesViewMode) => void;
	clearError: () => void;
}

function isConflict(error: unknown): boolean {
	return error instanceof APIRequestError && error.statusCode === 409;
}

function buildListQuery(filters: NoteFilters, params: Partial<ListNotesParams> = {}): ListNotesParams {
	const search = params.search ?? filters.search;
	const folder_id = params.folder_id ?? filters.folderId ?? undefined;
	const tag_id = params.tag_id ?? filters.tagId ?? undefined;
	const skip = params.skip ?? filters.skip;
	const limit = params.limit ?? filters.limit;

	const query: ListNotesParams = {
		skip,
		limit,
	};

	if (search?.trim()) {
		query.search = search.trim();
	}

	if (folder_id) {
		query.folder_id = folder_id;
	}

	if (tag_id) {
		query.tag_id = tag_id;
	}

	return query;
}

export const useNoteStore = create<NoteState>((set, get) => ({
	notes: [],
	total: 0,
	selectedNote: null,
	noteConflict: null,
	folders: [],
	tags: [],
	filters: {
		search: "",
		folderId: null,
		tagId: null,
		viewMode: "grid",
		skip: 0,
		limit: 24,
	},
	isLoading: false,
	isSaving: false,
	isDeleting: false,
	error: null,

	fetchNotes: async (params = {}) => {
		set({ isLoading: true, error: null });
		try {
			const filters = get().filters;
			const query = buildListQuery(filters, params);
			const response = await listNotes(query);

			set((state) => {
				const selectedNoteStillExists = state.selectedNote
					? response.data.some((note) => note.id === state.selectedNote?.id)
					: false;

				return {
					notes: response.data ?? [],
					total: response.count ?? 0,
					selectedNote:
						selectedNoteStillExists && state.selectedNote
							? response.data.find((note) => note.id === state.selectedNote?.id) ?? null
							: null,
					isLoading: false,
					filters: {
						...state.filters,
						search: query.search ?? "",
						folderId: query.folder_id ?? null,
						tagId: query.tag_id ?? null,
						skip: query.skip ?? 0,
						limit: query.limit ?? 24,
					},
				};
			});
		} catch (error) {
			set({
				isLoading: false,
				error: error instanceof Error ? error.message : "Failed to fetch notes.",
			});
		}
	},

	fetchNoteById: async (id) => {
		set({ isLoading: true, error: null });
		try {
			const note = await getNoteById(id);
			set({ selectedNote: note, isLoading: false });
		} catch (error) {
			set({
				isLoading: false,
				error: error instanceof Error ? error.message : "Failed to fetch note.",
			});
		}
	},

	createNote: async (payload) => {
		set({ isSaving: true, error: null });
		try {
			const note = await createNoteRequest(payload);
			set((state) => ({
				notes: [note, ...state.notes],
				total: state.total + 1,
				selectedNote: note,
				isSaving: false,
			}));
			return note;
		} catch (error) {
			const message = error instanceof Error ? error.message : "Failed to create note.";
			set({ isSaving: false, error: message });
			throw new Error(message);
		}
	},

	updateNoteById: async (id, payload) => {
		set({ isSaving: true, error: null });
		try {
			const updated = await updateNoteRequest(id, payload);
			set((state) => ({
				notes: state.notes.map((note) => (note.id === id ? updated : note)),
				selectedNote: state.selectedNote?.id === id ? updated : state.selectedNote,
				isSaving: false,
			}));
			return updated;
		} catch (error) {
			const message = error instanceof Error ? error.message : "Failed to update note.";
			set({ isSaving: false, error: message });
			// Keep the request error: callers tell a conflict (409) from other failures
			throw error instanceof APIRequestError ? error : new Error(message);
		}
	},

	saveNoteDraft: (id, payload) => {
		const previous = draftSaves.get(id) ?? Promise.resolve();
		const run = previous
			.catch(() => undefined)
			.then(async () => {
				if (get().noteConflict?.noteId === id) throw new NoteConflictError();
				const known = get().selectedNote?.id === id ? get().selectedNote : get().notes.find((note) => note.id === id);
				try {
					return await get().updateNoteById(id, { ...payload, expected_revision: known?.revision });
				} catch (error) {
					if (!isConflict(error)) throw error;
					const latest = await getNoteById(id);
					set({ noteConflict: { noteId: id, latest }, error: null });
					throw new NoteConflictError();
				}
			});
		draftSaves.set(id, run);
		void run.finally(() => {
			if (draftSaves.get(id) === run) draftSaves.delete(id);
		}).catch(() => undefined);
		return run;
	},

	resolveNoteConflict: async (choice, draft) => {
		const conflict = get().noteConflict;
		if (!conflict) return null;
		const { noteId, latest } = conflict;
		if (choice === "theirs") {
			removeConflictDraft(noteId);
			set((state) => ({
				noteConflict: null,
				notes: state.notes.map((note) => (note.id === noteId ? latest : note)),
				selectedNote: state.selectedNote?.id === noteId ? latest : state.selectedNote,
			}));
			return latest;
		}
		set({ noteConflict: null });
		try {
			const saved = await get().updateNoteById(noteId, { ...draft, expected_revision: latest.revision });
			removeConflictDraft(noteId);
			return saved;
		} catch (error) {
			if (isConflict(error)) {
				// Changed again while deciding: ask again against the newest copy
				set({ noteConflict: { ...conflict, latest: await getNoteById(noteId) }, error: null });
				throw new NoteConflictError();
			}
			// Not saved: keep asking, so the offline edits aren't dropped from view
			set({ noteConflict: conflict });
			throw error;
		}
	},

	restoreNoteConflict: async (id) => {
		if (get().noteConflict?.noteId === id) return;
		const ownerId = useAuthStore.getState().user?.id;
		const draft = ownerId === undefined ? null : loadConflictDraft(id, ownerId);
		if (!draft) return;
		const latest = await getNoteById(id);
		if (!get().noteConflict) set({ noteConflict: { noteId: id, latest, draft } });
	},

	deleteNoteById: async (id) => {
		set({ isDeleting: true, error: null });
		try {
			await deleteNoteRequest(id);
			set((state) => ({
				notes: state.notes.filter((note) => note.id !== id),
				total: Math.max(0, state.total - 1),
				selectedNote: state.selectedNote?.id === id ? null : state.selectedNote,
				isDeleting: false,
			}));
		} catch (error) {
			const message = error instanceof Error ? error.message : "Failed to delete note.";
			set({ isDeleting: false, error: message });
			throw new Error(message);
		}
	},

	fetchFolders: async () => {
		try {
			const folders = await listFoldersRequest();
			set({ folders });
		} catch (error) {
			set({ error: error instanceof Error ? error.message : "Failed to fetch folders." });
		}
	},

	fetchTags: async () => {
		try {
			const tags = await listTagsRequest();
			set({ tags });
		} catch (error) {
			set({ error: error instanceof Error ? error.message : "Failed to fetch tags." });
		}
	},

	createFolder: async (payload) => {
		const folder = await createFolderRequest(payload);
		set((state) => ({
			folders: [...state.folders, folder].sort((a, b) => a.name.localeCompare(b.name)),
		}));
		return folder;
	},

	createTag: async (payload) => {
		const tag = await createTagRequest(payload);
		set((state) => ({
			tags: [...state.tags, tag].sort((a, b) => a.name.localeCompare(b.name)),
		}));
		return tag;
	},

	setSelectedNote: (note) => {
		set({ selectedNote: note });
	},

	setSearch: (search) => {
		set((state) => ({
			filters: {
				...state.filters,
				search,
				skip: 0,
			},
		}));
	},

	setFolderFilter: (folderId) => {
		set((state) => ({
			filters: {
				...state.filters,
				folderId,
				skip: 0,
			},
		}));
	},

	setTagFilter: (tagId) => {
		set((state) => ({
			filters: {
				...state.filters,
				tagId,
				skip: 0,
			},
		}));
	},

	setViewMode: (mode) => {
		set((state) => ({
			filters: {
				...state.filters,
				viewMode: mode,
			},
		}));
	},

	clearError: () => {
		set({ error: null });
	},
}));

const NOTE_URL = /^\/notes\/(\d+)$/;

// A note save queued offline has now been replayed
onOfflineReplay((request, result) => {
	const match = request.method === "PATCH" ? NOTE_URL.exec(request.url) : null;
	if (!match) return;
	const noteId = Number(match[1]);
	if (result.status === "applied") {
		const saved = result.data as NoteResponse;
		// Take its revision, so the next save isn't mistaken for a stale one
		useNoteStore.setState((state) => ({
			notes: state.notes.map((note) => (note.id === noteId ? saved : note)),
			selectedNote: state.selectedNote?.id === noteId ? saved : state.selectedNote,
		}));
	} else if (result.status === "conflict") {
		// The queued write is gone now; keep its edits until the user picks a version
		const draft: NoteDraftUpdate = { ...(request.data as NoteUpdate | undefined) };
		delete (draft as NoteUpdate).expected_revision;
		saveConflictDraft(noteId, request.ownerId, draft);
		void getNoteById(noteId)
			.then((latest) => useNoteStore.setState({ noteConflict: { noteId, latest, draft } }))
			.catch(() => undefined);
	}
});
