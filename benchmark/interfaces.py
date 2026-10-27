"""Public, training-only information exposed to candidate selection policies."""

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ClientInfo:
    client_id: int
    train_examples: int
    compute_time_multiplier: float


@dataclass(frozen=True)
class BudgetState:
    sim_seconds_used: float
    budget_sim_seconds: float


@dataclass(frozen=True)
class ClientHistory:
    participations: int = 0
    last_participation_sim_seconds: float | None = None
    last_observed_train_loss: float | None = None
    last_observed_train_loss_rms: float | None = None


@dataclass(frozen=True)
class RoundFeedback:
    selected_clients: tuple[int, ...]
    sim_seconds_used: float
    observed_train_losses: Mapping[int, float]
    observed_train_loss_rms: Mapping[int, float] = field(default_factory=dict)


class SelectionPolicy(Protocol):
    def select(
        self,
        available_clients: Sequence[ClientInfo],
        budget_state: BudgetState,
        history: Mapping[int, ClientHistory],
        num_clients: int = 6,
    ) -> list[int]: ...

    def observe(self, round_feedback: RoundFeedback) -> None: ...

    def state_dict(self) -> dict[str, Any]: ...

    def load_state_dict(self, state: Mapping[str, Any]) -> None: ...
