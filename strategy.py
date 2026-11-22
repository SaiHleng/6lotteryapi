"""V2.0 Advanced Auto-Strategy Engine (Custom Ladder, Pattern, D'Alembert, SL Wait Layer)."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    enabled: bool = True
    strategy_type: str = "signal"       # signal | pattern | fixed
    pattern: str = "BSSBSB"             # e.g. BSSBSB
    bet_method: str = "ladder"          # ladder | martingale | anti_martingale | dalembert
    stake_ladder: list[int] = field(default_factory=lambda: [100, 300, 700, 1500, 3200])
    min_confidence: int = 60
    fixed_side: Side = "BIG"
    base_stake: int = 100
    max_stake: int = 50000
    sl_wait_trigger: int = 0            # 0 = off; e.g. 3 = pause after 3 losses
    sl_wait_rounds: int = 2             # how many rounds to skip in wait mode


class AutoStrategy:
    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()
        self.step_index: int = 0
        self.pattern_index: int = 0
        self.dalembert_unit: int = 1
        self.consecutive_losses: int = 0
        self.consecutive_wins: int = 0
        self.max_win_streak: int = 0
        self.max_loss_streak: int = 0
        self.wait_remaining: int = 0

    def reset_session(self) -> None:
        self.step_index = 0
        self.pattern_index = 0
        self.dalembert_unit = 1
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.max_win_streak = 0
        self.max_loss_streak = 0
        self.wait_remaining = 0

    def current_stake(self) -> int:
        cfg = self.config
        ladder = cfg.stake_ladder or [cfg.base_stake]
        if cfg.bet_method in ("ladder", "martingale", "anti_martingale"):
            idx = min(self.step_index, len(ladder) - 1)
            return ladder[idx]
        if cfg.bet_method == "dalembert":
            return cfg.base_stake * max(1, self.dalembert_unit)
        return cfg.base_stake

    def on_result(self, won: bool) -> None:
        cfg = self.config
        ladder_len = len(cfg.stake_ladder) if cfg.stake_ladder else 1

        if won:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.max_win_streak = max(self.max_win_streak, self.consecutive_wins)

            if cfg.bet_method in ("ladder", "martingale"):
                self.step_index = 0
            elif cfg.bet_method == "anti_martingale":
                self.step_index = (self.step_index + 1) % ladder_len
            elif cfg.bet_method == "dalembert":
                self.dalembert_unit = max(1, self.dalembert_unit - 1)
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            self.max_loss_streak = max(self.max_loss_streak, self.consecutive_losses)

            if cfg.bet_method in ("ladder", "martingale"):
                if self.step_index + 1 < ladder_len:
                    self.step_index += 1
                else:
                    self.step_index = 0  # reset after full ladder
            elif cfg.bet_method == "anti_martingale":
                self.step_index = 0
            elif cfg.bet_method == "dalembert":
                self.dalembert_unit += 1

            # Trigger SL Wait Layer if configured
            if cfg.sl_wait_trigger > 0 and self.consecutive_losses >= cfg.sl_wait_trigger:
                self.wait_remaining = cfg.sl_wait_rounds

    def decide(self, signal: Signal | None, balance: int) -> StrategyDecision:
        cfg = self.config

        # 1. Check SL Layer (Wait Mode)
        if self.wait_remaining > 0:
            self.wait_remaining -= 1
            return StrategyDecision(
                False, None, None,
                f"🛡️ SL Wait Layer active ({self.wait_remaining} rounds left)"
            )

        # 2. Determine Side
        if cfg.strategy_type == "fixed":
            side = cfg.fixed_side
            s_reason = f"Fixed · {side}"
        elif cfg.strategy_type == "pattern":
            pat = (cfg.pattern or "BS").upper()
            ch = pat[self.pattern_index % len(pat)]
            self.pattern_index += 1
            side = "BIG" if ch == "B" else "SMALL"
            s_reason = f"Pattern ({pat}) · Step {self.pattern_index}"
        else:  # signal
            if signal is None:
                return StrategyDecision(False, None, None, "No signal")
            if signal.confidence < cfg.min_confidence:
                return StrategyDecision(
                    False, None, None,
                    f"Smart Skip · Conf {signal.confidence}% < {cfg.min_confidence}%"
                )
            side = signal.side
            s_reason = f"AI Signal ({signal.confidence}%)"

        # 3. Determine Stake (0 in ladder means intentional Skip step)
        raw_stake = self.current_stake()
        if raw_stake == 0:
            self.step_index = (self.step_index + 1) % max(1, len(cfg.stake_ladder))
            return StrategyDecision(False, None, None, "⏭ Ladder 0-Step Skip")

        stake = min(raw_stake, cfg.max_stake, balance)
        if stake < 100 or balance < stake:
            return StrategyDecision(False, None, None, "Insufficient balance")

        return StrategyDecision(
            True, side, stake,
            f"{s_reason} | {cfg.bet_method.upper()} (Step {self.step_index + 1})"
        )
