"""Locust HttpUser subclasses for each KASBench role."""

from kasbench_load_generator.users.portfolio_manager_user import PortfolioManagerUser
from kasbench_load_generator.users.trader_user import TraderUser
from kasbench_load_generator.users.back_office_user import BackOfficeUser
from kasbench_load_generator.users.investor_user import InvestorUser
from kasbench_load_generator.users.it_operations_user import ItOperationsUser

__all__ = [
    "PortfolioManagerUser",
    "TraderUser",
    "BackOfficeUser",
    "InvestorUser",
    "ItOperationsUser",
]
