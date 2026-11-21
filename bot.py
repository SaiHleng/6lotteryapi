"""Telegram control panel for a virtual TRX-like fixed-bet simulator.

There is NO live betting function and NO unofficial 6Lottery API access.
This bot exists only for testing risk controls, prediction UX, auto-strategy
logic and ledger behaviour.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from engine import (
    Store,
    RiskStop,
    MIN_STAKE,
    MAX_STAKE,
    MIN_INTERVAL,
    MAX_INTERVAL,
    MIN_LIMIT,
    MAX_LIMIT,
    MIN_MAX_BETS,
    MAX_MAX_BETS,
)
from prediction import Predictor
from strategy import AutoStrategy, StrategyConfig

# ── Bootstrap ────────────────────────────────────────────────────────────────

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()
DB_PATH = Path(os.getenv("DB_PATH", "trx_virtual.sqlite3"))

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

store = Store(DB_PATH)
tasks: dict[int, asyncio.Task] = {}
strategies: dict[int, AutoStrategy] = {}

HELP = """🧪 TRX Fixed Bet — VIRTUAL SIMULATOR (v1.2)

ဒီ Bot သည် 6Lottery နှင့် မချိတ်ထားပါ။ ငွေအစစ်မသုံးပါ။
ရလဒ်အားလုံးသည် Virtual 50/50 ဖြစ်သည်။

📌 အခြေခံ
/start /help — ဒီစာ
/id — Chat ID
/status — Balance + settings
/stake 100 — Fixed stake
/side big|small — Fixed side
/interval 60 — Round interval (sec)
/limits 3000 3000 40 — Loss / Profit / Max bets
/run — Auto simulation စတင်
/stop — ရပ်
/history — နောက်ဆုံး ၈ ကြိမ်
/reset CONFIRM — Ledger ပြန်စ

📡 Prediction Signal
/signal — နောက်တစ်ကြိမ် signal ကြည့်
/predmode mixed|momentum|mean_reversion|random

🤖 Auto-Strategy
/strategy on|off
/strategymode signal|fixed|martingale
/minconf 65 — Signal confidence အနည်းဆုံး
/strategyinfo — လက်ရှိ strategy အခြေအနေ

