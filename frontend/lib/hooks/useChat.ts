"use client";

import { useMemo } from "react";

import { useChatStore } from "@/store/chatStore";

export function useChat() {
	const sessions = useChatStore((state) => state.sessions);
	const total = useChatStore((state) => state.total);
	const selectedSession = useChatStore((state) => state.selectedSession);
	const isLoading = useChatStore((state) => state.isLoading);
	const isCreatingSession = useChatStore((state) => state.isCreatingSession);
	const pendingMessageRequests = useChatStore((state) => state.pendingMessageRequests);
	const isSendingMessage = selectedSession
		? pendingMessageRequests[selectedSession.id] === true
		: false;
	const isSavingAsNote = useChatStore((state) => state.isSavingAsNote);
	const streamingMessageId = useChatStore((state) => state.streamingMessageId);
	const streamedMessages = useChatStore((state) => state.streamedMessages);
	const error = useChatStore((state) => state.error);

	const fetchSessions = useChatStore((state) => state.fetchSessions);
	const fetchSessionById = useChatStore((state) => state.fetchSessionById);
	const createSession = useChatStore((state) => state.createSession);
	const sendMessage = useChatStore((state) => state.sendMessage);
	const cancelMessage = useChatStore((state) => state.cancelMessage);
	const retryMessage = useChatStore((state) => state.retryMessage);
	const saveSessionAsNote = useChatStore((state) => state.saveSessionAsNote);
	const setSelectedSession = useChatStore((state) => state.setSelectedSession);
	const clearError = useChatStore((state) => state.clearError);

	const renderedMessages = useMemo(() => {
		if (!selectedSession) {
			return [];
		}

		return selectedSession.messages.map((message) => {
			const streamedContent = streamedMessages[message.id];
			if (streamedContent === undefined) {
				return message;
			}

			return {
				...message,
				content: streamedContent,
			};
		});
	}, [selectedSession, streamedMessages]);

	return {
		sessions,
		total,
		selectedSession,
		renderedMessages,
		isLoading,
		isCreatingSession,
		isSendingMessage,
		pendingMessageRequests,
		isSavingAsNote,
		streamingMessageId,
		streamedMessages,
		error,
		fetchSessions,
		fetchSessionById,
		createSession,
		sendMessage,
		cancelMessage,
		retryMessage,
		saveSessionAsNote,
		setSelectedSession,
		clearError,
	};
}
