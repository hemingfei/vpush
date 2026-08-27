"""MX Socket.IO WebSocket client."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Callable

from .crypto import decrypt_ws_data

logger = logging.getLogger(__name__)


class MxWsClient:
    """MX Socket.IO WebSocket client."""

    def __init__(self, config: Any, on_message_callback: Callable[[dict], None]):
        """
        Initialize MX WebSocket client.
        
        Args:
            config: MX configuration object
            on_message_callback: Callback function when a new message is received
        """
        self.config = config
        self.on_message = on_message_callback
        self.connected = False
        self.last_message_at: datetime | None = None
        self._sio: Any = None
        self._task: Any = None
        self._should_stop = False

    async def connect(self):
        """Connect to MX WebSocket server."""
        try:
            import socketio

            self._sio = socketio.AsyncClient()

            @self._sio.event
            async def connect():
                logger.info("MX WebSocket connected")
                self.connected = True

            @self._sio.event
            async def disconnect():
                logger.info("MX WebSocket disconnected")
                self.connected = False

            @self._sio.event
            async def connect_error(data):
                logger.error(f"MX WebSocket connection error: {data}")

            @self._sio.on('room_msg')
            async def on_room_msg(data):
                await self._handle_message(data)

            auth = {
                "tt": int(time.time() * 1000),
                "token": self.config.token,
                "version": "web"
            }

            await self._sio.connect(
                self.config.ws_url,
                socketio_path=self.config.ws_path,
                transports=["websocket"],
                auth=auth
            )

        except Exception as e:
            logger.error(f"Failed to connect to MX WebSocket: {e}")
            raise

    async def disconnect(self):
        """Disconnect from MX WebSocket server."""
        if self._sio and self.connected:
            await self._sio.disconnect()
        self.connected = False

    async def _handle_message(self, data):
        """
        Handle incoming WebSocket message.
        
        Args:
            data: Message data (could be encrypted or plain JSON)
        """
        try:
            self.last_message_at = datetime.now()
            logger.debug(f"Received MX WebSocket message: {data}")

            message = self._parse_message(data)
            if message:
                self.on_message(message)
        except Exception as e:
            logger.error(f"Failed to handle MX WebSocket message: {e}")

    def _parse_message(self, data) -> dict | None:
        """
        Parse incoming WebSocket message.
        
        Handles various message formats:
        - Plain JSON object (case A)
        - Encrypted string (case B)
        - Wrapped object with content field (case C)
        
        Args:
            data: Raw message data
            
        Returns:
            Parsed message object or None if parsing failed
        """
        if isinstance(data, dict):
            if "content" in data:
                # Case C: Wrapped object
                encrypted = data["content"]
                decrypted = decrypt_ws_data(encrypted)
                if decrypted and isinstance(decrypted, dict):
                    return decrypted
                return None
            else:
                # Case A: Direct JSON
                return data

        if isinstance(data, str):
            # Case B: Encrypted string
            decrypted = decrypt_ws_data(data)
            if decrypted and isinstance(decrypted, dict):
                return decrypted
            # Try to parse as plain JSON string
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse MX message as JSON: {data}")
                return None

        logger.warning(f"Unexpected MX message type: {type(data)}")
        return None

    async def run_forever(self):
        """
        Run the WebSocket client forever, with automatic reconnection.
        """
        self._should_stop = False

        while not self._should_stop:
            try:
                if not self.connected:
                    await self.connect()

                # Sleep and let the Socket.IO client handle events
                await self._sio.wait()
            except Exception as e:
                logger.error(f"MX WebSocket error: {e}, reconnecting in 5 seconds...")
                self.connected = False

                if not self._should_stop:
                    time.sleep(5)

    async def stop(self):
        """Stop the WebSocket client."""
        self._should_stop = True
        await self.disconnect()
