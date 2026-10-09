# Crypto Futures Signal Lab — Telegram bot

Initial Telegram-only bot for public WEEX and Bybit USDT perpetual futures candle data.

## Commands
- `/start` — main menu
- `/scan` — scan a curated watchlist of up to 50 symbols on both exchanges
- `/btc` — BTC analysis on both exchanges
- `/long` and `/short` — show qualifying setups
- `/check BTCUSDT Bybit` or `/check BTCUSDT WEEX`
- `/help` — help

## Deploy
Upload `bot.py`, `requirements.txt`, and `render.yaml` to a **separate** GitHub repository. In a hosting provider that supports always-on Python background workers, create a worker:
- Build: `pip install -r requirements.txt`
- Start: `python bot.py`
- Secret environment variable: `TELEGRAM_BOT_TOKEN` = your BotFather token

Do not paste the token into the source code or commit it to GitHub. If it is exposed, revoke it in BotFather and generate a new one. Check the host's current price and whether the worker runs continuously; sleeping services cannot respond while asleep.

## Limitations
This is an experimental baseline: EMA20/EMA50 trend plus RSI filter, with ATR-derived illustrative SL/TP. It is not AI and has no verified win rate. The watchlist is curated, not dynamically ranked; unsupported symbols are skipped. This version does **not** include a backtesting engine, automatic scheduled alert loop, or order execution. Public APIs can fail or rate-limit. Test and paper-trade before risking money. Futures can cause rapid losses and liquidation.
