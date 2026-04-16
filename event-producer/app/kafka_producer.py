"""
event-producer/app/kafka_producer.py

Thin wrapper around confluent-kafka's synchronous Producer.

AWS equivalent: Amazon Kinesis Data Streams PutRecord / PutRecords.

Design notes:
- confluent-kafka (C extension) is used instead of kafka-python for lower
  per-message latency and better throughput under load.
- Messages are serialized to JSON. Avro/Protobuf is the production upgrade
  path (schema registry + smaller payloads), but JSON keeps this debuggable.
- Delivery is best-effort at the producer level. Kafka's replication factor
  and acks setting control durability guarantees.
- publish() is non-blocking — it enqueues the message and returns immediately.
  poll(0) drains the internal callback queue without blocking the HTTP response.
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from confluent_kafka import KafkaError, KafkaException, Producer

logger = logging.getLogger(__name__)


class _JSONEncoder(json.JSONEncoder):
    """Handle types that appear in Pydantic model dumps but aren't JSON-native."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def _delivery_callback(err: Any, msg: Any) -> None:
    """
    Called by librdkafka on message delivery confirmation or failure.
    Runs in the producer's polling thread — keep it fast and non-blocking.
    """
    if err:
        logger.error(
            "kafka_delivery_failed topic=%s error=%s",
            msg.topic(),
            err,
        )
    else:
        logger.debug(
            "kafka_delivery_ok topic=%s partition=%d offset=%d",
            msg.topic(),
            msg.partition(),
            msg.offset(),
        )


class KafkaEventProducer:
    """
    Produces serialized events to a Kafka topic.

    Thread-safe: confluent-kafka's Producer is safe for concurrent produce()
    calls from multiple threads, which matters when FastAPI runs with workers > 1.

    Usage:
        producer = KafkaEventProducer(bootstrap_servers="localhost:9092")
        producer.publish(topic="user-events", key="user_0042", value={...})
        producer.flush()   # call on shutdown to drain the queue
    """

    def __init__(
        self,
        bootstrap_servers: str,
        acks: str = "1",
        retries: int = 3,
        linger_ms: int = 5,
    ) -> None:
        conf: dict[str, Any] = {
            "bootstrap.servers": bootstrap_servers,
            "acks": acks,
            "retries": retries,
            "linger.ms": linger_ms,
            # Idempotence requires acks=all and retries > 0
            "enable.idempotence": acks == "all",
        }
        self._producer = Producer(conf)
        logger.info("kafka_producer_initialized bootstrap_servers=%s", bootstrap_servers)

    def publish(self, topic: str, key: str, value: dict[str, Any]) -> None:
        """
        Serialize value to JSON bytes and enqueue for delivery.

        The partition key is user_id — this keeps all events for a given user
        in the same partition and preserves causal ordering for the stream
        processor. Important for session-aware feature computation.

        Args:
            topic: Target Kafka topic.
            key:   Partition key string (use user_id).
            value: Payload dict. Must be JSON-serializable via _JSONEncoder.

        Raises:
            KafkaException: If the internal produce queue is full (back-pressure).
        """
        payload = json.dumps(value, cls=_JSONEncoder).encode("utf-8")
        try:
            self._producer.produce(
                topic=topic,
                key=key.encode("utf-8"),
                value=payload,
                callback=_delivery_callback,
            )
            # Trigger delivery callbacks without blocking.
            # Without this, callbacks only fire on the next produce() or flush().
            self._producer.poll(0)
        except KafkaException as exc:
            # Queue full: poll for up to 1 second to drain in-flight deliveries,
            # then retry once. If it fails again, propagate to the caller.
            if exc.args[0].code() == KafkaError._QUEUE_FULL:
                logger.warning("kafka_queue_full topic=%s — polling and retrying", topic)
                self._producer.poll(1)
                try:
                    self._producer.produce(
                        topic=topic,
                        key=key.encode("utf-8"),
                        value=payload,
                        callback=_delivery_callback,
                    )
                    self._producer.poll(0)
                except KafkaException as retry_exc:
                    logger.error("kafka_produce_failed_after_retry topic=%s error=%s", topic, retry_exc)
                    raise
            else:
                logger.error("kafka_produce_failed topic=%s error=%s", topic, exc)
                raise

    def flush(self, timeout: float = 5.0) -> None:
        """
        Block until all enqueued messages are delivered or timeout expires.
        Call this on service shutdown to avoid losing in-flight messages.
        """
        remaining = self._producer.flush(timeout=timeout)
        if remaining > 0:
            logger.warning(
                "kafka_flush_incomplete remaining_messages=%d", remaining
            )

    def close(self) -> None:
        """Flush and release resources. Call once during service shutdown."""
        self.flush()
        logger.info("kafka_producer_closed")
