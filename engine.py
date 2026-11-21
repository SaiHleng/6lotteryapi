"""Virtual TRX-like Big/Small fixed-stake simulation engine.

IMPORTANT
---------
This module does **not** implement the rules, draw feed, payouts, or betting
API of any real lottery operator (including 6Lottery).

All outcomes are generated with a fair 50/50 random choice purely for
software testing, risk-limit experiments and Telegram UX development.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo
import secrets
import sqlite3
from typing import Any

# ── Configuration constants ──────────────────────────────────────────────────

TZ = ZoneInfo("Asia/Yangon")

# Hypothetical gross payout multiplier used only for virtual accounting.
# This is NOT an official 6Lottery (or any other operator) rate.
VIRTUAL_GROSS_PAYOUT = Decimal("1.90")

DEFAULT_BALANCE = 100_000
DEFAULT_STAKE = 100
DEFAULT_SIDE = "BIG"
DEFAULT_INTERVAL_SEC = 60
DEFAULT_STOP_LOSS = 3_000
DEFAULT_TAKE_PROFIT = 3_000
DEFAULT_MAX_DAILY_BETS = 40

MIN_STAKE = 100
MAX_STAKE = 10_000
MIN_INTERVAL = 15
MAX_INTERVAL = 3_600
MIN_LIMIT = 100
MAX_LIMIT = 100_000
MIN_MAX_BETS = 1
MAX_MAX_BETS = 500


class RiskStop(Exception):
    """Raised when the virtual session has reached a safety limit."""


def now_local() -> datetime:
    return datetime.now(TZ)


class Store:
    """SQLite-backed virtual ledger + risk controls + strategy settings."""

    def __init__(self, db_path: str | Path = "trx_virtual.sqlite3") -> None:
        self.db_path = str(db_path)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    chat_id         INTEGER PRIMARY KEY,
                    balance         INTEGER NOT NULL DEFAULT 100000,
                    stake           INTEGER NOT NULL DEFAULT 100,
                    side            TEXT    NOT NULL DEFAULT 'BIG',
                    interval_sec    INTEGER NOT NULL DEFAULT 60,
                    stop_loss       INTEGER NOT NULL DEFAULT 3000,
                    take_profit     INTEGER NOT NULL DEFAULT 3000,
                    max_daily_bets  INTEGER NOT NULL DEFAULT 40,
                    active          INTEGER NOT NULL DEFAULT 0,
                    -- strategy settings
                    strategy_enabled INTEGER NOT NULL DEFAULT 0,
                    strategy_mode    TEXT    NOT NULL DEFAULT 'signal',
                    min_confidence  INTEGER NOT NULL DEFAULT 65,
                    pred_mode       TEXT    NOT NULL DEFAULT 'mixed'
                );

                CREATE TABLE IF NOT EXISTS bets (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id         INTEGER NOT NULL,
                    played_at       TEXT    NOT NULL,
                    play_date       TEXT    NOT NULL,
                    stake           INTEGER NOT NULL,
                    side            TEXT    NOT NULL,
                    outcome         TEXT    NOT NULL,
                    won             INTEGER NOT NULL,
                    net             INTEGER NOT NULL,
                    balance_after   INTEGER NOT NULL,
                    signal_side     TEXT,
                    signal_conf     INTEGER,
                    signal_reason   TEXT
                );

                CREATE INDEX IF NOT EXISTS bets_by_user_day
                    ON bets(chat_id, play_date);
                """
            )
            # Lightweight migration for existing DBs
            cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
            migrations = [
                ("strategy_enabled", "INTEGER NOT NULL DEFAULT 0"),
                ("strategy_mode", "TEXT NOT NULL DEFAULT 'signal'"),
                ("min_confidence", "INTEGER NOT NULL DEFAULT 65"),
                ("pred_mode", "TEXT NOT NULL DEFAULT 'mixed'"),
            ]
            for name, typedef in migrations:
                if name not in cols:
                    conn.execute(f"ALTER TABLE accounts ADD COLUMN {name} {typedef}")

            bet_cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)").fetchall()}
            for name, typedef in [
                ("signal_side", "TEXT"),
                ("signal_conf", "INTEGER"),
                ("signal_reason", "TEXT"),
            ]:
                if name not in bet_cols:
                    conn.execute(f"ALTER TABLE bets ADD COLUMN {name} {typedef}")

    def ensure(self, chat_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR IGNORE INTO accounts(chat_id) VALUES (?)",
                (chat_id,),
            )

    def get(self, chat_id: int) -> dict[str, Any]:
        self.ensure(chat_id)
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE chat_id=?", (chat_id,)
            ).fetchone()
            return dict(row)

    def update(self, chat_id: int, **values: int | str) -> None:
        allowed = {
            "balance", "stake", "side", "interval_sec",
            "stop_loss", "take_profit", "max_daily_bets", "active",
            "strategy_enabled", "strategy_mode", "min_confidence", "pred_mode",
        }
        if not values or not set(values).issubset(allowed):
            raise ValueError(f"Unsupported setting(s): {set(values) - allowed}")
        self.ensure(chat_id)
        fields = ", ".join(f"{name}=?" for name in values)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"UPDATE accounts SET {fields} WHERE chat_id=?",
                (*values.values(), chat_id),
            )

    def pause_all_at_restart(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE accounts SET active=0")

    def today(self, chat_id: int, date: str | None = None) -> dict[str, Any]:
        day = date or now_local().date().isoformat()
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count, COALESCE(SUM(net), 0) AS pnl
                FROM bets
                WHERE chat_id=? AND play_date=?
                """,
                (chat_id, day),
            ).fetchone()
            return dict(row)

    def history(self, chat_id: int, limit: int = 8) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT * FROM bets
                WHERE chat_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def recent_outcomes(self, chat_id: int, limit: int = 20) -> list[str]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT outcome FROM bets
                WHERE chat_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
            return [r["outcome"] for r in reversed(rows)]

    def reset_demo(self, chat_id: int) -> None:
        self.ensure(chat_id)
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM bets WHERE chat_id=?", (chat_id,))
            conn.execute(
                "UPDATE accounts SET balance=?, active=0, strategy_enabled=0 WHERE chat_id=?",
                (DEFAULT_BALANCE, chat_id),
            )

    def virtual_round(
        self,
        chat_id: int,
        *,
        side: str | None = None,
        stake: int | None = None,
        signal_side: str | None = None,
        signal_conf: int | None = None,
        signal_reason: str | None = None,
    ) -> dict[str, Any]:
        """Run exactly one *fictional* round, atomically with risk checks."""
        current = now_local()
        day = current.date().isoformat()

        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                "SELECT * FROM accounts WHERE chat_id=?", (chat_id,)
            ).fetchone()
            if row is None:
                raise RiskStop("No account. Use /start first.")

            a = dict(row)
            if not a["active"]:
                raise RiskStop("Bot is paused.")

            use_side = (side or a["side"]).upper()
            use_stake = stake if stake is not None else a["stake"]

            stats = conn.execute(
                """
                SELECT COUNT(*) AS count, COALESCE(SUM(net), 0) AS pnl
                FROM bets
                WHERE chat_id=? AND play_date=?
                """,
                (chat_id, day),
            ).fetchone()
            count, pnl = stats["count"], stats["pnl"]

            reason: str | None = None
            if count >= a["max_daily_bets"]:
                reason = "Daily maximum number of simulated bets reached."
            elif pnl >= a["take_profit"]:
                reason = "Daily virtual take-profit reached."
            elif pnl <= -a["stop_loss"]:
                reason = "Daily virtual stop-loss reached."
            elif pnl - use_stake < -a["stop_loss"]:
                reason = "Next stake could exceed the remaining daily loss budget."
            elif a["balance"] < use_stake:
                reason = "Insufficient virtual balance."

            if reason:
                conn.execute(
                    "UPDATE accounts SET active=0 WHERE chat_id=?", (chat_id,)
                )
                raise RiskStop(reason)

            # Purely fictional 50/50 outcome — NOT an official TRX / 6Lottery result.
            outcome = secrets.choice(("BIG", "SMALL"))
            won = use_side == outcome

            if won:
                net = int(
                    (Decimal(use_stake) * (VIRTUAL_GROSS_PAYOUT - 1)).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
            else:
                net = -use_stake

            new_balance = a["balance"] + net

            conn.execute(
                "UPDATE accounts SET balance=? WHERE chat_id=?",
                (new_balance, chat_id),
            )
            conn.execute(
                """
                INSERT INTO bets
                    (chat_id, played_at, play_date, stake, side, outcome, won, net,
                     balance_after, signal_side, signal_conf, signal_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    current.isoformat(timespec="seconds"),
                    day,
                    use_stake,
                    use_side,
                    outcome,
                    int(won),
                    net,
                    new_balance,
                    signal_side,
                    signal_conf,
                    signal_reason,
                ),
            )

            return {
                "side": use_side,
                "outcome": outcome,
                "won": won,
                "stake": use_stake,
                "net": net,
                "balance": new_balance,
                "daily_pnl": pnl + net,
                "daily_count": count + 1,
                "signal_side": signal_side,
                "signal_conf": signal_conf,
                "signal_reason": signal_reason,
            }
