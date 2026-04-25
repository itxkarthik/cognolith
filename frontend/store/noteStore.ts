import { create } from "zustand";

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

type NotesViewMode = "grid" | "list";

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
							: state.selectedNote,
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
			throw new Error(message);
		}
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
