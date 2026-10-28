"""DDPG consensus steering: PyTorch actor-critic, online in-episode learning.

The actor maps the MDP state [consensus, mean deviation, max deviation,
last feedback] to a continuous feedback intensity in [0, 1]. The critic
estimates Q(s, a); both learn during the run from a seeded replay buffer
with Adam updates, Bellman targets from target nets, and soft updates.
Reward = 0.5 * consensus gain - 0.3 * round penalty
         + 0.2 * opinion retention, so steering pulls outliers toward
the threshold while the retention term protects dissent and the round
penalty keeps emergency decisions fast.

Deterministic per seed (torch.manual_seed + seeded batch sampling), so
replays reproduce exactly. No trained weights are shipped: the policy in
the demo is the product of this in-episode learning, honestly labeled.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Tuple

import numpy as np
import torch
import torch.nn as nn

STATE_DIM = 4


class Actor(nn.Module):
    def __init__(self, hidden: int = 32) -> None:
        super().__init__()
        self.fc1 = nn.Linear(STATE_DIM, hidden)
        self.fc2 = nn.Linear(hidden, 1)

    def forward(self, s: torch.Tensor) -> torch.Tensor:
        return self.fc2(torch.relu(self.fc1(s)))


class Critic(nn.Module):
    def __init__(self, hidden: int = 32) -> None:
        super().__init__()
        self.fc1 = nn.Linear(STATE_DIM + 1, hidden)
        self.fc2 = nn.Linear(hidden, 1)

    def forward(self, s: torch.Tensor, a: torch.Tensor) -> torch.Tensor:
        return self.fc2(torch.relu(self.fc1(torch.cat([s, a], dim=1))))


@dataclass
class DDPGSteerer:
    seed: int = 7
    actor_lr: float = 1e-3
    critic_lr: float = 1e-3
    tau: float = 0.05
    gamma: float = 0.9
    w1: float = 0.5
    w2: float = 0.3
    w3: float = 0.2
    buffer_size: int = 256
    batch_size: int = 32
    hidden: int = 32
    actor: Actor = field(init=False)
    actor_target: Actor = field(init=False)
    critic: Critic = field(init=False)
    critic_target: Critic = field(init=False)
    buffer: Deque = field(init=False)

    def __post_init__(self) -> None:
        torch.manual_seed(self.seed)
        self.actor = Actor(self.hidden)
        self.actor_target = Actor(self.hidden)
        self.actor_target.load_state_dict(self.actor.state_dict())
        self.critic = Critic(self.hidden)
        self.critic_target = Critic(self.hidden)
        self.critic_target.load_state_dict(self.critic.state_dict())
        self.actor_opt = torch.optim.Adam(self.actor.parameters(),
                                          lr=self.actor_lr)
        self.critic_opt = torch.optim.Adam(self.critic.parameters(),
                                           lr=self.critic_lr)
        self.buffer = deque(maxlen=self.buffer_size)

    def act(self, state: np.ndarray) -> float:
        with torch.no_grad():
            s = torch.tensor(state, dtype=torch.float32).unsqueeze(0)
            raw = self.actor(s)
            return float(torch.sigmoid(raw).item())

    def reward(self, prev_consensus: float, new_consensus: float,
               opinion_shift: float, step: int = 0,
               max_steps: int = 12) -> float:
        gain = new_consensus - prev_consensus
        round_penalty = step / max(1, max_steps)
        retention = 1.0 - opinion_shift
        return (self.w1 * gain - self.w2 * round_penalty
                + self.w3 * retention)

    def observe(self, s: np.ndarray, a: float, r: float,
                s2: np.ndarray) -> None:
        self.buffer.append((s.copy(), a, r, s2.copy()))
        if len(self.buffer) >= self.batch_size:
            self._update()

    def _batch(self) -> Tuple[torch.Tensor, ...]:
        idx = torch.randperm(len(self.buffer))[: self.batch_size].tolist()
        s = torch.tensor(np.stack([self.buffer[i][0] for i in idx]),
                         dtype=torch.float32)
        a = torch.tensor([[self.buffer[i][1]] for i in idx],
                         dtype=torch.float32)
        r = torch.tensor([[self.buffer[i][2]] for i in idx],
                         dtype=torch.float32)
        s2 = torch.tensor(np.stack([self.buffer[i][3] for i in idx]),
                          dtype=torch.float32)
        return s, a, r, s2

    def _update(self) -> None:
        s, a, r, s2 = self._batch()
        with torch.no_grad():
            a2 = torch.sigmoid(self.actor_target(s2))
            target = r + self.gamma * self.critic_target(s2, a2)
        q = self.critic(s, a)
        critic_loss = torch.nn.functional.mse_loss(q, target)
        self.critic_opt.zero_grad()
        critic_loss.backward()
        self.critic_opt.step()
        a_pred = torch.sigmoid(self.actor(s))
        actor_loss = -self.critic(s, a_pred).mean()
        self.actor_opt.zero_grad()
        actor_loss.backward()
        self.actor_opt.step()
        with torch.no_grad():
            for tp, sp in zip(self.actor_target.parameters(),
                              self.actor.parameters()):
                tp.copy_(self.tau * sp + (1.0 - self.tau) * tp)
            for tp, sp in zip(self.critic_target.parameters(),
                              self.critic.parameters()):
                tp.copy_(self.tau * sp + (1.0 - self.tau) * tp)
