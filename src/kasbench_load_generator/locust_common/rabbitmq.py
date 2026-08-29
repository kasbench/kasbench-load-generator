import logging
import threading

import pika
import pika.exceptions

import config

PORTFOLIO_QUEUE_NAME = 'portfolio_queue'
FUNDED_PORTFOLIO_QUEUE_NAME = 'funded_portfolio_queue'
MODEL_QUEUE_NAME = 'model_queue'
REBALANCE_QUEUE_NAME = 'rebalance_queue'
EXECUTION_QUEUE_NAME = 'execution_queue'
TRANSACTION_QUEUE_NAME = 'transaction_queue'
ORDER_QUEUE_NAME = 'order_queue'

CASH_QUEUE_NAME = 'cash_queue'
PORTFOLIO_GROUP_QUEUE_NAME = 'portfolio_group_queue'
ORDER_GROUP_QUEUE_NAME = 'order_group_queue'
CASH_GROUP_QUEUE_NAME = 'cash_group_queue'
MODEL_GROUP_QUEUE_NAME = 'model_group_queue'

# Mute pika's verbose INFO logs, only show WARNING or ERROR if something actually breaks
logging.getLogger("pika").setLevel(logging.WARNING)

# Number of times to retry an operation if the cached connection has gone stale.
_MAX_RETRIES = 2

# Under Locust/gevent every simulated user runs in its own greenlet. A pika
# BlockingConnection is not safe to share across greenlets, so we keep one
# connection (and its set of already-declared queues) per greenlet/thread and
# reuse it across calls instead of opening a fresh TCP + AMQP handshake for
# every publish/get. Opening a connection per operation is what exhausts
# RabbitMQ's connection/file-descriptor limits under load and surfaces as
# "Connection reset by peer" / ProbableAccessDeniedError.
_local = threading.local()


def _connection_parameters() -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        # Keep the connection alive while idle between tasks.
        heartbeat=60,
        blocked_connection_timeout=30,
        # Don't hang forever if the broker is momentarily saturated.
        socket_timeout=10,
        # Enable TCP keepalive so dead peers are detected.
        tcp_options={"TCP_KEEPIDLE": 60, "TCP_KEEPINTVL": 10, "TCP_KEEPCNT": 5},
    )


def _get_channel():
    """Return a live channel for the current greenlet, opening one if needed."""
    connection = getattr(_local, "connection", None)
    channel = getattr(_local, "channel", None)

    if connection is not None and connection.is_open and channel is not None and channel.is_open:
        return channel

    # Existing connection is unusable; drop it and open a fresh one.
    _close_local(quiet=True)

    connection = pika.BlockingConnection(_connection_parameters())
    channel = connection.channel()
    _local.connection = connection
    _local.channel = channel
    _local.declared = set()
    return channel


def _ensure_queue(channel, queue_name: str):
    """Declare a queue at most once per connection to avoid redundant round-trips."""
    declared = getattr(_local, "declared", None)
    if declared is None:
        declared = set()
        _local.declared = declared
    if queue_name not in declared:
        channel.queue_declare(queue=queue_name, durable=True)
        declared.add(queue_name)


def _close_local(quiet: bool = False):
    """Tear down the cached connection for the current greenlet."""
    connection = getattr(_local, "connection", None)
    if connection is not None:
        try:
            if connection.is_open:
                connection.close()
        except Exception:
            if not quiet:
                logging.warning("Error closing RabbitMQ connection", exc_info=True)
    _local.connection = None
    _local.channel = None
    _local.declared = set()


def _run_with_reconnect(operation):
    """Run ``operation(channel)`` reusing the cached connection, reconnecting on failure.

    ``operation`` receives an open channel and returns a result. If the cached
    connection has been dropped by the broker (a common outcome under heavy
    connection churn), we discard it and retry with a freshly opened one.
    """
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            channel = _get_channel()
            return operation(channel)
        except (
            pika.exceptions.AMQPConnectionError,
            pika.exceptions.AMQPChannelError,
            pika.exceptions.StreamLostError,
            pika.exceptions.ConnectionClosed,
            pika.exceptions.ChannelClosed,
            ConnectionResetError,
            OSError,
        ) as exc:
            last_exc = exc
            # Force a reconnect on the next iteration.
            _close_local(quiet=True)
            if attempt < _MAX_RETRIES:
                logging.warning(
                    "RabbitMQ operation failed (attempt %d/%d), reconnecting: %s",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    exc,
                )
    raise last_exc


def sync_publish(queue_name: str, message: str):
    def _op(channel):
        _ensure_queue(channel, queue_name)
        channel.basic_publish(
            exchange='',  # Default exchange
            routing_key=queue_name,
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent  # Make message persistent
            ),
        )

    _run_with_reconnect(_op)


def get_one_or_none(queue_name='task_queue'):
    """
    Attempts to fetch exactly one message from the specified queue.
    Returns the message body (str) if available, otherwise returns None.
    """
    def _op(channel):
        _ensure_queue(channel, queue_name)
        # auto_ack=False means we manually acknowledge after processing.
        method_frame, header_frame, body = channel.basic_get(queue=queue_name, auto_ack=False)
        if method_frame:
            message_content = body.decode('utf-8')
            channel.basic_ack(delivery_tag=method_frame.delivery_tag)
            return message_content
        return None

    return _run_with_reconnect(_op)
