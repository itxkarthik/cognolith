import { apiClient } from "@/lib/api/client";
import type {
	FolderCreate,
	MessageResponse,
	NoteCreate,
	NoteFolder,
	NoteList,
	NoteResponse,
	NoteTag,
	NoteUpdate,
	TagCreate,
} from "@/types";

export interface ListNotesParams {
	folder_id?: number;
	tag_id?: number;
	search?: string;
	skip?: number;
	limit?: number;
}

export async function listNotes(params: ListNotesParams = {}): Promise<NoteList> {
	const response = await apiClient.get<NoteList>("/notes/", { params });
	return response.data;
}

export async function getNoteById(id: number): Promise<NoteResponse> {
	const response = await apiClient.get<NoteResponse>(`/notes/${id}`);
	return response.data;
}

export async function createNote(payload: NoteCreate): Promise<NoteResponse> {
	const response = await apiClient.post<NoteResponse>("/notes/", payload);
	return response.data;
}

export async function updateNote(id: number, payload: NoteUpdate): Promise<NoteResponse> {
	const response = await apiClient.patch<NoteResponse>(`/notes/${id}`, payload);
	return response.data;
}

export async function deleteNote(id: number): Promise<MessageResponse> {
	const response = await apiClient.delete<MessageResponse>(`/notes/${id}`);
	return response.data;
}

export async function listFolders(): Promise<NoteFolder[]> {
	const response = await apiClient.get<NoteFolder[]>("/notes/folders");
	return response.data;
}

export async function createFolder(payload: FolderCreate): Promise<NoteFolder> {
	const response = await apiClient.post<NoteFolder>("/notes/folders", payload);
	return response.data;
}

export async function listTags(): Promise<NoteTag[]> {
	const response = await apiClient.get<NoteTag[]>("/notes/tags");
	return response.data;
}

export async function createTag(payload: TagCreate): Promise<NoteTag> {
	const response = await apiClient.post<NoteTag>("/notes/tags", payload);
	return response.data;
}