⚠️ အားလုံး Virtual ဖြစ်သည်။ တကယ့်ပိုက်ဆံ မသုံးပါ။"""


# ── Access control ───────────────────────────────────────────────────────────

def allow(update: Update) -> bool:
    chat = update.effective_chat
    return bool(
        OWNER_ID
        and OWNER_ID.isdecimal()
        and chat
        and chat.id == int(OWNER_ID)
    )


async def guard(update: Update) -> bool:
    if not allow(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ Owner-only bot ဖြစ်ပါတယ်။ /id ကိုသုံးပြီး သင့် Chat ID ကိုဖတ်ပါ။ "
                "ပြီးမှ .env ထဲက ALLOWED_CHAT_ID မှာ ထည့်ပြီး Bot ကို restart လုပ်ပါ။"
            )
        return False
    store.ensure(update.effective_chat.id)
    return True


def get_strategy(chat_id: int) -> AutoStrategy:
    if chat_id not in strategies:
        a = store.get(chat_id)
        cfg = StrategyConfig(
            enabled=bool(a.get("strategy_enabled", 0)),
            mode=a.get("strategy_mode", "signal"),
            min_confidence=int(a.get("min_confidence", 65)),
            fixed_side=a.get("side", "BIG"),
            base_stake=int(a.get("stake", 100)),
        )
        strategies[chat_id] = AutoStrategy(cfg)
    return strategies[chat_id]


# ── Commands ─────────────────────────────────────────────────────────────────

async def identify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        f"Your chat ID: `{update.effective_chat.id}`\n"
        "ဒီ ID ကို .env ထဲက ALLOWED_CHAT_ID မှာ ထည့်ပါ။",
        parse_mode="Markdown",
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update):
        await update.effective_message.reply_text(HELP)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return

    chat_id = update.effective_chat.id
    a = store.get(chat_id)
    stats = store.today(chat_id)
    running = bool(
        a["active"] and chat_id in tasks and not tasks[chat_id].done()
    )
    strat = get_strategy(chat_id)

    await update.effective_message.reply_text(
        "🧪 VIRTUAL TRX BOT — "
        + ("RUNNING ▶️" if running else "PAUSED ⏹")
        + "\n"
        f"Balance: {a['balance']:,} virtual units\n"
        f"Stake: {a['stake']:,} | Side: {a['side']}\n"
        f"Interval: {a['interval_sec']} sec\n"
        f"Today bets: {stats['count']}/{a['max_daily_bets']}\n"
        f"Today P/L: {stats['pnl']:+,}\n"
        f"Stop-loss: {a['stop_loss']:,} | Take-profit: {a['take_profit']:,}\n"
        f"──────────────\n"
        f"Strategy: {'ON' if strat.config.enabled else 'OFF'} "
        f"({strat.config.mode})\n"
        f"Min confidence: {strat.config.min_confidence}%\n"
        f"Pred mode: {a.get('pred_mode', 'mixed')}\n"
        "Payout: hypothetical 1.90x (virtual only)"
    )


async def stake(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        n = int(context.args[0])
        if not MIN_STAKE <= n <= MAX_STAKE:
            raise ValueError
    except (IndexError, ValueError):
        await update.effective_message.reply_text(
            f"Usage: /stake 100 ({MIN_STAKE}–{MAX_STAKE})"
        )
        return

    chat_id = update.effective_chat.id
    store.update(chat_id, stake=n)
    get_strategy(chat_id).config.base_stake = n
    await update.effective_message.reply_text(f"Fixed stake → {n:,} VIRTUAL")


async def side(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    pick = (context.args[0] if context.args else "").upper()
    if pick not in ("BIG", "SMALL"):
        await update.effective_message.reply_text("Usage: /side big | /side small")
        return

    chat_id = update.effective_chat.id
    store.update(chat_id, side=pick)
    get_strategy(chat_id).config.fixed_side = pick
    await update.effective_message.reply_text(f"Fixed side → {pick}")


async def interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        n = int(context.args[0])
        if not MIN_INTERVAL <= n <= MAX_INTERVAL:
            raise ValueError
    except (IndexError, ValueError):
        await update.effective_message.reply_text(
            f"Usage: /interval 60 ({MIN_INTERVAL}–{MAX_INTERVAL})"
        )
        return

    store.update(update.effective_chat.id, interval_sec=n)
    await update.effective_message.reply_text(f"Interval → {n} seconds")


async def limits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        loss, profit, maximum = map(int, context.args)
        if not (
            MIN_LIMIT <= loss <= MAX_LIMIT
            and MIN_LIMIT <= profit <= MAX_LIMIT
            and MIN_MAX_BETS <= maximum <= MAX_MAX_BETS
        ):
            raise ValueError
    except (ValueError, IndexError):
        await update.effective_message.reply_text(
            "Usage: /limits 3000 3000 40"
        )
        return

    store.update(
        update.effective_chat.id,
        stop_loss=loss,
        take_profit=profit,
        max_daily_bets=maximum,
    )
    await update.effective_message.reply_text(
        f"Limits → loss {loss:,} | profit {profit:,} | bets {maximum}"
    )


# ── Prediction ───────────────────────────────────────────────────────────────

async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return

    chat_id = update.effective_chat.id
    a = store.get(chat_id)
    recent = store.recent_outcomes(chat_id, 20)
    predictor = Predictor(a.get("pred_mode", "mixed"))
    sig = predictor.generate(recent)

    bar = "█" * (sig.confidence // 10) + "░" * (10 - sig.confidence // 10)
    await update.effective_message.reply_text(
        f"📡 VIRTUAL SIGNAL\n"
        f"Side: *{sig.side}*\n"
        f"Confidence: {sig.confidence}%  [{bar}]\n"
        f"Reason: {sig.reason}\n"
        f"──────────────\n"
        f"⚠️ ဒါသည် Virtual signal သာဖြစ်သည်။ တကယ့်ရလဒ် မဟုတ်ပါ။",
        parse_mode="Markdown",
    )


async def predmode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    mode = (context.args[0] if context.args else "").lower()
    if mode not in ("mixed", "momentum", "mean_reversion", "random"):
        await update.effective_message.reply_text(
            "Usage: /predmode mixed|momentum|mean_reversion|random"
        )
        return

    store.update(update.effective_chat.id, pred_mode=mode)
    await update.effective_message.reply_text(f"Prediction mode → {mode}")


# ── Auto-Strategy ────────────────────────────────────────────────────────────

async def strategy_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    arg = (context.args[0] if context.args else "").lower()
    if arg not in ("on", "off"):
        await update.effective_message.reply_text("Usage: /strategy on | /strategy off")
        return

    chat_id = update.effective_chat.id
    enabled = arg == "on"
    store.update(chat_id, strategy_enabled=1 if enabled else 0)
    strat = get_strategy(chat_id)
    strat.config.enabled = enabled
    if enabled:
        strat.reset_streak()

    await update.effective_message.reply_text(
        f"Auto-Strategy → {'ON ✅' if enabled else 'OFF ⏹'}"
    )


async def strategymode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    mode = (context.args[0] if context.args else "").lower()
    if mode not in ("signal", "fixed", "martingale"):
        await update.effective_message.reply_text(
            "Usage: /strategymode signal|fixed|martingale"
        )
        return

    chat_id = update.effective_chat.id
    store.update(chat_id, strategy_mode=mode)
    get_strategy(chat_id).config.mode = mode
    await update.effective_message.reply_text(f"Strategy mode → {mode}")


async def minconf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        n = int(context.args[0])
        if not 50 <= n <= 95:
            raise ValueError
    except (IndexError, ValueError):
        await update.effective_message.reply_text("Usage: /minconf 65 (50–95)")
        return

    chat_id = update.effective_chat.id
    store.update(chat_id, min_confidence=n)
    get_strategy(chat_id).config.min_confidence = n
    await update.effective_message.reply_text(f"Min confidence → {n}%")


async def strategyinfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return

    chat_id = update.effective_chat.id
    a = store.get(chat_id)
    strat = get_strategy(chat_id)
    cfg = strat.config

    await update.effective_message.reply_text(
        "🤖 AUTO-STRATEGY INFO\n"
        f"Enabled: {'YES' if cfg.enabled else 'NO'}\n"
        f"Mode: {cfg.mode}\n"
        f"Min confidence: {cfg.min_confidence}%\n"
        f"Base stake: {cfg.base_stake:,}\n"
        f"Fixed side: {cfg.fixed_side}\n"
        f"Consecutive losses: {strat._consecutive_losses}\n"
        f"Current martingale stake: {strat._current_stake:,}\n"
        f"Pred mode: {a.get('pred_mode', 'mixed')}"
    )


# ── Core loop ────────────────────────────────────────────────────────────────

async def loop(chat_id: int, app: Application) -> None:
    try:
        while store.get(chat_id)["active"]:
            a = store.get(chat_id)
            strat = get_strategy(chat_id)
            recent = store.recent_outcomes(chat_id, 20)
            predictor = Predictor(a.get("pred_mode", "mixed"))
            sig = predictor.generate(recent)

            # Decide whether / how to bet
            if strat.config.enabled:
                decision = strat.decide(sig, a["balance"])
                if not decision.should_bet:
                    await app.bot.send_message(
                        chat_id,
                        f"⏭ SKIP\n{decision.reason}\n"
                        f"Signal was: {sig.side} ({sig.confidence}%)",
                    )
                    await asyncio.sleep(a["interval_sec"])
                    continue
                use_side = decision.side
                use_stake = decision.stake
                reason = decision.reason
            else:
                use_side = a["side"]
                use_stake = a["stake"]
                reason = "Manual fixed settings"

            try:
                r = store.virtual_round(
                    chat_id,
                    side=use_side,
                    stake=use_stake,
                    signal_side=sig.side,
                    signal_conf=sig.confidence,
                    signal_reason=sig.reason,
                )
            except RiskStop as exc:
                store.update(chat_id, active=0)
                await app.bot.send_message(chat_id, "🛑 AUTO-STOP: " + str(exc))
                break
            except Exception:
                logger.exception("Virtual engine error")
                store.update(chat_id, active=0)
                await app.bot.send_message(
                    chat_id, "🛑 Simulation error; bot paused."
                )
                break

            # Update strategy state
            strat.on_result(r["won"])

            result = "✅ SIM WIN" if r["won"] else "❌ SIM LOSS"
            await app.bot.send_message(
                chat_id,
                f"🧪 {result} (FAKE DRAW)\n"
                f"Bet: {r['side']} × {r['stake']:,}\n"
                f"Outcome: {r['outcome']}\n"
                f"P/L: {r['net']:+,} | Balance: {r['balance']:,}\n"
                f"Today: {r['daily_pnl']:+,} / {r['daily_count']} bets\n"
                f"──────────────\n"
                f"Signal: {sig.side} ({sig.confidence}%) · {sig.reason}\n"
                f"Strategy: {reason}",
            )
            await asyncio.sleep(store.get(chat_id)["interval_sec"])
    except asyncio.CancelledError:
        pass
    finally:
        store.update(chat_id, active=0)
        current = asyncio.current_task()
        if tasks.get(chat_id) is current:
            tasks.pop(chat_id, None)


async def run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return

    chat_id = update.effective_chat.id
    existing = tasks.get(chat_id)
    if existing and not existing.done():
        await update.effective_message.reply_text(
            "Already running. /stop to pause."
        )
        return

    store.update(chat_id, active=1)
    tasks[chat_id] = context.application.create_task(
        loop(chat_id, context.application)
    )
    await update.effective_message.reply_text(
        "▶️ Virtual auto simulation started.\n"
        "NO real money · NO live API.\n"
        "/stop to pause."
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return

    chat_id = update.effective_chat.id
    store.update(chat_id, active=0)
    task = tasks.get(chat_id)
    if task and not task.done():
        task.cancel()
    await update.effective_message.reply_text("⏹ Simulation paused.")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return

    items = store.history(update.effective_chat.id)
    if not items:
        await update.effective_message.reply_text("No simulated rounds yet.")
        return

    lines = ["🧪 LAST SIMULATED ROUNDS"]
    for r in items:
        sig = ""
        if r.get("signal_side"):
            sig = f" | sig:{r['signal_side']}({r.get('signal_conf', '?')}%)"
        lines.append(
            f"#{r['id']} {r['side']}/{r['outcome']} "
            f"{'WIN' if r['won'] else 'LOSS'} {r['net']:+,}{sig}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return

    if context.args != ["CONFIRM"]:
        await update.effective_message.reply_text(
            "Reset လုပ်ရန် /stop ပြီး /reset CONFIRM ရိုက်ပါ။"
        )
        return

    chat_id = update.effective_chat.id
    if tasks.get(chat_id) and not tasks[chat_id].done():
        await update.effective_message.reply_text("Please /stop first.")
        return

    store.reset_demo(chat_id)
    if chat_id in strategies:
        strategies[chat_id].reset_streak()
    await update.effective_message.reply_text(
        "Virtual ledger reset to 100,000. History cleared."
    )


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    if not TOKEN:
        raise SystemExit(
            "Missing TELEGRAM_BOT_TOKEN. Copy .env.example → .env"
        )

    if not OWNER_ID or not OWNER_ID.isdecimal():
        print("ALLOWED_CHAT_ID not set — only /id will work.")

    store.pause_all_at_restart()

    app = Application.builder().token(TOKEN).build()

    handlers = (
        ("start", start),
        ("help", start),
        ("id", identify),
        ("status", status),
        ("stake", stake),
        ("side", side),
        ("interval", interval),
        ("limits", limits),
        ("run", run),
        ("stop", stop),
        ("history", history),
        ("reset", reset),
        # prediction
        ("signal", signal_cmd),
        ("predmode", predmode),
        # strategy
        ("strategy", strategy_toggle),
        ("strategymode", strategymode),
        ("minconf", minconf),
        ("strategyinfo", strategyinfo),
    )
    for name, callback in handlers:
        app.add_handler(CommandHandler(name, callback))

    logger.info("Virtual TRX bot v1.2 starting (signal + strategy)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
