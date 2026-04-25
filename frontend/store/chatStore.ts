import { create } from "zustand";

import {
	convertChatToNote,
	createChatSession,
	getChatSessionById,
	listChatSessions,
	sendChatMessage,
	type ConvertChatToNotePayload,
	type ListChatSessionsParams,
} from "@/lib/api/chat";
import type {
	ChatCreate,
	ChatMessageResponse,
	ChatResponse,
	NoteResponse,
} from "@/types";

type StreamedMessages = Record<number, string>;

interface ChatState {
	sessions: ChatResponse[];
	total: number;
	selectedSession: ChatResponse | null;
	isLoading: boolean;
	isCreatingSession: boolean;
	isSendingMessage: boolean;
	isSavingAsNote: boolean;
	streamingMessageId: number | null;
	streamedMessages: StreamedMessages;
	error: string | null;
	fetchSessions: (params?: ListChatSessionsParams) => Promise<void>;
	fetchSessionById: (sessionId: number) => Promise<void>;
	createSession: (payload?: ChatCreate) => Promise<ChatResponse>;
	sendMessage: (sessionId: number, content: string) => Promise<ChatMessageResponse>;
	saveSessionAsNote: (sessionId: number, payload?: ConvertChatToNotePayload) => Promise<NoteResponse>;
	setSelectedSession: (session: ChatResponse | null) => void;
	clearError: () => void;
}

function sortByLastMessageAt(sessions: ChatResponse[]): ChatResponse[] {
	return [...sessions].sort((left, right) => {
		const leftTime = new Date(left.last_message_at).getTime();
		const rightTime = new Date(right.last_message_at).getTime();
		return rightTime - leftTime;
	});
}

function upsertSession(sessions: ChatResponse[], session: ChatResponse): ChatResponse[] {
	const exists = sessions.some((item) => item.id === session.id);
	if (!exists) {
		return sortByLastMessageAt([session, ...sessions]);
	}

	return sortByLastMessageAt(
		sessions.map((item) => (item.id === session.id ? session : item))
	);
}

function createTemporaryUserMessage(sessionId: number, content: string): ChatMessageResponse {
	const now = new Date().toISOString();
	return {
		id: -Date.now(),
		session_id: sessionId,
		role: "user",
		content,
		created_at: now,
		updated_at: now,
	};
}

async function streamAssistantMessage(
	messageId: number,
	fullContent: string,
	set: (partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>)) => void
): Promise<void> {
	if (!fullContent) {
		return;
	}

	set((state) => ({
		streamingMessageId: messageId,
		streamedMessages: {
			...state.streamedMessages,
			[messageId]: "",
		},
	}));

	const chunkSize = 16;
	for (let pointer = chunkSize; pointer < fullContent.length + chunkSize; pointer += chunkSize) {
		set((state) => ({
			streamedMessages: {
				...state.streamedMessages,
				[messageId]: fullContent.slice(0, Math.min(pointer, fullContent.length)),
			},
		}));

		await new Promise((resolve) => {
			setTimeout(resolve, 18);
		});
	}

	set((state) => {
		const nextStreamed = { ...state.streamedMessages };
		delete nextStreamed[messageId];

		return {
			streamedMessages: nextStreamed,
			streamingMessageId: state.streamingMessageId === messageId ? null : state.streamingMessageId,
		};
	});
}

export const useChatStore = create<ChatState>((set) => ({
	sessions: [],
	total: 0,
	selectedSession: null,
	isLoading: false,
	isCreatingSession: false,
	isSendingMessage: false,
	isSavingAsNote: false,
	streamingMessageId: null,
	streamedMessages: {},
	error: null,

	fetchSessions: async (params = {}) => {
		set({ isLoading: true, error: null });
		try {
			const response = await listChatSessions({
				skip: params.skip ?? 0,
				limit: params.limit ?? 30,
			});

			set((state) => {
				const selectedId = state.selectedSession?.id;
				const nextSessions = sortByLastMessageAt(response.data ?? []);
				const selectedSession = selectedId
					? nextSessions.find((item) => item.id === selectedId) ?? state.selectedSession
					: state.selectedSession;

				return {
					sessions: nextSessions,
					total: response.count ?? 0,
					selectedSession,
					isLoading: false,
				};
			});
		} catch (error) {
			set({
				isLoading: false,
				error: error instanceof Error ? error.message : "Failed to load chat sessions.",
			});
		}
	},

	fetchSessionById: async (sessionId) => {
		set({ isLoading: true, error: null });
		try {
			const session = await getChatSessionById(sessionId);
			set((state) => ({
				sessions: upsertSession(state.sessions, session),
				selectedSession: session,
				isLoading: false,
			}));
		} catch (error) {
			set({
				isLoading: false,
				error: error instanceof Error ? error.message : "Failed to load chat session.",
			});
		}
	},

	createSession: async (payload = {}) => {
		set({ isCreatingSession: true, error: null });
		try {
			const session = await createChatSession(payload);
			set((state) => ({
				sessions: upsertSession(state.sessions, session),
				total: state.total + 1,
				selectedSession: session,
				isCreatingSession: false,
			}));
			return session;
		} catch (error) {
			const message = error instanceof Error ? error.message : "Failed to create chat session.";
			set({ isCreatingSession: false, error: message });
			throw new Error(message);
		}
	},

	sendMessage: async (sessionId, content) => {
		const normalizedContent = content.trim();
		if (!normalizedContent) {
			throw new Error("Message content is required.");
		}

		const optimisticUserMessage = createTemporaryUserMessage(sessionId, normalizedContent);
		set((state) => {
			if (!state.selectedSession || state.selectedSession.id !== sessionId) {
				return {
					isSendingMessage: true,
					error: null,
				};
			}

			return {
				selectedSession: {
					...state.selectedSession,
					messages: [...state.selectedSession.messages, optimisticUserMessage],
					last_message_at: optimisticUserMessage.created_at,
				},
				isSendingMessage: true,
				error: null,
			};
		});

		try {
			const assistantMessage = await sendChatMessage(sessionId, {
				content: normalizedContent,
				role: "user",
			});

			const refreshedSession = await getChatSessionById(sessionId);
			set((state) => ({
				sessions: upsertSession(state.sessions, refreshedSession),
				selectedSession: refreshedSession,
			}));

			await streamAssistantMessage(assistantMessage.id, assistantMessage.content, set);

			set({ isSendingMessage: false });
			return assistantMessage;
		} catch (error) {
			const message = error instanceof Error ? error.message : "Failed to send message.";

			set((state) => {
				if (!state.selectedSession || state.selectedSession.id !== sessionId) {
					return {
						isSendingMessage: false,
						error: message,
					};
				}

				return {
					selectedSession: {
						...state.selectedSession,
						messages: state.selectedSession.messages.filter(
							(item) => item.id !== optimisticUserMessage.id
						),
					},
					isSendingMessage: false,
					error: message,
				};
			});

			throw new Error(message);
		}
	},

	saveSessionAsNote: async (sessionId, payload = {}) => {
		set({ isSavingAsNote: true, error: null });
		try {
			const note = await convertChatToNote(sessionId, payload);
			set({ isSavingAsNote: false });
			return note;
		} catch (error) {
			const message = error instanceof Error ? error.message : "Failed to save chat as note.";
			set({ isSavingAsNote: false, error: message });
			throw new Error(message);
		}
	},

	setSelectedSession: (session) => {
		set({ selectedSession: session });
	},

	clearError: () => {
		set({ error: null });
	},
}));
