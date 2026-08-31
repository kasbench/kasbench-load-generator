"""RabbitMQ helpers for the load generator.

Design (why it looks like this)
-------------------------------
Under Locust every simulated user runs in its own gevent greenlet. The naive
approach -- open a connection per operation, or even one persistent connection
per greenlet -- creates hundreds of concurrent AMQP connections and a storm of
handshakes. When the broker is co-located with the CPU-hungry load generator,
its connection acceptor gets starved of CPU during load spikes and resets
handshakes ("Connection reset by peer" / the misleading ProbableAccessDenied).

To bound the connection count regardless of how many users are running we split
the two usage patterns:

* Publishing is fire-and-forget. ``sync_publish`` no longer talks to RabbitMQ on
  the calling greenlet; it drops the message onto an in-process queue. A small,
  fixed pool of dedicated *publisher* greenlets drains that queue over a handful
  of long-lived connections. A transient reset therefore never fails a Locust
  task, and the number of publishing connections is capped at ``_PUBLISHER_COUNT``.

* Reading (``get_one_or_none``) must stay synchronous -- callers use the returned
  value immediately. Instead of a connection per greenlet, reads borrow a
  connection from a small shared pool (``_READER_POOL_SIZE``) and return it,
  capping read connections too.

Net effect: connection count goes from O(number of users) to
O(_PUBLISHER_COUNT + _READER_POOL_SIZE), which removes the acceptor pressure that
caused the resets. The public API (``sync_publish``, ``get_one_or_none`` and the
``*_QUEUE_NAME`` constants) is unchanged, so callers need no edits.
"""

import logging
import random
import time

import gevent
from gevent.queue import Queue as GeventQueue
from gevent.lock import BoundedSemaphore

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

# Pika logs full ERROR-level tracebacks (StreamLostError, the misleading
# "ProbableAccessDeniedError" / "probable permission error" messages) whenever
# a connection is torn down -- including drops this module transparently
# recovers from. Silence pika below CRITICAL so its internal teardown noise
# doesn't flood the logs; our own logging (below) is the source of truth.
logging.getLogger("pika").setLevel(logging.CRITICAL)

_log = logging.getLogger("rabbitmq")

# ---------------------------------------------------------------------------
# Tuning knobs
# ---------------------------------------------------------------------------

# Number of dedicated publisher greenlets (each holds one connection). Each one
# drains and publishes serially, so sustained throughput scales roughly linearly
# with this count. Still a tiny, fixed number of connections for the broker.
# Overridable via RABBITMQ_PUBLISHERS for tuning against your peak load.
_PUBLISHER_COUNT = config.RABBITMQ_PUBLISHERS

# Max messages buffered in memory awaiting publish. Bounded so a broker outage
# can't grow memory without limit. If the buffer fills, sync_publish blocks
# briefly (applying natural backpressure) rather than dropping messages.
_PUBLISH_BUFFER_SIZE = 10000

# How long sync_publish waits for buffer space before giving up on a message.
_ENQUEUE_TIMEOUT_SECONDS = 5.0

# Each publisher greenlet drains up to this many messages per wake-up and
# publishes them back-to-back before yielding, amortizing per-iteration
# overhead and greatly increasing sustained throughput.
_PUBLISH_BATCH_SIZE = 100

# Persistent (delivery_mode=2) messages force the broker to fsync each message
# to disk before it's considered stored, which serializes publishing and is the
# dominant throughput limiter under load. For a load generator these queues hold
# transient IDs that other simulated users pull back out; losing one occasionally
# just means a workflow isn't picked up, which is already tolerated (see the
# buffer-full drop path). So default to transient (non-persistent) delivery for
# far higher publish throughput. Set RABBITMQ_PERSISTENT=1 to restore durability.
_DELIVERY_MODE = (
    pika.DeliveryMode.Persistent
    if config.RABBITMQ_PERSISTENT
    else pika.DeliveryMode.Transient
)

# Number of pooled connections shared by synchronous readers (get_one_or_none).
_READER_POOL_SIZE = 4

# Retry behaviour for connection operations (open + single op).
_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 0.1
_BACKOFF_MAX_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Connection parameters
# ---------------------------------------------------------------------------

def _connection_parameters() -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        # Long-lived pooled/publisher connections are used frequently, so
        # heartbeats are appropriate here to detect dead peers. Kept modest.
        heartbeat=30,
        blocked_connection_timeout=30,
        # Give the handshake room to complete when the broker's acceptor is
        # briefly starved of CPU during a load spike.
        socket_timeout=15,
        stack_timeout=20,
        tcp_options={"TCP_KEEPIDLE": 20, "TCP_KEEPINTVL": 10, "TCP_KEEPCNT": 3},
    )


