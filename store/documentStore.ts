import { create } from "zustand";

import {
	deleteDocument as deleteDocumentRequest,
	getDocumentById,
	listDocuments,
	uploadDocument,
	type ListDocumentsParams,
	type UploadDocumentPayload,
} from "@/lib/api/documents";
import type { DocumentResponse } from "@/types";

interface DocumentState {
	documents: DocumentResponse[];
	total: number;
	selectedDocument: DocumentResponse | null;
	isLoading: boolean;
	isUploading: boolean;
	isDeleting: boolean;
	error: string | null;
	lastQuery: ListDocumentsParams;
	fetchDocuments: (params?: ListDocumentsParams) => Promise<void>;
	fetchDocumentById: (id: number) => Promise<void>;
	uploadDocumentFile: (payload: UploadDocumentPayload) => Promise<DocumentResponse>;
	deleteDocumentById: (id: number) => Promise<void>;
	clearSelectedDocument: () => void;
	clearError: () => void;
}

export const useDocumentStore = create<DocumentState>((set, get) => ({
	documents: [],
	total: 0,
	selectedDocument: null,
	isLoading: false,
	isUploading: false,
	isDeleting: false,
	error: null,
	lastQuery: {
		skip: 0,
		limit: 20,
	},

	fetchDocuments: async (params = {}) => {
		const resolvedQuery: ListDocumentsParams = {
			skip: params.skip ?? get().lastQuery.skip ?? 0,
			limit: params.limit ?? get().lastQuery.limit ?? 20,
			search: params.search,
		};

		set({ isLoading: true, error: null, lastQuery: resolvedQuery });

		try {
			const response = await listDocuments(resolvedQuery);
			set({
				documents: response.data ?? [],
				total: response.count ?? 0,
				isLoading: false,
			});
		} catch (error) {
			set({
				isLoading: false,
				error:
					error instanceof Error
						? error.message
						: "Failed to fetch documents.",
			});
		}
	},

	fetchDocumentById: async (id) => {
		set({ isLoading: true, error: null });
		try {
			const document = await getDocumentById(id);
			set({ selectedDocument: document, isLoading: false });
		} catch (error) {
			set({
				isLoading: false,
				error:
					error instanceof Error
						? error.message
						: "Failed to fetch document.",
			});
		}
	},

	uploadDocumentFile: async (payload) => {
		set({ isUploading: true, error: null });
		try {
			const document = await uploadDocument(payload);
			set((state) => ({
				documents: [document, ...state.documents],
				total: state.total + 1,
				selectedDocument: document,
				isUploading: false,
			}));
			return document;
		} catch (error) {
			const message =
				error instanceof Error ? error.message : "Failed to upload document.";
			set({ isUploading: false, error: message });
			throw new Error(message);
		}
	},

	deleteDocumentById: async (id) => {
		set({ isDeleting: true, error: null });
		try {
			await deleteDocumentRequest(id);
			set((state) => ({
				documents: state.documents.filter((item) => item.id !== id),
				total: Math.max(0, state.total - 1),
				selectedDocument:
					state.selectedDocument?.id === id ? null : state.selectedDocument,
				isDeleting: false,
			}));
		} catch (error) {
			const message =
				error instanceof Error ? error.message : "Failed to delete document.";
			set({
				isDeleting: false,
				error: message,
			});
			throw new Error(message);
		}
	},

	clearSelectedDocument: () => {
		set({ selectedDocument: null });
	},

	clearError: () => {
		set({ error: null });
	},
}));
