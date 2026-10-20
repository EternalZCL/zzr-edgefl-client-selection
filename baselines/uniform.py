"""Reproducible selector example, with JSON-roundtrippable RNG state."""

import random
from typing import Any, Mapping, Sequence

from benchmark.interfaces import BudgetState, ClientHistory, ClientInfo, RoundFeedback


def _tuples(value):
    return tuple(_tuples(item) for item in value) if isinstance(value, (list, tuple)) else value


class UniformPolicy:
    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)

    def select(
        self,
        available_clients: Sequence[ClientInfo],
        budget_state: BudgetState,
        history: Mapping[int, ClientHistory],
        num_clients: int = 6,
    ) -> list[int]:
        ids = [client.client_id for client in available_clients]
        if len(set(ids)) != len(ids):
            raise ValueError("Available client IDs must be unique.")
        if type(num_clients) is not int or not 0 <= num_clients <= len(ids):
            raise ValueError("num_clients must be an integer within the available population.")
        return self._rng.sample(ids, num_clients)

    def observe(self, round_feedback: RoundFeedback) -> None:
        pass

    def state_dict(self) -> dict[str, Any]:
        return {"version": 1, "rng_state": self._rng.getstate()}

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        if state.get("version") != 1:
            raise ValueError("Unsupported UniformPolicy state version.")
        self._rng.setstate(_tuples(state["rng_state"]))
