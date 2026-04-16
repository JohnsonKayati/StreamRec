"""
stream-processor/app/consumer.py

Kafka consumer wrapper.

Responsibility: polling, deserialization, and offset management only.
No feature logic or storage writes belong here.

Design:
- poll() returns a (envelope, had_message) tuple so callers can distinguish
  three states: good message, bad message, and no message. This matters for
  offset commit tracking — bad messages must still advance the commit counter,
  otherwise a stream of malformed messages will never commit.
- Manual offset commits (enable.auto.commit=False) give at-least-once
  delivery semantics. Reprocessing at most kafka_commit_interval messages
  on restart is acceptable for a recommender system.
- _PARTITION_EOF is not an error — it means this partition is caught up.
  Treat it the same as a timeout: no message, no commit counter advance.
"""

import json
import logging

from confluent_kafka import Consumer, KafkaError, KafkaException, Message

from shared.schemas import EventEnvelope

logger = logging.getLogger(__name__)


class KafkaEventConsumer:
    """
    Thin wrapper around confluent_kafka.Consumer.

    poll() return value semantics:
        (envelope, True)   — message received and parsed successfully
        (None,     True)   — message received but failed to parse/validate
        (None,     False)  — no message (poll timeout or partition EOF)

    Usage:
        consumer = KafkaEventConsumer(...)
        while running:
            envelope, had_message = consumer.poll()
            if envelope:
                process(envelope.event)
            elif had_message:
                # bad message — still advance commit tracking
        consumer.close()
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topic: str,
        auto_offset_reset: str = "earliest",
        poll_timeout_s: float = 1.0,
    ) -> None:
        self._topic = topic
        self._poll_timeout = poll_timeout_s
        self._consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": auto_offset_reset,
            "enable.auto.commit": False,
            # Max time between poll() calls before the broker considers
            # this consumer dead and triggers a rebalance.
            "max.poll.interval.ms": 300_000,
        })
        self._consumer.subscribe([topic])
        logger.info(
            "kafka_consumer_subscribed topic=%s group=%s", topic, group_id
        )

    def poll(self) -> tuple[EventEnvelope | None, bool]:
        """
        Poll for one message.

        Returns:
            (envelope, True)  — message received and parsed. Process envelope.event.
            (None,     True)  — message received but skipped (bad payload).
                                Caller must still advance offset commit tracking.
            (None,     False) — no message (timeout or EOF). Safe to sleep/continue.

        Raises:
            KafkaException: for unrecoverable broker-level errors.
        """
        msg: Message | None = self._consumer.poll(timeout=self._poll_timeout)

        if msg is None:
            return None, False

        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                logger.debug(
                    "partition_eof partition=%d offset=%d",
                    msg.partition(), msg.offset(),
                )
                return None, False
            raise KafkaException(msg.error())

        # A real message was received — attempt to deserialise.
        try:
            raw = json.loads(msg.value().decode("utf-8"))
            envelope = EventEnvelope.model_validate(raw)
            logger.debug(
                "message_received partition=%d offset=%d user_id=%s event_type=%s",
                msg.partition(), msg.offset(),
                envelope.event.user_id, envelope.event.event_type.value,
            )
            return envelope, True
        except Exception as exc:
            # Log with enough context to find the bad message in the broker.
            logger.error(
                "message_skipped_bad_payload partition=%d offset=%d error=%s",
                msg.partition(), msg.offset(), exc,
            )
            # Return had_message=True so the caller advances commit tracking.
            # Without this, a run of bad messages would stall offset commits.
            return None, True

    def commit(self) -> None:
        """Synchronously commit current offsets to the broker."""
        self._consumer.commit(asynchronous=False)
        logger.debug("offsets_committed")

    def close(self) -> None:
        """Commit pending offsets and close the consumer cleanly."""
        try:
            self._consumer.commit(asynchronous=False)
        except Exception as exc:
            logger.warning("final_commit_failed error=%s", exc)
        self._consumer.close()
        logger.info("kafka_consumer_closed")
