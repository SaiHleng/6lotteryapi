"""Virtual prediction signal generator.

This module produces *demo* signals only.
It does NOT use real market data, real TRX draws, or any live feed.
Signals are generated from recent virtual outcomes + simple heuristics
so the Telegram UX feels closer to a real prediction tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import secrets

Side = Literal["BIG", "SMALL"]


@dataclass(frozen=True)
class Signal:
    side: Side
    confidence: int          # 50 – 95
    reason: str
    source: str = "virtual"  # always virtual in this build


class Predictor:
    """Simple virtual signal engine.

    Strategies available:
    - random          : pure 50/50 with confidence 50-65
    - momentum        : follow the last N outcomes
    - mean_reversion  : bet against the last streak
    - mixed           : combination (default)
    """

    def __init__(self, mode: str = "mixed") -> None:
        self.mode = mode if mode in ("random", "momentum", "mean_reversion", "mixed") else "mixed"

    def generate(self, recent_outcomes: list[str]) -> Signal:
        """Generate a signal from the last virtual outcomes."""
        if self.mode == "random" or len(recent_outcomes) < 3:
            return self._random_signal()

        if self.mode == "momentum":
            return self._momentum(recent_outcomes)
        if self.mode == "mean_reversion":
            return self._mean_reversion(recent_outcomes)

        # mixed
        if secrets.randbelow(100) < 45:
            return self._momentum(recent_outcomes)
        if secrets.randbelow(100) < 50:
            return self._mean_reversion(recent_outcomes)
        return self._random_signal()

    def _random_signal(self) -> Signal:
        side: Side = secrets.choice(("BIG", "SMALL"))
        conf = 50 + secrets.randbelow(16)  # 50-65
        return Signal(side=side, confidence=conf, reason="Virtual random baseline")

    def _momentum(self, recent: list[str]) -> Signal:
        last = recent[-1]
        streak = 1
        for o in reversed(recent[:-1]):
            if o == last:
                streak += 1
            else:
                break

        conf = min(55 + streak * 8, 88)
        reason = f"Momentum · last {streak} = {last}"
        return Signal(side=last, confidence=conf, reason=reason)  # type: ignore

    def _mean_reversion(self, recent: list[str]) -> Signal:
        last = recent[-1]
        opposite: Side = "SMALL" if last == "BIG" else "BIG"
        streak = 1
        for o in reversed(recent[:-1]):
            if o == last:
                streak += 1
            else:
                break

        conf = min(58 + streak * 7, 90)
        reason = f"Mean-reversion · streak {streak} of {last}"
        return Signal(side=opposite, confidence=conf, reason=reason)
