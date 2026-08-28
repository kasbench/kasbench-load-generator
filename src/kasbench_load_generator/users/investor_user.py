import random
import sys
import time
from pathlib import Path

from locust import task

from base_user import BaseUser
from locust_common.rabbitmq import get_one_or_none, FUNDED_PORTFOLIO_QUEUE_NAME, sync_publish, MODEL_QUEUE_NAME, \
    REBALANCE_QUEUE_NAME, ORDER_QUEUE_NAME, PORTFOLIO_QUEUE_NAME, EXECUTION_QUEUE_NAME

# Add the kasbench_load_generator package directory to sys.path so that
# locust_common can be resolved when Locust runs this file as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import locust_common.portal_client as portal_client

from locust_common.portal_common import post_portfolio_group



class Investor(BaseUser):

    wait_time = between(5, 20)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # @task(90)
    # def no_op(self):
    #     time.sleep(5)

    @task(10)
    def run_sequential(self):
        self.wait_short()

        # Get a portfolio
        portfolio_id = get_one_or_none(PORTFOLIO_QUEUE_NAME)
        if portfolio_id:
            # Put the portfolio back in the queue (so we don't run out of portfolios)
            sync_publish(PORTFOLIO_QUEUE_NAME, portfolio_id)

            # Get the portfolio (simulate a read operation)
            portal_client.get_portfolio(self.client, portfolio_id)
            self.wait_short()

        # Get an execution
        self.wait_short()
        execution_id = get_one_or_none(EXECUTION_QUEUE_NAME)
        if execution_id:
            # Put the execution_id back in the queue (so we don't run out of executions)
            sync_publish(EXECUTION_QUEUE_NAME, execution_id)

            # Get the execution (simulate a read operation)
            portal_client.get_execution(self.client, execution_id)
            self.wait_short()






