"""Virtual auto-strategy rules.

All strategies operate only on the virtual ledger.
No real money or live API calls are made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from prediction import Signal

Side = Literal["BIG", "SMALL"]


@dataclass
class StrategyDecision:
    should_bet: bool
    side: Side | None
    stake: int | None
    reason: str


@dataclass
class StrategyConfig:
    """User-configurable auto-strategy settings."""

    enabled: bool = False
    mode: str = "signal"          # signal | fixed | martingale
    min_confidence: int = 65      # only bet when signal confidence >= this
    fixed_side: Side = "BIG"
    base_stake: int = 100
    max_stake: int = 2000
    martingale_multiplier: float = 2.0
    max_consecutive_losses: int = 4


class AutoStrategy:
    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()
        self._consecutive_losses = 0
        self._current_stake = self.config.base_stake

    def reset_streak(self) -> None:
        self._consecutive_losses = 0
        self._current_stake = self.config.base_stake

    def on_result(self, won: bool) -> None:
        if won:
            self._consecutive_losses = 0
            self._current_stake = self.config.base_stake
        else:
            self._consecutive_losses += 1
            if self.config.mode == "martingale":
                next_stake = int(self._current_stake * self.config.martingale_multiplier)
                self._current_stake = min(next_stake, self.config.max_stake)

    def decide(self, signal: Signal | None, balance: int) -> StrategyDecision:
        cfg = self.config

        if not cfg.enabled:
            return StrategyDecision(False, None, None, "Auto-strategy disabled")

        if self._consecutive_losses >= cfg.max_consecutive_losses:
            return StrategyDecision(
                False, None, None,
                f"Max consecutive losses ({cfg.max_consecutive_losses}) reached"
            )

        # Determine side
        if cfg.mode == "fixed":
            side = cfg.fixed_side
            reason = f"Fixed side · {side}"
        elif cfg.mode == "signal":
            if signal is None:
                return StrategyDecision(False, None, None, "No signal available")
            if signal.confidence < cfg.min_confidence:
                return StrategyDecision(
                    False, None, None,
                    f"Signal confidence {signal.confidence}% < min {cfg.min_confidence}%"
                )
            side = signal.side
            reason = f"Signal · {side} ({signal.confidence}%) · {signal.reason}"
        elif cfg.mode == "martingale":
            side = cfg.fixed_side
            reason = f"Martingale · {side} · streak losses={self._consecutive_losses}"
        else:
            return StrategyDecision(False, None, None, f"Unknown mode: {cfg.mode}")

        # Determine stake
        if cfg.mode == "martingale":
            stake = self._current_stake
        else:
            stake = cfg.base_stake

        stake = max(100, min(stake, cfg.max_stake, balance))

        if balance < stake:
            return StrategyDecision(False, None, None, "Insufficient virtual balance")

        return StrategyDecision(True, side, stake, reason)
