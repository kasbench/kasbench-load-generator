import random
import sys
import time
from pathlib import Path

from locust import task

from base_user import BaseUser
from locust_common.rabbitmq import get_one_or_none, FUNDED_PORTFOLIO_QUEUE_NAME, sync_publish, MODEL_QUEUE_NAME, \
    REBALANCE_QUEUE_NAME, ORDER_QUEUE_NAME, EXECUTION_QUEUE_NAME

# Add the kasbench_load_generator package directory to sys.path so that
# locust_common can be resolved when Locust runs this file as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import locust_common.portal_client as portal_client

from locust_common.portal_common import post_portfolio_group


class TraderUser(BaseUser):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @task
    def run_sequential(self):
        time.sleep(random.uniform(1, 10))

        # Get a submitted order
        order_id = get_one_or_none(ORDER_QUEUE_NAME)
        if not order_id:
            return

        # Execute the trade
        execution_id = self.submit_trade(int(order_id))

        # Publish the execution id to the execution queue
        sync_publish(EXECUTION_QUEUE_NAME, str(execution_id))

        time.sleep(random.uniform(1, 10))