def _open_connection_with_retry():
    """Open a fresh BlockingConnection, retrying with jittered backoff.

    Returns an open connection, or raises the last exception if all attempts
    fail. Used by both the publisher greenlets and the reader pool.
    """
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return pika.BlockingConnection(_connection_parameters())
        except (
            pika.exceptions.AMQPConnectionError,
            pika.exceptions.StreamLostError,
            ConnectionResetError,
            OSError,
        ) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                backoff = min(_BACKOFF_BASE_SECONDS * (2 ** attempt), _BACKOFF_MAX_SECONDS)
                # gevent.sleep yields the hub so the broker's acceptor can catch up.
                gevent.sleep(random.uniform(0, backoff))
    raise last_exc


def _declare(channel, declared: set, queue_name: str):
    """Declare a queue at most once per connection to avoid redundant round-trips."""
    if queue_name not in declared:
        channel.queue_declare(queue=queue_name, durable=True)
        declared.add(queue_name)


# ---------------------------------------------------------------------------
# Publisher side: in-process buffer drained by dedicated greenlets
# ---------------------------------------------------------------------------

_publish_buffer = GeventQueue(maxsize=_PUBLISH_BUFFER_SIZE)
_publishers_started = False
_publisher_start_lock = BoundedSemaphore(1)


def _drain_batch():
    """Block for one message, then greedily collect up to a full batch.

    Returns a list of (queue_name, message) tuples. Batching lets each publisher
    push many messages between gevent yields, which is where the throughput gain
    comes from versus one-message-per-iteration.
    """
    batch = [_publish_buffer.get()]  # blocks until at least one is available
    while len(batch) < _PUBLISH_BATCH_SIZE:
        try:
            batch.append(_publish_buffer.get_nowait())
        except gevent.queue.Empty:
            break
    return batch


def _publisher_loop(worker_id: int):
    """Long-lived greenlet: hold one connection and drain the publish buffer."""
    connection = None
    channel = None
    declared = set()

    while True:
        batch = _drain_batch()

        for queue_name, message in batch:
            published = False
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    if connection is None or not connection.is_open or channel is None or not channel.is_open:
                        connection = _open_connection_with_retry()
                        channel = connection.channel()
                        declared = set()

                    _declare(channel, declared, queue_name)
                    channel.basic_publish(
                        exchange='',  # Default exchange
                        routing_key=queue_name,
                        body=message,
                        properties=pika.BasicProperties(delivery_mode=_DELIVERY_MODE),
                    )
                    published = True
                    break
                except (
                    pika.exceptions.AMQPConnectionError,
                    pika.exceptions.AMQPChannelError,
                    pika.exceptions.StreamLostError,
                    pika.exceptions.ConnectionClosed,
                    pika.exceptions.ChannelClosed,
                    ConnectionResetError,
                    OSError,
                ) as exc:
                    # Drop the dead connection; reopen on next attempt.
                    _safe_close(connection)
                    connection, channel, declared = None, None, set()
                    if attempt < _MAX_RETRIES:
                        backoff = min(_BACKOFF_BASE_SECONDS * (2 ** attempt), _BACKOFF_MAX_SECONDS)
                        gevent.sleep(random.uniform(0, backoff))
                    else:
                        _log.warning(
                            "publisher %d dropped a message to %s after %d attempts: %s",
                            worker_id, queue_name, _MAX_RETRIES + 1, exc,
                        )

            if not published:
                # Last-resort re-queue so a healthier publisher can retry, unless
                # the buffer is full (then drop to avoid blocking during outage).
                try:
                    _publish_buffer.put_nowait((queue_name, message))
                except Exception:
                    pass


def _ensure_publishers():
    """Start the publisher greenlet pool exactly once."""
    global _publishers_started
    if _publishers_started:
        return
    with _publisher_start_lock:
        if _publishers_started:
            return
        for i in range(_PUBLISHER_COUNT):
            gevent.spawn(_publisher_loop, i)
        _publishers_started = True


def sync_publish(queue_name: str, message: str):
    """Enqueue a message for asynchronous publishing.

    Despite the name (kept for API compatibility), this no longer performs a
    synchronous network round-trip. It hands the message to the background
    publisher pool and returns immediately, so a transient RabbitMQ reset can
    never fail the calling Locust task. Blocks only briefly if the in-memory
    buffer is full (backpressure).
    """
    _ensure_publishers()
    try:
        _publish_buffer.put((queue_name, message), timeout=_ENQUEUE_TIMEOUT_SECONDS)
    except gevent.queue.Full:
        # Buffer saturated for too long -- the broker is badly behind. Drop this
        # message rather than blocking the user task indefinitely, and log it.
        _log.warning(
            "publish buffer full; dropping message to %s (broker falling behind)",
            queue_name,
        )


