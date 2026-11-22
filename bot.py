"""LOTTERY AUTOBET V2.0 — Interactive Telegram Control Panel & Web Dashboard."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import os
from pathlib import Path
import time

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from engine import (
    Store,
    RiskStop,
    MIN_STAKE,
    MAX_STAKE,
    MIN_LIMIT,
    MAX_LIMIT,
    MIN_MAX_BETS,
    MAX_MAX_BETS,
)
from mock_api_client import MockAppsScriptClient
from prediction import Predictor
from strategy import AutoStrategy, StrategyConfig

# ── Bootstrap ────────────────────────────────────────────────────────────────

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
RAW_OWNERS = os.getenv("ALLOWED_CHAT_ID", "").strip()
OWNER_IDS: set[int] = {
    int(x.strip()) for x in RAW_OWNERS.split(",") if x.strip().isdecimal()
}
PRIMARY_OWNER_ID: int | None = next(iter(OWNER_IDS), None)

DB_PATH = Path(os.getenv("DB_PATH", "trx_virtual.sqlite3"))
MOCK_API_URL = os.getenv(
    "MOCK_API_URL",
    "https://script.google.com/macros/s/AKfycbxSeLUqO-H1aL71MdyywdNQ1I2pfEBiUbtNFB9_zomuF6UbWgToWUkO4pMwvDd2Q2rtCQ/exec",
).strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://sixlotteryapi.onrender.com").strip()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

store = Store(DB_PATH)
api_client = MockAppsScriptClient(MOCK_API_URL)
tasks: dict[int, asyncio.Task] = {}
strategies: dict[int, AutoStrategy] = {}
session_meta: dict[int, dict] = {}

# ── Interactive Tutorial Pages (Step 1 to 6) ─────────────────────────────────

GUIDE_PAGES = [
    (
        "🤖 *LOTTERY AUTOBET V2.0 — GUIDE*\n"
        "━━━━━━━━━━━━━━\n"
        "မင်္ဂလာပါ! ဒီ Bot က TRX 1-Min Round တွေမှာ အလိုအလျောက် လောင်းကြေးထိုးပေးသွားမှာ ဖြစ်ပါတယ်။\n\n"
        "📌 *ပါဝင်သော စနစ်များ:*\n"
        "1. Interactive Button Control Panel\n"
        "2. Custom Stake Ladder (`100-300-700-1500`)\n"
        "3. Pattern & AI Signal Strategy\n"
        "4. SL Layer (Wait Mode / Smart Skip)\n"
        "5. Live Chart Web Dashboard\n\n"
        "👇 *Next* ကိုနှိပ်ပြီး ဆက်လေ့လာပါ။"
    ),
    (
        "📚 *အဆင့် ၁ — Strategy ရွေးချယ်နည်း*\n"
        "━━━━━━━━━━━━━━\n"
        "• *AI Signal:* နောက်ဆုံးရလဒ်များကို တွက်ချက်ပြီး Confidence အမြင့်ဆုံးဘက်ကို ထိုးပေးပါမယ်။\n"
        "• *Pattern Mode:* ကိုယ်ကြိုက်တဲ့ Pattern ထည့်နိုင်ပါတယ်။\n"
        "  ဥပမာ: `/setpattern BSSBSB`\n"
        "• *Fixed Side:* BIG သို့မဟုတ် SMALL တစ်ဖက်တည်း စွဲထိုးပါမယ်။"
    ),
    (
        "🎫 *အဆင့် ၂ — Bet Method & Stake Ladder*\n"
        "━━━━━━━━━━━━━━\n"
        "• *Ladder / Martingale:* ရှုံးရင် နောက်တစ်ဆင့် တိုးထိုးပါမယ်။\n"
        "• *Anti-Martingale:* နိုင်ရင် တိုးထိုးပြီး ရှုံးရင် အစပြန်ဆင်းပါမယ်။\n"
        "• *D'Alembert:* ရှုံးရင် 1 Unit တိုး၊ နိုင်ရင် 1 Unit လျှော့ပါမယ်။\n\n"
        "💰 *Custom Ladder ထည့်နည်း:*\n"
        "`/setladder 100-300-700-1600-3600`\n"
        "*(0 ထည့်ထားတဲ့ အဆင့်မှာ Skip လုပ်ပေးပါမယ် ဥပမာ: `0-0-100-300`)*"
    ),
    (
        "🛡️ *အဆင့် ၃ — Risk & SL Layer (Wait Mode)*\n"
        "━━━━━━━━━━━━━━\n"
        "• *Take Profit / Stop Loss:* `/limits 3000 3000 50`\n"
        "• *SL Layer (Smart Wait):* ဆက်တိုက်ရှုံးနေချိန် အရင်းကာကွယ်ရန် ခဏနားပြီး စောင့်ကြည့်ပေးပါမယ်။\n"
        "  ဥပမာ: `/sllayer 3 2` (၃ ပွဲဆက်ရှုံးရင် ၂ ပွဲ မထိုးဘဲ စောင့်မယ်)\n"
        "  ပိတ်ရန်: `/sllayer 0 0`"
    ),
]


# ── Access Control & Helpers ─────────────────────────────────────────────────

def allow(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.id in OWNER_IDS)


async def guard(update: Update) -> bool:
    if not allow(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ Owner-only bot ဖြစ်ပါတယ်။ /id ကိုသုံးပြီး သင့် Chat ID ကိုယူပါ။"
            )
        return False
    store.ensure(update.effective_chat.id)
    return True


def get_strategy(chat_id: int) -> AutoStrategy:
    if chat_id not in strategies:
        a = store.get(chat_id)
        cfg = StrategyConfig(
            enabled=True,
            strategy_type="signal",
            bet_method="ladder",
            min_confidence=int(a.get("min_confidence", 60)),
            fixed_side=a.get("side", "BIG"),
            base_stake=int(a.get("stake", 100)),
        )
        strategies[chat_id] = AutoStrategy(cfg)
    return strategies[chat_id]


def format_duration(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}h {m}m {sec}s"


def main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    a = store.get(chat_id)
    strat = get_strategy(chat_id)
    running = bool(a["active"] and chat_id in tasks and not tasks[chat_id].done())

    toggle_btn = (
        InlineKeyboardButton("🍎 HALT (Stop)", callback_data="act:stop")
        if running
        else InlineKeyboardButton("🍏 DEPLOY (Run)", callback_data="act:run")
    )

    return InlineKeyboardMarkup([
        [toggle_btn, InlineKeyboardButton("📊 Live Chart", web_app=WebAppInfo(url=WEBAPP_URL))],
        [
            InlineKeyboardButton(f"📚 Strat: {strat.config.strategy_type.upper()}", callback_data="cycle:strat"),
            InlineKeyboardButton(f"🎫 Method: {strat.config.bet_method.upper()}", callback_data="cycle:method"),
        ],
        [
            InlineKeyboardButton(f"🎯 Side: {a['side']}", callback_data="cycle:side"),
            InlineKeyboardButton(f"🛡️ SL Wait: {strat.config.sl_wait_trigger}→{strat.config.sl_wait_rounds}", callback_data="cycle:sl"),
        ],
        [
            InlineKeyboardButton("📈 Status", callback_data="act:status"),
            InlineKeyboardButton("📖 Guide (1/4)", callback_data="guide:0"),
        ],
    ])


def guide_keyboard(page: int) -> InlineKeyboardMarkup:
    total = len(GUIDE_PAGES)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"guide:{page - 1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"guide:{page + 1}"))
    return InlineKeyboardMarkup([
        nav,
        [InlineKeyboardButton("✖️ Close Guide", callback_data="guide:close")],
    ])


def render_control_panel(chat_id: int) -> str:
    a = store.get(chat_id)
    stats = store.today(chat_id)
    strat = get_strategy(chat_id)
    running = bool(a["active"] and chat_id in tasks and not tasks[chat_id].done())
    ladder_str = "-".join(str(x) for x in strat.config.stake_ladder)

    return (
        f"🤖 *LOTTERY AUTOBET V2.0*\n"
        f"━━━━━━━━━━━━━━\n"
        f"Status: {'🍏 DEPLOYED (RUNNING)' if running else '🍎 STANDBY (PAUSED)'}\n"
        f"Balance: `{a['balance']:,} Ks` (Virtual)\n"
        f"Today P/L: `{stats['pnl']:+,} Ks` ({stats['count']} bets)\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎮 Strategy: `{strat.config.strategy_type.upper()}` "
        f"({strat.config.pattern if strat.config.strategy_type == 'pattern' else f'Conf ≥ {strat.config.min_confidence}%'})\n"
        f"🎫 Method: `{strat.config.bet_method.upper()}`\n"
        f"💰 Ladder: `{ladder_str}`\n"
        f"🛡️ Risk: TP `{a['take_profit']:,}` | SL `{a['stop_loss']:,}` | Wait `{strat.config.sl_wait_trigger}L/{strat.config.sl_wait_rounds}R`"
    )


# ── Commands ─────────────────────────────────────────────────────────────────

async def identify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        f"Your chat ID: `{update.effective_chat.id}`", parse_mode="Markdown"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    chat_id = update.effective_chat.id
    await update.effective_message.reply_text(
        render_control_panel(chat_id),
        reply_markup=main_menu_keyboard(chat_id),
        parse_mode="Markdown",
    )


async def setladder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    raw = context.args[0] if context.args else ""
    parts = [p.strip() for p in raw.replace(",", "-").split("-") if p.strip()]
    try:
        ladder = [int(x) for x in parts]
        if not ladder or any(x < 0 or x > 100000 for x in ladder):
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            "Usage: `/setladder 100-300-700-1600-3600`\n(0 ထည့်ရင် အဲဒီအဆင့် Skip လုပ်ပါမယ်)",
            parse_mode="Markdown",
        )
        return

    chat_id = update.effective_chat.id
    strat = get_strategy(chat_id)
    strat.config.stake_ladder = ladder
    strat.config.base_stake = next((x for x in ladder if x > 0), 100)
    strat.step_index = 0
    store.update(chat_id, stake=strat.config.base_stake)
    await update.effective_message.reply_text(
        f"💰 Stake Ladder updated → `{'-'.join(map(str, ladder))}`",
        parse_mode="Markdown",
    )


async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    pat = (context.args[0] if context.args else "").upper()
    if not pat or any(c not in ("B", "S") for c in pat):
        await update.effective_message.reply_text(
            "Usage: `/setpattern BSSBSB` (B=BIG, S=SMALL)", parse_mode="Markdown"
        )
        return

    chat_id = update.effective_chat.id
    strat = get_strategy(chat_id)
    strat.config.pattern = pat
    strat.config.strategy_type = "pattern"
    strat.pattern_index = 0
    await update.effective_message.reply_text(
        f"📚 Pattern Strategy active → `{pat}`", parse_mode="Markdown"
    )


async def sllayer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        trig = int(context.args[0])
        wait_r = int(context.args[1])
        if not (0 <= trig <= 10 and 0 <= wait_r <= 10):
            raise ValueError
    except (IndexError, ValueError):
        await update.effective_message.reply_text(
            "Usage: `/sllayer 3 2` (၃ ပွဲဆက်ရှုံးရင် ၂ ပွဲစောင့်)\nပိတ်ရန် `/sllayer 0 0`",
            parse_mode="Markdown",
        )
        return

    strat = get_strategy(update.effective_chat.id)
    strat.config.sl_wait_trigger = trig
    strat.config.sl_wait_rounds = wait_r
    strat.wait_remaining = 0
    await update.effective_message.reply_text(
        f"🛡️ SL Wait Layer → Trigger: `{trig} losses`, Wait: `{wait_r} rounds`",
        parse_mode="Markdown",
    )


async def stake(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        n = int(context.args[0])
        if not MIN_STAKE <= n <= MAX_STAKE:
            raise ValueError
    except (IndexError, ValueError):
        await update.effective_message.reply_text(f"Usage: /stake 100 ({MIN_STAKE}–{MAX_STAKE})")
        return

    chat_id = update.effective_chat.id
    store.update(chat_id, stake=n)
    strat = get_strategy(chat_id)
    strat.config.base_stake = n
    strat.config.stake_ladder = [n, n * 2, n * 4, n * 8, n * 16]
    await update.effective_message.reply_text(f"Fixed base stake → {n:,} Ks")


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
        await update.effective_message.reply_text("Usage: /limits 3000 3000 40")
        return
    store.update(update.effective_chat.id, stop_loss=loss, take_profit=profit, max_daily_bets=maximum)
    await update.effective_message.reply_text(f"Limits → SL {loss:,} | TP {profit:,} | Max {maximum}")


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


async def apihealth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    try:
        res = await api_client.health()
        cur = await api_client.get_current_round()
        await update.effective_message.reply_text(
            f"✅ Mock API Connected ({res.get('status')})\n"
            f"Current Round: `{cur.round_id}` ({cur.status})\nCloses: {cur.closes_at}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        await update.effective_message.reply_text(f"❌ API Error: {exc}")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    items = store.history(update.effective_chat.id, 10)
    if not items:
        await update.effective_message.reply_text("No rounds played yet.")
        return
    lines = ["📊 *LAST 10 ROUNDS*"]
    for r in items:
        lines.append(
            f"#{r['id']} {r['side']}/{r['outcome']} → {'✅' if r['won'] else '❌'} `{r['net']:+,}`"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    if context.args != ["CONFIRM"]:
        await update.effective_message.reply_text("Reset လုပ်ရန် `/stop` ပြီး `/reset CONFIRM` ရိုက်ပါ။", parse_mode="Markdown")
        return
    chat_id = update.effective_chat.id
    if tasks.get(chat_id) and not tasks[chat_id].done():
        await update.effective_message.reply_text("Please stop the bot first.")
        return
    store.reset_demo(chat_id)
    get_strategy(chat_id).reset_session()
    await update.effective_message.reply_text("🔄 Ledger reset to 100,000 Ks.")


# ── Session Lifecycle (Deploy / Abort Report) ────────────────────────────────

async def start_bot_session(chat_id: int, app: Application) -> None:
    existing = tasks.get(chat_id)
    if existing and not existing.done():
        return

    a = store.get(chat_id)
    strat = get_strategy(chat_id)
    strat.reset_session()
    session_meta[chat_id] = {
        "start_time": time.time(),
        "start_balance": a["balance"],
        "bets": 0,
        "wins": 0,
        "losses": 0,
    }

    store.update(chat_id, active=1)
    tasks[chat_id] = app.create_task(loop(chat_id, app))

    ladder_str = ", ".join(str(x) for x in strat.config.stake_ladder)
    await app.bot.send_message(
        chat_id,
        f"🍏 *BOT DEPLOYED*\n"
        f"💫 Balance: Virtual • `{a['balance']:,} Ks`\n"
        f"━━━━━━━━━━━━━━\n"
        f"💫 Game: `TRX_1M` • Big/Small\n"
        f"💫 Strategy: `{strat.config.strategy_type.upper()}`\n"
        f"💫 Betting: `{strat.config.bet_method.upper()}`\n"
        f"━━━━━━━━━━━━━━\n"
        f"💫 Bet Amount: `{ladder_str} Ks`\n"
        f"💫 Profit Target: `{a['take_profit']:,} Ks`\n"
        f"💫 Stop Loss: `{a['stop_loss']:,} Ks`",
        parse_mode="Markdown",
    )


async def stop_bot_session(chat_id: int, app: Application, stop_reason: str = "Manual Halt") -> None:
    store.update(chat_id, active=0)
    t = tasks.get(chat_id)
    if t and not t.done():
        t.cancel()

    a = store.get(chat_id)
    strat = get_strategy(chat_id)
    meta = session_meta.pop(chat_id, None)
    if meta:
        profit = a["balance"] - meta["start_balance"]
        runtime = format_duration(time.time() - meta["start_time"])
        await app.bot.send_message(
            chat_id,
            f"🍎 *BOT ABORTED* ({stop_reason})\n"
            f"━━━━━━━━━━━━━━\n"
            f"💳 Final Balance: `{a['balance']:,} Ks`\n"
            f"🏆 Session Profit: `{profit:+,} Ks`\n\n"
            f"📊 *Session Summary*\n"
            f"🔸 Total Bets: `{meta['bets']}`\n"
            f"✅ Wins: `{meta['wins']}`\n"
            f"❌ Losses: `{meta['losses']}`\n"
            f"📈 Max Win Streak: `{strat.max_win_streak}`\n"
            f"📉 Max Loss Streak: `{strat.max_loss_streak}`\n\n"
            f"⏰ Runtime: `{runtime}`",
            parse_mode="Markdown",
        )


async def run_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update):
        await start_bot_session(update.effective_chat.id, context.application)


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update):
        await stop_bot_session(update.effective_chat.id, context.application, "User Stopped")


# ── Inline Button Callbacks ──────────────────────────────────────────────────

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not allow(update):
        if query:
            await query.answer("⛔ Owner only", show_alert=True)
        return

    await query.answer()
    chat_id = update.effective_chat.id
    store.ensure(chat_id)
    data = query.data or ""
    strat = get_strategy(chat_id)

    if data == "act:run":
        await start_bot_session(chat_id, context.application)
    elif data == "act:stop":
        await stop_bot_session(chat_id, context.application, "Button Halt")
    elif data == "cycle:strat":
        order = ["signal", "pattern", "fixed"]
        nxt = order[(order.index(strat.config.strategy_type) + 1) % len(order)]
        strat.config.strategy_type = nxt
    elif data == "cycle:method":
        order = ["ladder", "anti_martingale", "dalembert"]
        nxt = order[(order.index(strat.config.bet_method) + 1) % len(order)]
        strat.config.bet_method = nxt
        strat.step_index = 0
    elif data == "cycle:side":
        a = store.get(chat_id)
        nxt = "SMALL" if a["side"] == "BIG" else "BIG"
        store.update(chat_id, side=nxt)
        strat.config.fixed_side = nxt
    elif data == "cycle:sl":
        presets = [(0, 0), (2, 1), (3, 2), (4, 3)]
        cur = (strat.config.sl_wait_trigger, strat.config.sl_wait_rounds)
        nxt = presets[(presets.index(cur) + 1) % len(presets)] if cur in presets else (3, 2)
        strat.config.sl_wait_trigger, strat.config.sl_wait_rounds = nxt
        strat.wait_remaining = 0
    elif data.startswith("guide:"):
        arg = data.split(":", 1)[1]
        if arg == "close":
            await query.edit_message_text(
                render_control_panel(chat_id),
                reply_markup=main_menu_keyboard(chat_id),
                parse_mode="Markdown",
            )
            return
        page = int(arg)
        await query.edit_message_text(
            f"{GUIDE_PAGES[page]}\n\n*Step {page + 1}/{len(GUIDE_PAGES)}*",
            reply_markup=guide_keyboard(page),
            parse_mode="Markdown",
        )
        return

    # Refresh main control panel
    try:
        await query.edit_message_text(
            render_control_panel(chat_id),
            reply_markup=main_menu_keyboard(chat_id),
            parse_mode="Markdown",
        )
    except Exception:
        pass


# ── Core 1-Minute Synced API Loop ────────────────────────────────────────────

def _seconds_until_close(closes_at_iso: str) -> float:
    try:
        closes_dt = datetime.fromisoformat(closes_at_iso)
        now_dt = datetime.now(closes_dt.tzinfo)
        diff = (closes_dt - now_dt).total_seconds()
        return max(1.0, min(diff + 1.5, 65.0))
    except Exception:
        return 60.0


async def loop(chat_id: int, app: Application) -> None:
    last_played_round_id: str | None = None

    try:
        while store.get(chat_id)["active"]:
            try:
                cur_round = await api_client.get_current_round()
            except Exception as exc:
                logger.warning("API fetch error: %s", exc)
                await asyncio.sleep(5)
                continue

            if cur_round.status != "open" or cur_round.round_id == last_played_round_id:
                await asyncio.sleep(2)
                continue

            round_id = cur_round.round_id
            wait_sec = _seconds_until_close(cur_round.closes_at)

            a = store.get(chat_id)
            strat = get_strategy(chat_id)
            recent = store.recent_outcomes(chat_id, 20)
            sig = Predictor(a.get("pred_mode", "mixed")).generate(recent)

            decision = strat.decide(sig, a["balance"])
            if not decision.should_bet:
                await app.bot.send_message(
                    chat_id,
                    f"⏭ *SKIP* Round `{round_id}`\n{decision.reason}",
                    parse_mode="Markdown",
                )
                last_played_round_id = round_id
                await asyncio.sleep(wait_sec)
                continue

            use_side = decision.side
            use_stake = decision.stake
            reason = decision.reason

            await app.bot.send_message(
                chat_id,
                f"⏳ Issue `{round_id}` OPEN\n"
                f"🎯 Bet: *{use_side}* × `{use_stake:,} Ks`\n"
                f"📌 {reason} · ({int(wait_sec)}s)",
                parse_mode="Markdown",
            )

            await asyncio.sleep(wait_sec)
            if not store.get(chat_id)["active"]:
                break

            outcome = None
            for _ in range(4):
                try:
                    await api_client.get_current_round()
                    res_round = await api_client.get_result(round_id)
                    if res_round.status == "settled" and res_round.result:
                        outcome = res_round.result
                        break
                except Exception as exc:
                    logger.warning("Settle check error: %s", exc)
                await asyncio.sleep(2)

            if not outcome:
                last_played_round_id = round_id
                continue

            try:
                r = store.virtual_round(
                    chat_id,
                    outcome=outcome,
                    round_id=round_id,
                    side=use_side,
                    stake=use_stake,
                    signal_side=sig.side,
                    signal_conf=sig.confidence,
                    signal_reason=reason,
                )
            except RiskStop as exc:
                await stop_bot_session(chat_id, app, str(exc))
                break
            except Exception:
                logger.exception("Engine error")
                await stop_bot_session(chat_id, app, "Engine Error")
                break

            last_played_round_id = round_id
            strat.on_result(r["won"])

            if chat_id in session_meta:
                session_meta[chat_id]["bets"] += 1
                if r["won"]:
                    session_meta[chat_id]["wins"] += 1
                else:
                    session_meta[chat_id]["losses"] += 1

            badge = "✅ WIN" if r["won"] else "❌ LOSS"
            await app.bot.send_message(
                chat_id,
                f"🎲 Issue `{round_id}` — *{badge}*\n"
                f"Bet: {r['side']} (`{r['stake']:,}`) | Result: *{r['outcome']}*\n"
                f"P/L: `{r['net']:+,} Ks` | Bal: `{r['balance']:,} Ks`\n"
                f"Today: `{r['daily_pnl']:+,} Ks` ({r['daily_count']} bets)",
                parse_mode="Markdown",
            )

    except asyncio.CancelledError:
        pass
    finally:
        store.update(chat_id, active=0)
        current = asyncio.current_task()
        if tasks.get(chat_id) is current:
            tasks.pop(chat_id, None)


# ── Web Dashboard Server ─────────────────────────────────────────────────────

async def _start_health_server(app: Application) -> None:
    from aiohttp import web

    async def handle_index(request):
        html_path = Path("index.html")
        if html_path.exists():
            return web.FileResponse(html_path)
        return web.Response(text="OK - LOTTERY AUTOBET V2.0")

    async def handle_health(request):
        return web.Response(text="OK")

    async def handle_state(request):
        if not PRIMARY_OWNER_ID:
            return web.json_response({"error": "ALLOWED_CHAT_ID not set"}, status=400)
        chat_id = PRIMARY_OWNER_ID
        store.ensure(chat_id)
        a = store.get(chat_id)
        stats = store.today(chat_id)
        strat = get_strategy(chat_id)
        recent = store.recent_outcomes(chat_id, 20)
        sig = Predictor(a.get("pred_mode", "mixed")).generate(recent)
        running = bool(a["active"] and chat_id in tasks and not tasks[chat_id].done())

        round_id = "---"
        seconds_left = 60
        try:
            cur = await api_client.get_current_round()
            round_id = cur.round_id
            seconds_left = int(_seconds_until_close(cur.closes_at))
        except Exception:
            pass

        return web.json_response({
            "running": running,
            "balance": a["balance"],
            "daily_pnl": stats["pnl"],
            "round_id": round_id,
            "seconds_left": seconds_left,
            "strategy_mode": f"{strat.config.strategy_type} · {strat.config.bet_method}",
            "signal": {
                "side": sig.side,
                "confidence": sig.confidence,
                "reason": sig.reason,
            },
            "history": store.history(chat_id, 15),
        })

    async def handle_control(request):
        if not PRIMARY_OWNER_ID:
            return web.json_response({"error": "ALLOWED_CHAT_ID not set"}, status=400)
        chat_id = PRIMARY_OWNER_ID
        store.ensure(chat_id)
        body = await request.json()
        act = body.get("action")
        if act == "run":
            await start_bot_session(chat_id, app)
        elif act == "stop":
            await stop_bot_session(chat_id, app, "Web Dashboard Halt")
        return web.json_response({"ok": True})

    web_app = web.Application()
    web_app.router.add_get("/", handle_index)
    web_app.router.add_get("/health", handle_health)
    web_app.router.add_get("/api/state", handle_state)
    web_app.router.add_post("/api/control", handle_control)

    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("V2.0 Web App & Health server listening on port %s", port)


def main() -> None:
    if not TOKEN:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN")

    store.pause_all_at_restart()

    async def post_init(application: Application) -> None:
        await _start_health_server(application)

    app = Application.builder().token(TOKEN).post_init(post_init).build()

    handlers = (
        ("start", start),
        ("help", start),
        ("menu", start),
        ("id", identify),
        ("apihealth", apihealth),
        ("stake", stake),
        ("setladder", setladder),
        ("setpattern", setpattern),
        ("sllayer", sllayer),
        ("side", side),
        ("limits", limits),
        ("minconf", minconf),
        ("run", run_cmd),
        ("stop", stop_cmd),
        ("history", history),
        ("reset", reset),
    )
    for name, callback in handlers:
        app.add_handler(CommandHandler(name, callback))

    app.add_handler(CallbackQueryHandler(on_callback))

    logger.info("LOTTERY AUTOBET V2.0 starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()