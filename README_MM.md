# TRX Fixed Bet Telegram Bot — VIRTUAL Mode

**အရေးကြီး:**  
6Lottery အကောင့်နှင့် ချိတ်ဆက်ထားခြင်း မရှိပါ။  
အမှန်တကယ် Bet မတင်ပါ။ ငွေလွှဲမှု မရှိပါ။  

သတ်မှတ်ထားသည့် 60-second default interval သည် TRX/6Lottery ရဲ့ အမှန်တကယ် round အချိန်နှင့် Sync လုပ်ထားခြင်း မဟုတ်ပါ။  
BIG/SMALL ရလဒ်များကို 50/50 random generator ဖြင့်သာ တုပထားပါသည်။  
အနိုင်ရလျှင် Gross Payout = 1.90x သတ်မှတ်မှုသည် hypothetical test value သာဖြစ်ပြီး 6Lottery payout မဟုတ်ပါ။

---

## ပါဝင်သောဖိုင်များ

| ဖိုင် | အကြောင်းအရာ |
|------|-------------|
| `bot.py` | Telegram commands နှင့် simulation loop |
| `engine.py` | SQLite virtual ledger + risk limits |
| `authorized_api_template.py` | တရားဝင် API ရမှသာ အသုံးပြုရန် **placeholder interface** |
| `.env.example` | Bot token နှင့် owner chat ID |
| `requirements.txt` | Python packages |
| `tests/test_virtual.py` | Unit tests |
| `README.md` | English documentation |
| `LICENSE` | MIT License |

---

## PC / VPS မှာ စတင်နည်း

Python 3.10+ သုံးပါ။ Project folder ထဲမှာ terminal ဖွင့်ပါ။

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env
# Windows: copy .env.example .env
```

1. Telegram ရဲ့ official [@BotFather](https://t.me/BotFather) မှာ `/newbot` ဖန်တီးပြီး token ယူပါ။
2. `.env` ထဲက `TELEGRAM_BOT_TOKEN` မှာ ထည့်ပါ။ **Bot token ကို လူမပေးပါနှင့်။**
3. Bot စဖွင့်ရန် `python bot.py` လုပ်ပါ။ Telegram မှာ Bot ကို `/id` ပို့ပါ။
4. ပြန်လာသော Chat ID ကို `.env` ထဲ `ALLOWED_CHAT_ID=123456789` အဖြစ် ထည့်ပါ။ Bot ကို restart လုပ်ပါ။
5. Telegram မှာ `/start`, `/status`, `/stake 100`, `/side big`, `/limits 3000 3000 40`, `/interval 60`, `/run` ပို့ပါ။ ရပ်ရန် `/stop`။

`.env` မပြင်ရသေးလျှင် `/id` မှအပ command များကို ပိတ်ထားသည်။  
Chat ID တစ်ခုတည်းသာ အသုံးပြုနိုင်သည်။  
VPS ပေါ်မှာ run ရန် Process Manager သုံးနိုင်သော်လည်း process restart ပြီးလျှင် safety အတွက် simulation သည် paused ဖြစ်နေမည်။

---

## Android / Termux

```bash
pkg update
pkg install python
# project ဖိုင်များကို device ထဲသို့ ဖြည်ကာ Termux working directory ထဲသို့ ကူးပါ
pip install -r requirements.txt
cp .env.example .env
nano .env
python bot.py
```

အမြဲတမ်း online ဖြစ်ရန် phone ပေါ်တွင် battery optimization နှင့် process kill ပြဿနာတွေ ရှိနိုင်သဖြင့် VPS သို့မဟုတ် always-on host သုံးရန် စဉ်းစားပါ။

---

## Commands

| Command | လုပ်ဆောင်ချက် |
|---------|---------------|
| `/id` | မိမိ Telegram Chat ID ရှာရန် |
| `/start` / `/help` | Help |
| `/status` | Balance / daily P/L / settings |
| `/stake 100` | Fixed stake (100–10,000 virtual units) |
| `/side big` သို့မဟုတ် `/side small` | Fixed side |
| `/interval 60` | Virtual round seconds (15–3600) |
| `/limits 3000 3000 40` | Stop loss / take profit / max daily bets |
| `/run` / `/stop` | Start / stop virtual simulation |
| `/history` | နောက်ဆုံး ၈ ကြိမ် |
| `/reset CONFIRM` | Demo ledger ဖျက်ပြီး balance ပြန်စ |

---

## API / URL error — `code:11, msg:"Url is not exist"`

အဆိုပါ error message သည် API route/URL မရှိကြောင်းဆိုနိုင်ပါသည်။  
အဲဒါတစ်ခုတည်းဖြင့် token invalid ဖြစ်ကြောင်း မပြောနိုင်ပါ။  

စစ်ရန်မှာ:
1. Request URL: root domain vs `/api/...` path, spelling, trailing slash
2. HTTP method: GET vs POST, expected headers / content-type
3. Documentation version, operator's authorized API access
4. Full HTTP status နှင့် redacted response body  

**token / cookies / credentials မမျှဝေပါနှင့်**

6Lottery ၏ official order API မရသေးသဖြင့် domain သို့မဟုတ် path ကို ခန့်မှန်းပြီး login request, endpoint scraping, access bypass မလုပ်ပါနှင့်။  
Third-party results API သည် bet-placement API မဟုတ်ပါ။

---

## Developer test

```bash
python -m unittest discover -s tests -v
```

---

## Future Authorized Live Integration (Not Implemented)

Operator ၏ ရေးသားပေးထားသော API permission, endpoint docs, staging credentials, game/round definitions, odds, settlement rules, legal review လိုပါသည်။  

ထိုအခြေအနေမှာ `authorized_api_template.py` interface ကို အခြေခံ၍ သီးခြား live client ရေးနိုင်သည်။  

**Live ကို ဤ build မှာ ဖွင့်၍ မရပါ။**
