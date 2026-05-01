"""
WebSocket connection management for real-time chat messaging.

Handles:
- Active connection tracking
- Message broadcasting
- Connection lifecycle (connect/disconnect)
- Connection state and metadata
"""

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for chat sessions.

    Tracks active connections per session and user, enabling:
    - Targeted message delivery
    - Connection state management
    - Multi-user session support
    """

    def __init__(self) -> None:
        # Map of session_id -> dict of (user_id -> WebSocket)
        self.active_connections: dict[int, dict[int, WebSocket]] = {}
        # Map of session_id -> metadata
        self.session_metadata: dict[int, dict[str, Any]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        session_id: int,
        user_id: int,
    ) -> None:
        """
        Register a new WebSocket connection for a chat session.

        Args:
            websocket: The WebSocket connection
            session_id: The chat session ID
            user_id: The user ID
        """
        await websocket.accept()

        if session_id not in self.active_connections:
            self.active_connections[session_id] = {}
            self.session_metadata[session_id] = {"created_at": None}

        self.active_connections[session_id][user_id] = websocket

        logger.info(
            f"WebSocket connected: session={session_id}, user={user_id}, "
            f"total_users={len(self.active_connections[session_id])}"
        )

    def disconnect(self, session_id: int, user_id: int) -> None:
        """
        Remove a WebSocket connection.

        Args:
            session_id: The chat session ID
            user_id: The user ID
        """
        if session_id in self.active_connections and user_id in self.active_connections[session_id]:
            del self.active_connections[session_id][user_id]

            # Clean up empty sessions
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                if session_id in self.session_metadata:
                    del self.session_metadata[session_id]

                logger.info(f"WebSocket session cleaned up: session={session_id}")
            else:
                logger.info(
                    f"WebSocket disconnected: session={session_id}, user={user_id}, "
                    f"remaining_users={len(self.active_connections[session_id])}"
                )

    async def broadcast_to_session(
        self,
        session_id: int,
        message: dict[str, Any],
        exclude_user: int | None = None,
    ) -> None:
        """
        Broadcast a message to all users in a session.

        Args:
            session_id: The chat session ID
            message: The message to broadcast
            exclude_user: Optional user ID to exclude from broadcast
        """
        if session_id not in self.active_connections:
            logger.warning(f"No active connections for session {session_id}")
            return

        disconnected_users = []
        message_str = json.dumps(message)

        for user_id, connection in self.active_connections[session_id].items():
            if exclude_user and user_id == exclude_user:
                continue

            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"Failed to send message to session {session_id}, user {user_id}: {e}")
                disconnected_users.append(user_id)

        # Clean up disconnected users
        for user_id in disconnected_users:
            self.disconnect(session_id, user_id)

    async def send_to_user(
        self,
        session_id: int,
        user_id: int,
        message: dict[str, Any],
    ) -> bool:
        """
        Send a message to a specific user in a session.

        Args:
            session_id: The chat session ID
            user_id: The target user ID
            message: The message to send

        Returns:
            True if sent successfully, False otherwise
        """
        if (
            session_id not in self.active_connections
            or user_id not in self.active_connections[session_id]
        ):
            logger.warning(f"User {user_id} not connected to session {session_id}")
            return False

        try:
            connection = self.active_connections[session_id][user_id]
            await connection.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Failed to send message to session {session_id}, user {user_id}: {e}")
            self.disconnect(session_id, user_id)
            return False

    def get_session_user_count(self, session_id: int) -> int:
        """
        Get the number of active connections in a session.

        Args:
            session_id: The chat session ID

        Returns:
            Number of connected users
        """
        if session_id not in self.active_connections:
            return 0
        return len(self.active_connections[session_id])

    def has_active_connections(self, session_id: int) -> bool:
        """
        Check if a session has any active connections.

        Args:
            session_id: The chat session ID

        Returns:
            True if session has active connections
        """
        return session_id in self.active_connections and bool(self.active_connections[session_id])


# Global connection manager instance
manager = ConnectionManager()
