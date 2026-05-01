"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
	ChatWebSocketClient,
	WebSocketMessage,
	createWebSocketClient,
} from "@/lib/api/websocket";

export interface UseWebSocketState {
	state: "connected" | "disconnected" | "connecting" | "error";
	messages: WebSocketMessage[];
	error: string | null;
	isConnected: boolean;
}

/**
 * React hook for WebSocket connection management.
 *
 * Features:
 * - Automatic connection/disconnection
 * - Message accumulation and history
 * - State management
 * - Error handling
 */
export function useWebSocket(sessionId: number) {
	const clientRef = useRef<ChatWebSocketClient | null>(null);
	const [state, setState] = useState<UseWebSocketState>({
		state: "disconnected",
		messages: [],
		error: null,
		isConnected: false,
	});

	/**
	 * Initialize WebSocket connection.
	 */
	useEffect(() => {
		const client = createWebSocketClient(sessionId, {
			reconnectAttempts: 5,
			initialReconnectDelay: 1000,
			maxReconnectDelay: 30000,
		});

		clientRef.current = client;

		// Handle incoming messages
		const unsubscribeMessage = client.onMessage((message) => {
			setState((prev) => ({
				...prev,
				messages: [...prev.messages, message],
			}));
		});

		// Handle state changes
		const unsubscribeState = client.onStateChange((newState) => {
			setState((prev) => ({
				...prev,
				state: newState,
				isConnected: newState === "connected",
				error: newState === "error" ? "Connection error" : null,
			}));
		});

		// Connect to server
		client.connect().catch((error) => {
			console.error("[useWebSocket] Connection failed:", error);
			setState((prev) => ({
				...prev,
				error: error instanceof Error ? error.message : "Connection failed",
			}));
		});

		// Cleanup on unmount
		return () => {
			unsubscribeMessage();
			unsubscribeState();
			client.disconnect();
		};
	}, [sessionId]);

	/**
	 * Send a message through WebSocket.
	 */
	const sendMessage = useCallback(
		(content: string): void => {
			if (!clientRef.current) {
				console.error("[useWebSocket] Client not initialized");
				return;
			}

			clientRef.current.send({
				type: "message",
				content,
			});
		},
		[]
	);

	/**
	 * Clear message history.
	 */
	const clearMessages = useCallback((): void => {
		setState((prev) => ({
			...prev,
			messages: [],
		}));
	}, []);

	/**
	 * Manually reconnect.
	 */
	const reconnect = useCallback((): void => {
		if (!clientRef.current) return;

		clientRef.current.disconnect();
		setTimeout(() => {
			clientRef.current?.connect().catch((error) => {
				console.error("[useWebSocket] Reconnection failed:", error);
			});
		}, 1000);
	}, []);

	return {
		...state,
		sendMessage,
		clearMessages,
		reconnect,
	};
}
