import random
import sys
import time
from pathlib import Path

from locust import task

from base_user import BaseUser
from locust_common.rabbitmq import get_one_or_none, FUNDED_PORTFOLIO_QUEUE_NAME, sync_publish, MODEL_QUEUE_NAME, \
    REBALANCE_QUEUE_NAME, ORDER_QUEUE_NAME

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

        # Get a funded portfolio
        funded_portfolio_id = get_one_or_none(FUNDED_PORTFOLIO_QUEUE_NAME)
        if not funded_portfolio_id:
            return

        # Create models for each funded portfolio
        model_ids = self.create_models_for_portfolios([funded_portfolio_id])
        time.sleep(random.uniform(1, 10))

        if not model_ids:
            return

        # Get the models to generate load and put them in the queue
        for model_id in model_ids:
            time.sleep(random.uniform(1, 10))
            portal_client.get_investment_model(self.client, model_id)
            time.sleep(random.uniform(1, 10))
            sync_publish(MODEL_QUEUE_NAME, model_id)

        # Rebalance one of the models
        time.sleep(random.uniform(1, 10))
        rebalance_id = self.rebalance_models(model_ids[0])
        sync_publish(REBALANCE_QUEUE_NAME, rebalance_id)

        # Submit the rebalance (send to the Order Service)
        time.sleep(random.uniform(1, 10))
        order_ids = self.submit_rebalance(rebalance_id)
        # Process order_ids in batches of max_orders
        max_orders = 10
        for i in range(0, len(order_ids), max_orders):
            try:
                batch_order_ids = order_ids[i:i + max_orders]
                time.sleep(random.uniform(1, 10))
                # Submit order (send to Trading Service)
                submitted_order_ids = self.submit_orders(batch_order_ids)
                for submitted_order_id in submitted_order_ids:
                    sync_publish(ORDER_QUEUE_NAME, str(submitted_order_id))
                    time.sleep(random.uniform(1, 10))
                # Submit trades (send to Execution Service)
                # self.submit_trades(submitted_order_ids)
            except Exception as e:
                print(f"Error submitting orders for batch {i}: {e}")
                continue


"""Trader role Locust user class."""

from locust import HttpUser, task, between


class TraderUser(HttpUser):
    """Simulates trader HTTP traffic."""

    wait_time = between(60, 60)

    @task
    def default_task(self) -> None:
        """Placeholder task - sleeps for the wait duration."""
        pass
