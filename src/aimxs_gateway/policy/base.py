from __future__ import annotations

from abc import ABC, abstractmethod
from aimxs_gateway.schemas import DecisionRequest, Decision


class PolicyPlugin(ABC):
    @abstractmethod
    def evaluate(self, req: DecisionRequest) -> Decision:
        raise NotImplementedError
