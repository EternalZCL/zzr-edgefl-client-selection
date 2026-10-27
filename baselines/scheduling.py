"""Scheduling baselines using only metadata and paid historical feedback.

Oort is an independent, limited adaptation of Lai et al. OSDI 2021 and
https://github.com/SymbioticLab/Oort/blob/master/oort/oort.py, not the original
distributed implementation. It retains RMS utility, staleness confidence,
clipping, duration penalty, weighted exploitation, exploration and a pacer.
After the shared warmup, exploration samples clients uniformly; this differs
from the original implementation, whose unexplored-client pool is exhausted.
"""

import math
import statistics

from baselines.uniform import UniformPolicy


class RoundRobinPolicy(UniformPolicy):
    cost_key = "round_robin"

    def __init__(self, seed=0):
        super().__init__(seed)
        self.queue = []

    def select(self, available_clients, budget_state, history, num_clients=6):
        ids = sorted(client.client_id for client in available_clients)
        if not 0 <= num_clients <= len(ids) or len(ids) != len(set(ids)):
            raise ValueError("Invalid round-robin population or quota.")
        if self.queue and not set(self.queue) <= set(ids):
            raise ValueError("Round-robin population changed.")
        selected = []
        while len(selected) < num_clients:
            if not self.queue:
                remaining = [client for client in ids if client not in selected]
                self._rng.shuffle(remaining)
                self.queue = remaining
            selected.append(self.queue.pop(0))
        return selected

    def state_dict(self):
        return {**super().state_dict(), "queue": list(self.queue)}

    def load_state_dict(self, state):
        super().load_state_dict(state)
        self.queue = list(state["queue"])


class FastRandomPolicy(UniformPolicy):
    cost_key = "fast_random"

    def __init__(self, seed=0, exploration=0.2):
        super().__init__(seed)
        if not 0 <= exploration <= 1:
            raise ValueError("Exploration must be in [0,1].")
        self.exploration = exploration

    def select(self, available_clients, budget_state, history, num_clients=6):
        clients = list(available_clients)
        if not 0 <= num_clients <= len(clients):
            raise ValueError("Invalid quota.")
        self._rng.shuffle(clients)
        clients.sort(key=lambda client: client.compute_time_multiplier)
        fast_count = num_clients - round(num_clients * self.exploration)
        selected = [client.client_id for client in clients[:fast_count]]
        selected += self._rng.sample([c.client_id for c in clients if c.client_id not in selected],
                                     num_clients - len(selected))
        return selected

    def state_dict(self):
        return {**super().state_dict(), "exploration": self.exploration}

    def load_state_dict(self, state):
        if state["exploration"] != self.exploration:
            raise ValueError("Changed fast/random parameters.")
        super().load_state_dict(state)


class OortPolicy(UniformPolicy):
    cost_key = "oort"

    def __init__(self, seed=0, exploration=0.3, pacer_window=5, utility="normalized"):
        super().__init__(seed)
        if not 0 <= exploration <= 1 or pacer_window < 1 or utility not in {"normalized", "original"}:
            raise ValueError("Invalid Oort settings.")
        self.exploration, self.pacer_window, self.utility = exploration, pacer_window, utility
        self.duration_percentile, self.utilities, self.round = 0.5, [], 0

    def scores(self, clients, budget, history):
        durations = sorted(c.compute_time_multiplier for c in clients)
        target = durations[min(len(durations) - 1, int(self.duration_percentile * len(durations)))]
        rewards = {}
        for client in clients:
            previous = history.get(client.client_id)
            loss = ((previous.last_observed_train_loss_rms or previous.last_observed_train_loss)
                    if previous else None)
            reward = float(loss if loss is not None else 1.0)
            if self.utility == "original":
                reward *= client.train_examples
            rewards[client.client_id] = reward
        values = sorted(rewards.values())
        clip = values[min(len(values) - 1, int(0.95 * len(values)))]
        lower, span = min(values), max(clip - min(values), 1e-4)
        result = {}
        for client in clients:
            previous = history.get(client.client_id)
            last = previous.last_participation_sim_seconds if previous else None
            staleness = max(0.0, (budget.sim_seconds_used - (last or 0.0))
                            / max(budget.sim_seconds_used, 1e-9))
            confidence = math.sqrt(0.1 * math.log(self.round + 2) * staleness)
            score = (min(rewards[client.client_id], clip) - lower) / span + confidence + 1e-6
            result[client.client_id] = score * min(1.0, target / client.compute_time_multiplier) ** 2
        return result

    def select(self, available_clients, budget_state, history, num_clients=6):
        clients = list(available_clients)
        if not 0 <= num_clients <= len(clients) or not clients:
            raise ValueError("Invalid Oort quota/population.")
        scores = self.scores(clients, budget_state, history)
        ids = sorted(scores)
        explore = round(num_clients * self.exploration)
        selected = self._rng.sample(ids, explore)
        pool = sorted((c for c in ids if c not in selected), key=lambda c: (-scores[c], c))
        pool = pool[:max(num_clients - explore, math.ceil(0.8 * len(pool)))]
        while len(selected) < num_clients:
            chosen = self._rng.choices(pool, weights=[scores[c] for c in pool], k=1)[0]
            pool.remove(chosen)
            selected.append(chosen)
        return selected

    def observe(self, round_feedback):
        self.round += 1
        values = round_feedback.observed_train_loss_rms or round_feedback.observed_train_losses
        self.utilities.append(statistics.mean(values.values()))
        window = self.pacer_window
        if self.round >= 2 * window and self.round % window == 0:
            previous = sum(self.utilities[-2 * window:-window])
            current = sum(self.utilities[-window:])
            if abs(current - previous) <= 0.1 * max(previous, 1e-9):
                self.duration_percentile = min(1.0, self.duration_percentile + 0.1)
            elif current >= previous * 5:
                self.duration_percentile = max(0.1, self.duration_percentile - 0.1)

    def state_dict(self):
        return {**super().state_dict(), "exploration": self.exploration,
                "pacer_window": self.pacer_window, "utility": self.utility,
                "duration_percentile": self.duration_percentile,
                "utilities": list(self.utilities), "round": self.round}

    def load_state_dict(self, state):
        for key in ("exploration", "pacer_window", "utility"):
            if state[key] != getattr(self, key):
                raise ValueError("Changed Oort parameters.")
        super().load_state_dict(state)
        self.duration_percentile = state["duration_percentile"]
        self.utilities, self.round = list(state["utilities"]), state["round"]
