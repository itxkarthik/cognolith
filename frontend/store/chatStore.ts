import { create } from "zustand";

import {
	convertChatToNote,
	createChatSession,
	getChatSessionById,
	listChatSessions,
	type ConvertChatToNotePayload,
	type ListChatSessionsParams,
} from "@/lib/api/chat";
import { cancelStreamingMessage, retryChatMessage, streamChatMessage, type ChatStreamEvent } from "@/lib/api/stream";
import type {
	ChatCreate,
	ChatMessageResponse,
	ChatResponse,
	NoteResponse,
} from "@/types";
import {
	beginChatRequest,
	endChatRequest,
	isChatRequestPending,
	type PendingChatRequests,
} from "./chatRequestState";

type StreamedMessages = Record<number, string>;

interface ChatState {
	sessions: ChatResponse[];
	total: number;
	selectedSession: ChatResponse | null;
	isLoading: boolean;
	isCreatingSession: boolean;
	pendingMessageRequests: PendingChatRequests;
	isSavingAsNote: boolean;
	streamingMessageId: number | null;
	streamedMessages: StreamedMessages;
	error: string | null;
	fetchSessions: (params?: ListChatSessionsParams) => Promise<void>;
	fetchSessionById: (sessionId: number) => Promise<void>;
	createSession: (payload?: ChatCreate) => Promise<ChatResponse>;
	sendMessage: (sessionId: number, content: string) => Promise<ChatMessageResponse>;
	cancelMessage: (sessionId: number) => Promise<void>;
	retryMessage: (sessionId: number, messageId: number) => Promise<ChatMessageResponse>;
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

const activeControllers = new Map<number, AbortController>();

function replaceMessage(messages: ChatMessageResponse[], message: ChatMessageResponse): ChatMessageResponse[] {
	const found = messages.some((item) => item.id === message.id);
	return found ? messages.map((item) => item.id === message.id ? message : item) : [...messages, message];
}

export const useChatStore = create<ChatState>((set, get) => ({
	sessions: [],
	total: 0,
	selectedSession: null,
	isLoading: false,
	isCreatingSession: false,
	pendingMessageRequests: {},
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
		if (isChatRequestPending(get().pendingMessageRequests, sessionId)) {
			throw new Error("A message is already being processed for this session.");
		}

		const normalizedContent = content.trim();
		if (!normalizedContent) {
			throw new Error("Message content is required.");
		}

		const optimisticUserMessage = createTemporaryUserMessage(sessionId, normalizedContent);
		set((state) => {
			const pendingMessageRequests = beginChatRequest(
				state.pendingMessageRequests,
				sessionId
			);
			if (!state.selectedSession || state.selectedSession.id !== sessionId) {
				return {
					pendingMessageRequests,
					error: null,
				};
			}

			return {
				selectedSession: {
					...state.selectedSession,
					messages: [...state.selectedSession.messages, optimisticUserMessage],
					last_message_at: optimisticUserMessage.created_at,
				},
				pendingMessageRequests,
				error: null,
			};
		});

		let started = false;
		let finalMessage: ChatMessageResponse | null = null;
		const controller = new AbortController();
		activeControllers.set(sessionId, controller);
		const applyEvent = (event: ChatStreamEvent) => {
			set((state) => {
				if (!state.selectedSession || state.selectedSession.id !== sessionId) return {};
				let messages = state.selectedSession.messages;
				if (event.type === "generation_started") {
					started = true;
					messages = messages.filter((item) => item.id !== optimisticUserMessage.id);
					messages = replaceMessage(replaceMessage(messages, event.user_message), event.assistant_message);
					return { selectedSession: { ...state.selectedSession, messages }, streamingMessageId: event.assistant_message.id };
				}
				if (event.type === "token") {
					messages = messages.map((item) => item.id === event.message_id ? { ...item, content: item.content + event.delta } : item);
				}
				if (event.type === "answer_reset") {
					messages = messages.map((item) => item.id === event.message_id ? { ...item, content: "", generation_metadata: { ...(item.generation_metadata ?? {}), repairing: true } } : item);
				}
				if (event.type === "retrieval_complete" && event.diagnostics) {
					messages = messages.map((item) => item.id === event.message_id ? { ...item, generation_metadata: { ...(item.generation_metadata ?? {}), retrieval: event.diagnostics } } : item);
				}
				if (event.type === "sources") {
					messages = messages.map((item) => item.id === event.message_id ? { ...item, sources: event.sources } : item);
				}
				if (event.type === "completed" || event.type === "cancelled") {
					finalMessage = event.message;
					messages = replaceMessage(messages, event.message);
					return { selectedSession: { ...state.selectedSession, messages }, streamingMessageId: null };
				}
				return { selectedSession: { ...state.selectedSession, messages } };
			});
		};

		try {
			await streamChatMessage(sessionId, normalizedContent, { signal: controller.signal, onEvent: applyEvent });
			if (!finalMessage) {
				const refreshed = await getChatSessionById(sessionId);
				finalMessage = [...refreshed.messages].reverse().find((item) => item.role === "assistant") ?? null;
				set((state) => ({ sessions: upsertSession(state.sessions, refreshed), selectedSession: refreshed }));
			}
			if (!finalMessage) throw new Error("The assistant response was not persisted.");
			return finalMessage;
		} catch (error) {
			if (controller.signal.aborted) {
				const stopped = [...(get().selectedSession?.messages ?? [])].reverse().find((item) => item.role === "assistant");
				if (stopped) return stopped;
			}
			const message = error instanceof Error ? error.message : "Failed to send message.";

			set((state) => {
				if (!state.selectedSession || state.selectedSession.id !== sessionId) {
					return {
						error: message,
					};
				}

				return {
					selectedSession: {
						...state.selectedSession,
						messages: started ? state.selectedSession.messages : state.selectedSession.messages.filter(
							(item) => item.id !== optimisticUserMessage.id
						),
					},
					error: message,
				};
			});

			throw new Error(message);
		} finally {
			activeControllers.delete(sessionId);
			set((state) => ({
				pendingMessageRequests: endChatRequest(
					state.pendingMessageRequests,
					sessionId
				),
			}));
		}
	},

	cancelMessage: async (sessionId) => {
		const messageId = get().streamingMessageId;
		if (!messageId) return;
		await cancelStreamingMessage(sessionId, messageId);
		set((state) => {
			if (!state.selectedSession || state.selectedSession.id !== sessionId) return { streamingMessageId: null };
			return {
				streamingMessageId: null,
				selectedSession: {
					...state.selectedSession,
					messages: state.selectedSession.messages.map((message) =>
						message.id === messageId
							? { ...message, generation_status: "cancelled" as const }
							: message
					),
				},
			};
		});
		activeControllers.get(sessionId)?.abort();
	},

	retryMessage: async (sessionId, messageId) => {
		if (isChatRequestPending(get().pendingMessageRequests, sessionId)) throw new Error("A message is already being processed for this session.");
		const controller = new AbortController();
		activeControllers.set(sessionId, controller);
		let finalMessage: ChatMessageResponse | null = null;
		set((state) => ({ pendingMessageRequests: beginChatRequest(state.pendingMessageRequests, sessionId), error: null }));
		try {
			await retryChatMessage(sessionId, messageId, {
				signal: controller.signal,
				onEvent: (event) => {
					set((state) => {
						if (!state.selectedSession || state.selectedSession.id !== sessionId) return {};
						let messages = state.selectedSession.messages;
						if (event.type === "generation_started") messages = replaceMessage(messages, event.assistant_message);
						if (event.type === "token") messages = messages.map((item) => item.id === event.message_id ? { ...item, content: item.content + event.delta } : item);
						if (event.type === "answer_reset") messages = messages.map((item) => item.id === event.message_id ? { ...item, content: "" } : item);
						if (event.type === "completed" || event.type === "cancelled") { finalMessage = event.message; messages = replaceMessage(messages, event.message); }
						return { selectedSession: { ...state.selectedSession, messages }, streamingMessageId: event.type === "generation_started" ? event.assistant_message.id : (event.type === "completed" || event.type === "cancelled" ? null : state.streamingMessageId) };
					});
				},
			});
			if (!finalMessage) throw new Error("The retried response was not persisted.");
			return finalMessage;
		} finally {
			activeControllers.delete(sessionId);
			set((state) => ({ pendingMessageRequests: endChatRequest(state.pendingMessageRequests, sessionId) }));
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