# ---------------------------------------------------------------------------
# Reader side: small shared connection pool for synchronous get()
# ---------------------------------------------------------------------------

_reader_pool = GeventQueue()
_reader_pool_initialized = False
_reader_pool_lock = BoundedSemaphore(1)


class _PooledConnection:
    """Holds a connection + channel + set of declared queues for reuse."""

    __slots__ = ("connection", "channel", "declared")

    def __init__(self):
        self.connection = None
        self.channel = None
        self.declared = set()

    def channel_ready(self):
        if (
            self.connection is not None and self.connection.is_open
            and self.channel is not None and self.channel.is_open
        ):
            return self.channel
        # (Re)open lazily.
        _safe_close(self.connection)
        self.connection = _open_connection_with_retry()
        self.channel = self.connection.channel()
        self.declared = set()
        return self.channel

    def reset_channel(self):
        """Rebuild just the channel, keeping the underlying connection.

        A pika channel is single-operation-at-a-time. If a basic_get is
        interrupted (e.g. the borrowing greenlet is killed mid-call, or a
        reset happens between the get and its GetOk), the channel is left with
        a half-registered GetOk callback and every subsequent basic_get on it
        raises DuplicateGetOkCallback. Recreating the channel clears that state
        without paying for a full reconnect handshake.
        """
        if self.connection is not None and self.connection.is_open:
            try:
                if self.channel is not None and self.channel.is_open:
                    self.channel.close()
            except Exception:
                pass
            try:
                self.channel = self.connection.channel()
                self.declared = set()
                return
            except Exception:
                # Channel couldn't be rebuilt on this connection; fall through
                # to a full close so channel_ready() reopens everything.
                pass
        self.close()

    def close(self):
        _safe_close(self.connection)
        self.connection = None
        self.channel = None
        self.declared = set()


def _ensure_reader_pool():
    global _reader_pool_initialized
    if _reader_pool_initialized:
        return
    with _reader_pool_lock:
        if _reader_pool_initialized:
            return
        for _ in range(_READER_POOL_SIZE):
            _reader_pool.put(_PooledConnection())
        _reader_pool_initialized = True


def get_one_or_none(queue_name='task_queue'):
    """
    Attempts to fetch exactly one message from the specified queue.
    Returns the message body (str) if available, otherwise returns None.

    Borrows a connection from a bounded shared pool so the number of read
    connections stays capped no matter how many user greenlets call this.
    """
    _ensure_reader_pool()

    # Borrow a pooled connection (blocks briefly if all are in use).
    pooled = _reader_pool.get()
    last_exc = None
    completed = False
    try:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                channel = pooled.channel_ready()
                _declare(channel, pooled.declared, queue_name)
                method_frame, _header, body = channel.basic_get(
                    queue=queue_name, auto_ack=False
                )
                if method_frame:
                    message_content = body.decode('utf-8')
                    channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                    completed = True
                    return message_content
                completed = True
                return None
            except pika.exceptions.ChannelError as exc:
                # Channel-level fault (notably DuplicateGetOkCallback from an
                # interrupted prior basic_get, which subclasses ChannelError but
                # NOT AMQPChannelError). Rebuild just the channel to clear the
                # stale GetOk state; the connection itself is still good.
                last_exc = exc
                pooled.reset_channel()
                if attempt < _MAX_RETRIES:
                    backoff = min(_BACKOFF_BASE_SECONDS * (2 ** attempt), _BACKOFF_MAX_SECONDS)
                    gevent.sleep(random.uniform(0, backoff))
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
                pooled.close()  # force full reopen on next attempt
                if attempt < _MAX_RETRIES:
                    backoff = min(_BACKOFF_BASE_SECONDS * (2 ** attempt), _BACKOFF_MAX_SECONDS)
                    gevent.sleep(random.uniform(0, backoff))
        _log.warning(
            "get_one_or_none(%s) failed after %d attempts: %s",
            queue_name, _MAX_RETRIES + 1, last_exc,
        )
        raise last_exc
    finally:
        # If this borrow did not finish cleanly (an exception propagated, or the
        # greenlet was killed by Locust mid-basic_get), the channel may be left
        # with a half-registered GetOk callback. Reset it before returning to the
        # pool so the next borrower never inherits a poisoned channel -- the
        # cause of the DuplicateGetOkCallback storms.
        if not completed:
            try:
                pooled.reset_channel()
            except Exception:
                pooled.close()
        # Always return the connection to the pool (even if closed; it will be
        # lazily reopened by the next borrower).
        _reader_pool.put(pooled)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_close(connection):
    if connection is not None:
        try:
            if connection.is_open:
                connection.close()
        except Exception:
            pass
