import logging

import pika



import config

PORTFOLIO_QUEUE_NAME = 'portfolio_queue'
FUNDED_PORTFOLIO_QUEUE_NAME = 'funded_portfolio_queue'
MODEL_QUEUE_NAME = 'model_queue'
REBALANCE_QUEUE_NAME = 'rebalance_queue'

TRANSACTION_QUEUE_NAME = 'transaction_queue'
ORDER_QUEUE_NAME = 'order_queue'
CASH_QUEUE_NAME = 'cash_queue'
PORTFOLIO_GROUP_QUEUE_NAME = 'portfolio_group_queue'
ORDER_GROUP_QUEUE_NAME = 'order_group_queue'
CASH_GROUP_QUEUE_NAME = 'cash_group_queue'
MODEL_GROUP_QUEUE_NAME = 'model_group_queue'

# Mute pika's verbose INFO logs, only show WARNING or ERROR if something actually breaks
logging.getLogger("pika").setLevel(logging.WARNING)


def sync_publish(queue_name:str, message:str):
    # 1. Establish connection to RabbitMQ server
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=config.RABBITMQ_HOST, port=config.RABBITMQ_PORT))
    channel = connection.channel()

    # 2. Declare a queue (creates it if it doesn't exist)
    channel.queue_declare(queue=queue_name, durable=True)

    # 3. Publish a message
    channel.basic_publish(
        exchange='', # Default exchange
        routing_key=queue_name,
        body=message,
        properties=pika.BasicProperties(
            delivery_mode=pika.DeliveryMode.Persistent # Make message persistent
        )
    )

    # 4. Clean up connection
    connection.close()


def get_one_or_none(queue_name='task_queue'):
    """
    Attempts to fetch exactly one message from the specified queue.
    Returns the message body (str) if available, otherwise returns None.
    """
    # 1. Establish connection and channel
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=config.RABBITMQ_HOST, port=config.RABBITMQ_PORT))
    channel = connection.channel()

    # 2. Declare the queue to ensure it exists
    channel.queue_declare(queue=queue_name, durable=True)

    # 3. Perform a single pull request (basic_get)
    # auto_ack=False means we will manually acknowledge the message after processing
    method_frame, header_frame, body = channel.basic_get(queue=queue_name, auto_ack=False)

    # 4. Evaluate the result
    if method_frame:
        # A message was successfully retrieved from the queue
        message_content = body.decode('utf-8')

        # Acknowledge to RabbitMQ that we processed the item safely
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)

        result = message_content
    else:
        # The queue was empty
        result = None

    # 5. Clean up connection
    connection.close()

    return result