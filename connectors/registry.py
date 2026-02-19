from dataclasses import dataclass
from typing import Any, Callable, Dict, List


@dataclass
class ConnectorSpec:
    name: str
    source_name: str
    source_tier: int
    signal_type: str
    fetch: Callable[..., List[Dict[str, Any]]]


CONNECTORS: List[ConnectorSpec] = []


def register(spec: ConnectorSpec):
    CONNECTORS.append(spec)


def list_connectors() -> List[ConnectorSpec]:
    return CONNECTORS
