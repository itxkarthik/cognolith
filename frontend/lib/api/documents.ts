import { apiClient } from "@/lib/api/client";
import type {
	DocumentContentResponse,
	DocumentList,
	DocumentResponse,
	DocumentUpdate,
	MessageResponse,
} from "@/types";

export interface ListDocumentsParams {
	search?: string;
	skip?: number;
	limit?: number;
}

export interface UploadDocumentPayload {
	file: File;
	title?: string;
	tags?: string[];
	language?: string;
}

export async function listDocuments(
	params: ListDocumentsParams = {}
): Promise<DocumentList> {
	const response = await apiClient.get<DocumentList>("/documents/", { params });
	return response.data;
}

export async function getDocumentById(id: number): Promise<DocumentResponse> {
	const response = await apiClient.get<DocumentResponse>(`/documents/${id}`);
	return response.data;
}

export async function getDocumentContent(
	id: number
): Promise<DocumentContentResponse> {
	const response = await apiClient.get<DocumentContentResponse>(
		`/documents/${id}/content`
	);
	return response.data;
}

export async function uploadDocument(
	payload: UploadDocumentPayload
): Promise<DocumentResponse> {
	const formData = new FormData();
	formData.append("file", payload.file);

	if (payload.title?.trim()) {
		formData.append("title", payload.title.trim());
	}

	if (payload.tags && payload.tags.length > 0) {
		formData.append("tags", payload.tags.join(","));
	}

	formData.append("language", payload.language?.trim() || "en");

	const response = await apiClient.post<DocumentResponse>(
		"/documents/upload",
		formData,
		{
			headers: {
				"Content-Type": "multipart/form-data",
			},
		}
	);

	return response.data;
}

export async function updateDocument(
	id: number,
	payload: DocumentUpdate
): Promise<DocumentResponse> {
	const response = await apiClient.patch<DocumentResponse>(
		`/documents/${id}`,
		payload
	);
	return response.data;
}

export async function deleteDocument(id: number): Promise<MessageResponse> {
	const response = await apiClient.delete<MessageResponse>(`/documents/${id}`);
	return response.data;
}
