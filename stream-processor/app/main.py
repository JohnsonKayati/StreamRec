"""
stream-processor/app/main.py

Entry point: wires together the consumer, processor, and feature store,
then runs the poll loop until a shutdown signal is received.

AWS equivalent:
  ECS Fargate task subscribed to a Kinesis stream, or a Lambda triggered
  by Kinesis with Enhanced Fan-Out for sub-second latency delivery.
  Consumer group ID maps to the Kinesis shard iterator checkpoint.
"""

import signal
import time

from app.config import get_settings
from app.consumer import KafkaEventConsumer
from app.feature_store import UserFeatureStore
from app.processor import EventProcessor
from shared.logging_config import configure_logging, get_logger

_NO_MESSAGE_SLEEP_S = 0.01  # avoid tight spin when the topic is quiet

# Configure logging before any other imports so startup messages are structured.
_settings = get_settings()
configure_logging(_settings.service_name, _settings.log_level)
logger = get_logger(__name__)

_running = True


def _handle_shutdown(sig: int, _frame: object) -> None:
    """SIGTERM / SIGINT handler — sets the stop flag for the poll loop."""
    global _running
    logger.info("shutdown_signal_received signal=%d", sig)
    _running = False


def run() -> None:
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    feature_store = UserFeatureStore(
        redis_url=_settings.redis_url,
        database_url=_settings.database_url,
    )
    processor = EventProcessor(feature_store=feature_store)
    consumer = KafkaEventConsumer(
        bootstrap_servers=_settings.kafka_bootstrap_servers,
        group_id=_settings.kafka_consumer_group,
        topic=_settings.kafka_topic_user_events,
        auto_offset_reset=_settings.kafka_auto_offset_reset,
        poll_timeout_s=_settings.kafka_poll_timeout_s,
    )

    logger.info(
        "stream_processor_started topic=%s group=%s commit_interval=%d",
        _settings.kafka_topic_user_events,
        _settings.kafka_consumer_group,
        _settings.kafka_commit_interval,
    )

    total_processed = 0
    since_last_commit = 0
    batch_start = time.monotonic()

    try:
        while _running:
            envelope, had_message = consumer.poll()

            if not had_message:
                # Timeout or partition EOF — nothing to do.
                time.sleep(_NO_MESSAGE_SLEEP_S)
                continue

            # A real Kafka message was received (good or bad).
            # Always advance the commit counter so a run of malformed
            # messages cannot stall offset commits indefinitely.
            since_last_commit += 1

            if envelope is not None:
                try:
                    processor.process(envelope.event)
                    total_processed += 1
                except Exception as exc:
                    # Log and continue — one bad event must not stall the consumer.
                    logger.error(
                        "event_processing_failed user_id=%s event_type=%s error=%s",
                        envelope.event.user_id,
                        envelope.event.event_type.value,
                        exc,
                    )

            # Commit offsets after every kafka_commit_interval messages.
            if since_last_commit >= _settings.kafka_commit_interval:
                consumer.commit()
                elapsed = time.monotonic() - batch_start
                rate = since_last_commit / elapsed if elapsed > 0 else 0.0
                logger.info(
                    "checkpoint total_processed=%d rate_per_sec=%.1f",
                    total_processed, rate,
                )
                since_last_commit = 0
                batch_start = time.monotonic()

    finally:
        consumer.close()
        feature_store.close()
        logger.info("stream_processor_stopped total_processed=%d", total_processed)


if __name__ == "__main__":
    run()
