import { apiClient } from "@/lib/api/client";
import type {
	ChatCreate,
	ChatMessageCreate,
	ChatMessageResponse,
	ChatResponse,
	ChatSessionList,
	NoteResponse,
} from "@/types";

export interface ListChatSessionsParams {
	skip?: number;
	limit?: number;
}

export interface ConvertChatToNotePayload {
	title?: string | null;
	folder_id?: number | null;
}

export async function createChatSession(payload: ChatCreate = {}): Promise<ChatResponse> {
	const response = await apiClient.post<ChatResponse>("/chat/sessions", payload);
	return response.data;
}

export async function listChatSessions(
	params: ListChatSessionsParams = {}
): Promise<ChatSessionList> {
	const response = await apiClient.get<ChatSessionList>("/chat/sessions", { params });
	return response.data;
}

export async function getChatSessionById(sessionId: number): Promise<ChatResponse> {
	const response = await apiClient.get<ChatResponse>(`/chat/sessions/${sessionId}`);
	return response.data;
}

export async function sendChatMessage(
	sessionId: number,
	payload: ChatMessageCreate
): Promise<ChatMessageResponse> {
	const response = await apiClient.post<ChatMessageResponse>(
		`/chat/sessions/${sessionId}/messages`,
		payload
	);
	return response.data;
}

export async function convertChatToNote(
	sessionId: number,
	payload: ConvertChatToNotePayload = {}
): Promise<NoteResponse> {
	const response = await apiClient.post<NoteResponse>(
		`/chat/sessions/${sessionId}/to-note`,
		payload
	);
	return response.data;
}
