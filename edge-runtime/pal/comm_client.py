"""
PAL — Communication Client
===========================
Async MQTT wrapper that provides a stable publish/subscribe interface
to the rest of the runtime, with automatic reconnection on broker
failures.

All MQTT topic conventions live here so the rest of the codebase never
constructs raw topic strings.

Topics
------
Subscribe:
    device/{device_id}/commands

Publish:
    device/{device_id}/events
    device/{device_id}/telemetry
    device/{device_id}/inference
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiomqtt

# Set up logging for this module
logger = logging.getLogger(__name__)

# Type alias for command handler callbacks.
# Receives the parsed JSON payload dict; may be async or sync.
CommandHandler = Callable[[dict], Awaitable[None] | None]


class CommunicationClient:
    """
    Async MQTT client with automatic reconnection and local SQLite buffering.

    This client manages communication with the MQTT broker, handles connection loss
    by queuing messages locally using SQLite, and automatically flushes buffered
    messages once the connection is re-established.

    :ivar _device_id: Unique device identifier.
    :type _device_id: str
    :ivar _host: Hostname of the MQTT broker.
    :type _host: str
    :ivar _port: Port of the MQTT broker.
    :type _port: int
    :ivar _reconnect_interval: Wait time in seconds before attempting reconnection.
    :type _reconnect_interval: int
    :ivar _client: Underlying aiomqtt Client instance.
    :type _client: aiomqtt.Client or None
    :ivar _command_handlers: Map of command names to registered callbacks.
    :type _command_handlers: dict[str, CommandHandler]
    :ivar _db_path: Path to the SQLite buffer database file.
    :type _db_path: Path
    """

    def __init__(
        self,
        device_id: str,
        host: str,
        port: int = 1883,
        reconnect_interval_s: int = 5,
        db_path: Path | None = None,
    ) -> None:
        """
        Initializes the CommunicationClient with connection parameters and SQLite path.

        :param device_id: Unique device identifier.
        :type device_id: str
        :param host: MQTT broker hostname.
        :type host: str
        :param port: MQTT broker port (default 1883).
        :type port: int
        :param reconnect_interval_s: Reconnection interval in seconds on connection failure.
        :type reconnect_interval_s: int
        :param db_path: Optional custom path for the SQLite database buffer.
        :type db_path: Path or None
        """
        self._device_id = device_id
        self._host = host
        self._port = port
        self._reconnect_interval = reconnect_interval_s
        self._client = None
        self._command_handlers = {}
        
        # If no custom DB path is provided, use the default path under /tmp/aura
        if db_path is None:
            self._db_path = Path("/tmp/aura") / f"mqtt_buffer_{device_id}.db"
        else:
            self._db_path = db_path
            
        # Initialize the SQLite local buffer database
        self._init_db()

    # ── Topic helpers ─────────────────────────────────────────────────────────

    @property
    def topic_commands(self) -> str:
        """
        Gets the command subscription topic for this device.

        :return: Topic string.
        :rtype: str
        """
        return f"device/{self._device_id}/commands"

    @property
    def topic_events(self) -> str:
        """
        Gets the events publishing topic for this device.

        :return: Topic string.
        :rtype: str
        """
        return f"device/{self._device_id}/events"

    @property
    def topic_telemetry(self) -> str:
        """
        Gets the telemetry publishing topic for this device.

        :return: Topic string.
        :rtype: str
        """
        return f"device/{self._device_id}/telemetry"

    @property
    def topic_inference(self) -> str:
        """
        Gets the inference publishing topic for this device.

        :return: Topic string.
        :rtype: str
        """
        return f"device/{self._device_id}/inference"

    # ── Public API ────────────────────────────────────────────────────────────

    def register_command_handler(self, command: str, handler: CommandHandler) -> None:
        """
        Registers a callback handler for a specific command name.

        :param command: Command name field in the MQTT payload to match.
        :type command: str
        :param handler: Callback executing when the command is received.
        :type handler: CommandHandler
        """
        self._command_handlers[command] = handler
        logger.debug(f"Registered handler for command '{command}'")

    async def publish_event(self, event: str, **extra: Any) -> None:
        """
        Publishes a status or notification event to the device events topic.

        :param event: Name of the event.
        :type event: str
        :param extra: Key-value parameters to include in the payload.
        :type extra: Any
        """
        await self._publish(self.topic_events, {"event": event, **extra})

    async def publish_telemetry(self, payload: dict) -> None:
        """
        Publishes system and device telemetry payload to the telemetry topic.

        :param payload: Telemetry metrics and state dictionary.
        :type payload: dict
        """
        await self._publish(self.topic_telemetry, payload)

    async def publish_inference(self, payload: dict) -> None:
        """
        Publishes machine learning inference results payload to the inference topic.

        :param payload: Inference details and model output dictionary.
        :type payload: dict
        """
        await self._publish(self.topic_inference, payload)

    async def run(self) -> None:
        """
        Connects to the MQTT broker and starts the async message processing loop.

        This runs continuously. On disconnect or errors, it backs off and tries
        to reconnect automatically. It should be spawned as an asyncio task.
        """
        import json
        while True:
            try:
                # Set up Last Will and Testament to announce offline status if connection drops abruptly
                will = aiomqtt.Will(
                    topic=f"device/{self._device_id}/status",
                    payload=json.dumps({"status": "offline"}),
                    qos=1,
                    retain=True
                )
                
                # Connect to broker using Client context manager
                async with aiomqtt.Client(
                    hostname=self._host, port=self._port, will=will
                ) as client:
                    self._client = client
                    # Subscribe to the command topic
                    await client.subscribe(self.topic_commands)
                    
                    # Announce online status immediately
                    await client.publish(
                        f"device/{self._device_id}/status",
                        json.dumps({"status": "online"}),
                        retain=True
                    )
                    
                    logger.info(
                        f"MQTT connected — subscribed to {self.topic_commands}"
                    )
                    
                    # Start background task to flush any queued messages in the SQLite DB
                    asyncio.create_task(self._flush_buffer())
                    
                    # Process incoming messages as they arrive
                    async for msg in client.messages:
                        await self._dispatch(msg)
                        
            except aiomqtt.MqttError as exc:
                self._client = None
                logger.warning(
                    f"MQTT error: {exc} — reconnecting in {self._reconnect_interval}s"
                )
                # Wait reconnect interval before trying again
                await asyncio.sleep(self._reconnect_interval)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _publish(self, topic: str, payload: dict) -> None:
        """
        Publishes the given payload to a topic. If offline, queues it locally.

        :param topic: Target MQTT topic.
        :type topic: str
        :param payload: Dictionary data to publish as JSON.
        :type payload: dict
        """
        # If client is not connected, buffer the message immediately
        if self._client is None:
            logger.warning(f"MQTT offline: buffering message for topic '{topic}' to SQLite.")
            await asyncio.to_thread(self._buffer_message, topic, payload)
            return
        try:
            # Publish payload converted to JSON string
            await self._client.publish(topic, json.dumps(payload))
        except Exception as exc:  # noqa: BLE001
            # Fallback to local buffer if publishing throws an exception
            logger.warning(f"Publish failed on {topic} ({exc}). Buffering message.")
            await asyncio.to_thread(self._buffer_message, topic, payload)

    def _init_db(self) -> None:
        """
        Creates the SQLite buffer table on disk if it does not exist.
        """
        import sqlite3
        try:
            # Create directories up to database path if missing
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            # Connect to database and execute schema definition
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS mqtt_buffer (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            logger.info(f"Local SQLite buffer database initialized at: {self._db_path}")
        except Exception as exc:
            logger.error(f"Failed to initialize SQLite buffer: {exc}")

    def _buffer_message(self, topic: str, payload: dict) -> None:
        """
        Inserts a message to the SQLite local table.

        :param topic: MQTT topic string.
        :type topic: str
        :param payload: Dictionary payload.
        :type payload: dict
        """
        import sqlite3
        try:
            # Connect and insert row
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO mqtt_buffer (topic, payload) VALUES (?, ?)",
                    (topic, json.dumps(payload))
                )
            logger.debug(f"Message buffered successfully in SQLite: {topic}")
        except Exception as exc:
            logger.error(f"Failed to buffer message to SQLite: {exc}")

    def _get_next_buffered_message(self) -> tuple[int, str, str] | None:
        """
        Retrieves the oldest queued message in the SQLite database.

        :return: Tuple containing (id, topic, payload) or None if buffer is empty.
        :rtype: tuple[int, str, str] or None
        """
        import sqlite3
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                # Query the oldest message using ID ordering
                cursor.execute("SELECT id, topic, payload FROM mqtt_buffer ORDER BY id ASC LIMIT 1")
                return cursor.fetchone()
        except Exception as exc:
            logger.error(f"Error reading from SQLite buffer: {exc}")
            return None

    def _delete_buffered_message(self, msg_id: int) -> None:
        """
        Deletes a queued message from SQLite buffer by its ID.

        :param msg_id: Database ID of the message to delete.
        :type msg_id: int
        """
        import sqlite3
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM mqtt_buffer WHERE id = ?", (msg_id,))
        except Exception as exc:
            logger.error(f"Error deleting from SQLite buffer: {exc}")

    async def _flush_buffer(self) -> None:
        """
        Flushes all buffered messages to the MQTT broker sequentially.

        Runs in the background once connected, processing rows until empty
        or connection drops again.
        """
        logger.info("Checking SQLite buffer for offline-queued messages...")
        
        while True:
            # Abort if connection was lost during flush
            if self._client is None:
                logger.info("Flush paused: MQTT disconnected.")
                break
                
            # Fetch oldest buffered row
            msg = await asyncio.to_thread(self._get_next_buffered_message)
            if msg is None:
                logger.info("SQLite buffer is empty. Flush completed.")
                break
                
            msg_id, topic, payload_str = msg
            try:
                # Attempt to publish the raw payload string
                await self._client.publish(topic, payload_str)
                # Delete the message on success
                await asyncio.to_thread(self._delete_buffered_message, msg_id)
                logger.info(f"Successfully flushed buffered message {msg_id} to {topic}")
                # Brief yield to avoid flooding the broker / CPU
                await asyncio.sleep(0.05)
            except Exception as exc:
                logger.warning(f"Failed to flush buffered message {msg_id}: {exc}. Retrying later.")
                break

    async def _dispatch(self, msg: aiomqtt.Message) -> None:
        """
        Parses and dispatches an incoming MQTT message to its registered handler.

        :param msg: Received MQTT message structure.
        :type msg: aiomqtt.Message
        """
        try:
            # Parse payload as JSON
            payload = json.loads(msg.payload)
            command = payload.get("command")
            if command is None:
                logger.warning(f"Message without 'command' field: {payload}")
                return
            # Lookup command callback handler
            handler = self._command_handlers.get(command)
            if handler is None:
                logger.warning(f"No handler registered for command '{command}'")
                return
            logger.debug(f"Dispatching command '{command}'")
            # Invoke the callback handler
            result = handler(payload)
            # If the handler is a coroutine, schedule it as an async task
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
        except json.JSONDecodeError as exc:
            logger.error(f"Invalid JSON in MQTT message: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Command dispatch error: {exc}")

