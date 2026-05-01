/**
 * WebSocket client for real-time chat messaging.
 *
 * Features:
 * - Automatic reconnection with exponential backoff
 * - Message queuing during disconnection
 * - Connection state management
 * - Event-based message handling
 */

export interface WebSocketMessage {
	type: "message" | "connection" | "user_left" | "error";
	content?: string;
	sender_id?: number;
	timestamp?: string;
	status?: string;
	session_id?: number;
	user_count?: number;
	user_id?: number;
}

export interface WebSocketOptions {
	reconnectAttempts?: number;
	initialReconnectDelay?: number;
	maxReconnectDelay?: number;
}

export class ChatWebSocketClient {
	private ws: WebSocket | null = null;
	private url: string;
	private sessionId: number;
	private messageQueue: WebSocketMessage[] = [];
	private isConnected = false;
	private reconnectAttempts = 0;
	private reconnectDelay = 1000;
	private reconnectTimer: NodeJS.Timeout | null = null;
	private messageHandlers: ((msg: WebSocketMessage) => void)[] = [];
	private stateHandlers: ((state: "connected" | "disconnected" | "error") => void)[] = [];

	private readonly reconnectConfig: Required<WebSocketOptions>;

	constructor(
		sessionId: number,
		options: WebSocketOptions = {}
	) {
		this.sessionId = sessionId;
		this.reconnectConfig = {
			reconnectAttempts: options.reconnectAttempts ?? 5,
			initialReconnectDelay: options.initialReconnectDelay ?? 1000,
			maxReconnectDelay: options.maxReconnectDelay ?? 30000,
		};

		// Build WebSocket URL
		const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
		this.url = `${protocol}//${window.location.host}/api/v1/chat/sessions/${sessionId}/ws`;
	}

	/**
	 * Connect to the WebSocket server.
	 */
	connect(): Promise<void> {
		return new Promise((resolve, reject) => {
			try {
				this.ws = new WebSocket(this.url);

				this.ws.onopen = () => {
					console.log(`[WebSocket] Connected to session ${this.sessionId}`);
					this.isConnected = true;
					this.reconnectAttempts = 0;
					this.reconnectDelay = this.reconnectConfig.initialReconnectDelay;

					// Flush queued messages
					this.flushMessageQueue();

					this.notifyStateChange("connected");
					resolve();
				};

				this.ws.onmessage = (event) => {
					try {
						const message: WebSocketMessage = JSON.parse(event.data);
						this.notifyMessageHandlers(message);
					} catch (error) {
						console.error("[WebSocket] Failed to parse message:", error);
					}
				};

				this.ws.onerror = (error) => {
					console.error("[WebSocket] Error:", error);
					this.notifyStateChange("error");
				};

				this.ws.onclose = () => {
					console.log(`[WebSocket] Disconnected from session ${this.sessionId}`);
					this.isConnected = false;
					this.ws = null;
					this.notifyStateChange("disconnected");

					// Attempt reconnection
					this.reconnect();
				};
			} catch (error) {
				console.error("[WebSocket] Connection failed:", error);
				reject(error);
			}
		});
	}

	/**
	 * Disconnect from the WebSocket server.
	 */
	disconnect(): void {
		if (this.reconnectTimer) {
			clearTimeout(this.reconnectTimer);
			this.reconnectTimer = null;
		}

		if (this.ws) {
			this.ws.close();
			this.ws = null;
		}

		this.isConnected = false;
	}

	/**
	 * Send a message through the WebSocket.
	 */
	send(message: WebSocketMessage): void {
		if (this.isConnected && this.ws) {
			this.ws.send(JSON.stringify(message));
		} else {
			// Queue message if disconnected
			this.messageQueue.push(message);
			console.warn("[WebSocket] Not connected. Message queued.");
		}
	}

	/**
	 * Register a handler for incoming messages.
	 */
	onMessage(handler: (msg: WebSocketMessage) => void): () => void {
		this.messageHandlers.push(handler);

		// Return unsubscribe function
		return () => {
			this.messageHandlers = this.messageHandlers.filter((h) => h !== handler);
		};
	}

	/**
	 * Register a handler for connection state changes.
	 */
	onStateChange(
		handler: (state: "connected" | "disconnected" | "error" | "connecting") => void
	): () => void {
		this.stateHandlers.push(handler);

		// Return unsubscribe function
		return () => {
			this.stateHandlers = this.stateHandlers.filter((h) => h !== handler);
		};
	}

	/**
	 * Get current connection state.
	 */
	getState(): "connected" | "disconnected" | "connecting" | "error" {
		if (this.isConnected) return "connected";
		if (this.reconnectTimer) return "connecting";
		return "disconnected";
	}

	/**
	 * Private: Attempt to reconnect with exponential backoff.
	 */
	private reconnect(): void {
		if (this.reconnectAttempts >= this.reconnectConfig.reconnectAttempts) {
			console.error(
				`[WebSocket] Max reconnection attempts reached (${this.reconnectConfig.reconnectAttempts})`
			);
			return;
		}

		// Calculate backoff delay
		const delay = Math.min(
			this.reconnectDelay * Math.pow(2, this.reconnectAttempts),
			this.reconnectConfig.maxReconnectDelay
		);

		this.reconnectAttempts++;
		console.log(
			`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`
		);

		this.reconnectTimer = setTimeout(() => {
			this.connect().catch((error) => {
				console.error("[WebSocket] Reconnection failed:", error);
			});
		}, delay);
	}

	/**
	 * Private: Flush all queued messages.
	 */
	private flushMessageQueue(): void {
		while (this.messageQueue.length > 0 && this.isConnected && this.ws) {
			const message = this.messageQueue.shift();
			if (message) {
				this.ws.send(JSON.stringify(message));
			}
		}
	}

	/**
	 * Private: Notify all message handlers.
	 */
	private notifyMessageHandlers(message: WebSocketMessage): void {
		this.messageHandlers.forEach((handler) => {
			try {
				handler(message);
			} catch (error) {
				console.error("[WebSocket] Handler error:", error);
			}
		});
	}

	/**
	 * Private: Notify all state change handlers.
	 */
	private notifyStateChange(state: "connected" | "disconnected" | "error"): void {
		this.stateHandlers.forEach((handler) => {
			try {
				handler(state);
			} catch (error) {
				console.error("[WebSocket] State handler error:", error);
			}
		});
	}
}

/**
 * Create and manage WebSocket connections.
 */
export function createWebSocketClient(
	sessionId: number,
	options?: WebSocketOptions
): ChatWebSocketClient {
	return new ChatWebSocketClient(sessionId, options);
}
