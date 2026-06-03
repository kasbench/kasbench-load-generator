"""Back Office role Locust user class."""

import random
import sys
import time
from pathlib import Path

from locust import task, between

from base_user import BaseUser
from locust_common.rabbitmq import sync_publish, PORTFOLIO_QUEUE_NAME, FUNDED_PORTFOLIO_QUEUE_NAME

# Add the kasbench_load_generator package directory to sys.path so that
# locust_common can be resolved when Locust runs this file as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import locust_common.portal_client as portal_client

from locust_common.portal_common import post_portfolio_group


class BackOfficeUser(BaseUser):
    """Simulates back office HTTP traffic."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    wait_time = between(30, 60)

    @task
    def run_sequential(self):
        time.sleep(random.uniform(1, 10))
        # Create a group of portfolios
        portfolio_ids = post_portfolio_group(self.client)

        # Publish the portfolio ids to the RabbitMQ queue (with a delay
        for portfolio_id in portfolio_ids:
            sync_publish(PORTFOLIO_QUEUE_NAME, portfolio_id)
            time.sleep(random.uniform(1, 10))
            # Get the portfolio (simulate a read operation)
            portal_client.get_portfolio(self.client, portfolio_id)
            time.sleep(random.uniform(1, 10))

        # Fund the portfolios
        funded_portfolio_ids = self.fund_portfolios_with_cash(portfolio_ids)

        # Publish the funded portfolio ids to the RabbitMQ queue (with a delay)
        for portfolio_id in funded_portfolio_ids:
            sync_publish(FUNDED_PORTFOLIO_QUEUE_NAME, portfolio_id)
            time.sleep(random.uniform(1, 10))


        # ADD MORE OPERATIONS LATER

        # # Create models for each funded portfolio
        # model_ids = self.create_models_for_portfolios(funded_portfolio_ids)
        # time.sleep(random.uniform(1, 5))
        # # Get the models
        # for model_id in model_ids:
        #     time.sleep(random.uniform(0, 2))
        #     portal_client.get_investment_model(self.client, model_id)
        # # Rebalance one of the models
        # time.sleep(random.uniform(1, 5))
        # rebalance_id = self.rebalance_models(model_ids[0])
        # # Submit the rebalance (send to the Order Service)
        # time.sleep(random.uniform(1, 5))
        # order_ids = self.submit_rebalance(rebalance_id)
        # # Process order_ids in batches of max_orders
        # max_orders = 10
        # for i in range(0, len(order_ids), max_orders):
        #     try:
        #         batch_order_ids = order_ids[i:i + max_orders]
        #         time.sleep(random.uniform(0, 2))
        #         # Submit order (send to Trading Service)
        #         submitted_order_ids = self.submit_orders(batch_order_ids)
        #         time.sleep(random.uniform(0, 2))
        #         # Submit trades (send to Execution Service)
        #         self.submit_trades(submitted_order_ids)
        #     except Exception as e:
        #         print(f"Error submitting orders for batch {i}: {e}")
        #         continue
        # # Get next 10 orders
        # time.sleep(random.uniform(0, 2))
        # portal_client.get_orders(self.client, offset=self.counter * 10, limit=10)
        # # Get the next 10 trades
        # time.sleep(random.uniform(0, 2))
        # portal_client.get_trades(self.client, offset=self.counter * 10, limit=10)
        # self.counter += 1
        # # Get executions for the first portfolio id
        # time.sleep(random.uniform(0, 2))
        # portal_client.get_executions(self.client, portfolio_id=portfolio_ids[0])

