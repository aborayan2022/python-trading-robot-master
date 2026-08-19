"""Broker factory and package exports."""

from pyrobot.brokers.base import BrokerInterface
from pyrobot.brokers.paper_broker import PaperBroker


def create_broker(broker_name: str, **kwargs) -> BrokerInterface:
    """Factory to instantiate the correct broker adapter.

    Arguments:
        broker_name: One of 'schwab', 'alpaca', 'ibkr', 'paper'.
        **kwargs: Broker-specific configuration (api keys, host, etc.)

    Returns:
        An initialized BrokerInterface instance.

    Raises:
        ValueError: If broker_name is not recognized.
    """
    broker_map = {
        "schwab": _create_schwab,
        "alpaca": _create_alpaca,
        "ibkr": _create_ibkr,
        "paper": _create_paper,
    }

    if broker_name not in broker_map:
        available = list(broker_map.keys())
        raise ValueError(
            f"Unknown broker: {broker_name}. Available: {available}"
        )

    return broker_map[broker_name](**kwargs)


def _create_schwab(**kwargs) -> BrokerInterface:
    from pyrobot.brokers.schwab_broker import SchwabBroker

    return SchwabBroker(**kwargs)


def _create_alpaca(**kwargs) -> BrokerInterface:
    from pyrobot.brokers.alpaca_broker import AlpacaBroker

    return AlpacaBroker(**kwargs)


def _create_ibkr(**kwargs) -> BrokerInterface:
    from pyrobot.brokers.ibkr_broker import IBKRBroker

    return IBKRBroker(**kwargs)


def _create_paper(**kwargs) -> BrokerInterface:
    return PaperBroker(**kwargs)


__all__ = [
    "BrokerInterface",
    "PaperBroker",
    "create_broker",
]
