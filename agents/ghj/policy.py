"""Age-triggered coverage plus fast/random; an interpretable known-rule combination."""

from baselines.scheduling import FastRandomPolicy


class Policy(FastRandomPolicy):
    cost_key = "ghj_coverage"

    def __init__(self, seed=0, exploration=0.2, coverage_slots=1, wait_fraction=0.1,
                 ablation=None):
        super().__init__(seed, exploration)
        if coverage_slots not in (0, 1, 2) or not 0 < wait_fraction <= 1:
            raise ValueError("Invalid coverage configuration.")
        if ablation not in (None, "no_wait", "no_speed"):
            raise ValueError("Unknown ablation.")
        self.coverage_slots, self.wait_fraction, self.ablation = coverage_slots, wait_fraction, ablation

    def select(self, available_clients, budget_state, history, num_clients=6):
        clients = list(available_clients)
        threshold = self.wait_fraction * budget_state.budget_sim_seconds
        def age(client):
            previous = history.get(client.client_id)
            last = previous.last_participation_sim_seconds if previous else None
            return budget_state.sim_seconds_used - (last or 0.0)
        self._rng.shuffle(clients)
        stale = sorted((c for c in clients if age(c) >= threshold), key=age, reverse=True)
        coverage = stale[:min(self.coverage_slots, num_clients)]
        if self.ablation == "no_wait":
            replacement = []
            for target in coverage:
                pool = [c for c in clients if c.compute_time_multiplier == target.compute_time_multiplier
                        and c.client_id not in replacement]
                replacement.append(self._rng.choice(pool).client_id)
            selected = replacement
        else:
            selected = [c.client_id for c in coverage]
        remaining = [c for c in clients if c.client_id not in selected]
        needed = num_clients - len(selected)
        if self.ablation == "no_speed":
            selected += self._rng.sample([c.client_id for c in remaining], needed)
        else:
            selected += super().select(remaining, budget_state, history, needed)
        return selected

    def state_dict(self):
        return {**super().state_dict(), "coverage_slots": self.coverage_slots,
                "wait_fraction": self.wait_fraction, "ablation": self.ablation}

    def load_state_dict(self, state):
        for key in ("coverage_slots", "wait_fraction", "ablation"):
            if state[key] != getattr(self, key):
                raise ValueError("Changed coverage parameters.")
        super().load_state_dict(state)
