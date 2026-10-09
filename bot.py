import os, time, logging, asyncio
import requests
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("futures-bot")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
BYBIT = "https://api.bybit.com"
WEEX = "https://api-contract.weex.com"

WATCHLIST = [
"BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","BNBUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT",
"LINKUSDT","DOTUSDT","LTCUSDT","BCHUSDT","TRXUSDT","TONUSDT","SUIUSDT","APTUSDT",
"NEARUSDT","OPUSDT","ARBUSDT","INJUSDT","UNIUSDT","AAVEUSDT","ETCUSDT","FILUSDT",
"ATOMUSDT","ICPUSDT","FETUSDT","RENDERUSDT","WIFUSDT","PEPEUSDT","SHIBUSDT","SEIUSDT",
"TIAUSDT","MKRUSDT","CRVUSDT","ENAUSDT","WLDUSDT","JUPUSDT","ORDIUSDT","POLUSDT",
"XLMUSDT","HBARUSDT","ONDOUSDT","TAOUSDT","KASUSDT","ARUSDT","GALAUSDT","SANDUSDT",
"MANAUSDT","1000PEPEUSDT"]

BYBIT_INTERVAL = {"15m":"15","1h":"60","4h":"240","1d":"D","1w":"W"}
WEEX_INTERVAL = {"15m":"15m","1h":"1h","4h":"4h","1d":"1d","1w":"1w"}

def candles(exchange, symbol, tf="1h", limit=160):
    if exchange == "Bybit":
        r = requests.get(BYBIT + "/v5/market/kline",
            params={"category":"linear","symbol":symbol,"interval":BYBIT_INTERVAL[tf],"limit":limit}, timeout=15)
        r.raise_for_status()
        j = r.json()
        if j.get("retCode") != 0:
            raise RuntimeError(j.get("retMsg","Bybit API error"))
        rows = list(reversed(j.get("result",{}).get("list",[])))
        if not rows: raise RuntimeError("No candles returned")
        df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume","turnover"])
        df = df[["time","open","high","low","close","volume"]]
    else:
        r = requests.get(WEEX + "/capi/v3/market/klines",
            params={"symbol":symbol,"interval":WEEX_INTERVAL[tf],"limit":limit}, timeout=15)
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows,list) or not rows: raise RuntimeError("No WEEX candles returned")
        df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume","close_time","quote_volume","trades","taker_base","taker_quote"])
        df = df[["time","open","high","low","close","volume"]]
    for c in ["open","high","low","close","volume"]: df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    if len(df) < 60: raise RuntimeError("Not enough candles")
    return df

def fmt(x):
    if x is None: return "—"
    if abs(x) >= 1000: return f"{x:,.2f}"
    if abs(x) >= 1: return f"{x:.4f}"
    return f"{x:.8f}".rstrip("0").rstrip(".")

def analyze(exchange, symbol, tf="1h"):
    df = candles(exchange,symbol,tf)
    c = df.close
    e20 = c.ewm(span=20,adjust=False).mean()
    e50 = c.ewm(span=50,adjust=False).mean()
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi_s = 100 - 100/(1+rs)
    prev = c.shift(1)
    tr = pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    atr_s = tr.rolling(14).mean()
    price=float(c.iloc[-1]); ema20=float(e20.iloc[-1]); ema50=float(e50.iloc[-1])
    rsi=float(rsi_s.iloc[-1]) if pd.notna(rsi_s.iloc[-1]) else 50
    atr=float(atr_s.iloc[-1]) if pd.notna(atr_s.iloc[-1]) else price*0.01
    direction="WAIT"
    if ema20 > ema50 and price > ema20 and 50 <= rsi <= 68: direction="LONG"
    elif ema20 < ema50 and price < ema20 and 32 <= rsi <= 50: direction="SHORT"
    risk=max(atr*1.5, price*0.002)
    if direction=="LONG": sl=price-risk; tps=[price+risk,price+2*risk,price+3*risk]
    elif direction=="SHORT": sl=price+risk; tps=[price-risk,price-2*risk,price-3*risk]
    else: sl=None; tps=[]
    return dict(exchange=exchange,symbol=symbol,tf=tf,price=price,ema20=ema20,ema50=ema50,rsi=rsi,direction=direction,sl=sl,tps=tps)

def render(a):
    icon="🟢" if a["direction"]=="LONG" else ("🔴" if a["direction"]=="SHORT" else "⚪")
    lines=[f"{icon} *{a['symbol']} — {a['direction']}*",
      f"Exchange: *{a['exchange']} USDT perpetual* | TF: `{a['tf']}`",
      f"Latest candle close: `{fmt(a['price'])}`",
      f"RSI(14): `{a['rsi']:.1f}`",
      f"EMA20 / EMA50: `{fmt(a['ema20'])}` / `{fmt(a['ema50'])}`"]
    if a["direction"]!="WAIT":
        lines += [f"Illustrative entry: `{fmt(a['price'])}`",f"Stop-loss: `{fmt(a['sl'])}`",
          f"TP1 (1R): `{fmt(a['tps'][0])}`",f"TP2 (2R): `{fmt(a['tps'][1])}`",f"TP3 (3R): `{fmt(a['tps'][2])}`"]
    lines += ["","_Experimental rule-based analysis, not financial advice. No verified win rate. Confirm data and costs before trading._"]
    return "\n".join(lines)

def menu():
    return InlineKeyboardMarkup([
      [InlineKeyboardButton("🔎 Scan 50 pairs",callback_data="scan")],
      [InlineKeyboardButton("₿ BTC analysis",callback_data="btc")],
      [InlineKeyboardButton("📈 LONG setups",callback_data="long"),InlineKeyboardButton("📉 SHORT setups",callback_data="short")],
      [InlineKeyboardButton("❔ Help",callback_data="help")]])

async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("*Crypto Futures Signal Lab*\\n\\nWEEX + Bybit USDT perpetual public market data.\\nUse /scan, /btc, /long, /short, /check BTCUSDT Bybit, /help.\\n\\nNo exchange login or trade permissions are used.",parse_mode="Markdown",reply_markup=menu())

async def help_cmd(update, context):
    await update.message.reply_text("/scan — scan watchlist on both exchanges\\n/btc — BTC analysis on both\\n/long — qualifying LONG setups\\n/short — qualifying SHORT setups\\n/check BTCUSDT Bybit — one pair\\n\\nThe first version does not place trades or run scheduled alerts. Signals have no verified accuracy.")

async def btc_cmd(update, context):
    for ex in ["Bybit","WEEX"]:
        try: await update.message.reply_text(render(analyze(ex,"BTCUSDT")),parse_mode="Markdown")
        except Exception as e: await update.message.reply_text(f"{ex} BTC data error: {str(e)[:150]}")

async def check_cmd(update, context):
    if len(context.args)<2:
        await update.message.reply_text("Use: /check BTCUSDT Bybit  (or /check BTCUSDT WEEX)"); return
    ex="Bybit" if context.args[1].lower().startswith("by") else "WEEX"
    try: await update.message.reply_text(render(analyze(ex,context.args[0].upper())),parse_mode="Markdown")
    except Exception as e: await update.message.reply_text(f"Data error: {str(e)[:180]}")

async def scan(update, context, wanted=None):
    await update.message.reply_text("Scanning public futures candles. This may take a minute…")
    results=[]; errors=0
    for ex in ["Bybit","WEEX"]:
        for sym in WATCHLIST:
            try:
                a=analyze(ex,sym)
                if a["direction"]!="WAIT" and (wanted is None or a["direction"]==wanted): results.append(a)
            except Exception: errors += 1
            await asyncio.sleep(0.06)
    if not results:
        await update.message.reply_text(f"No qualifying {wanted or 'LONG/SHORT'} setups in this scan. Failed/unsupported requests: {errors}. Avoid forcing a trade.")
        return
    await update.message.reply_text(f"Found {len(results)} potential setups; showing up to 12.")
    for a in results[:12]:
        await update.message.reply_text(render(a),parse_mode="Markdown")
        await asyncio.sleep(0.05)

async def scan_cmd(update, context): await scan(update,context)
async def long_cmd(update, context): await scan(update,context,"LONG")
async def short_cmd(update, context): await scan(update,context,"SHORT")

async def buttons(update, context):
    q=update.callback_query; await q.answer()
    if q.data=="help": await q.message.reply_text("/scan, /btc, /long, /short, /check BTCUSDT Bybit")
    elif q.data=="btc":
        for ex in ["Bybit","WEEX"]:
            try: await q.message.reply_text(render(analyze(ex,"BTCUSDT")),parse_mode="Markdown")
            except Exception as e: await q.message.reply_text(f"{ex} BTC data error: {str(e)[:150]}")
    elif q.data=="scan": await scan(q,context)
    elif q.data=="long": await scan(q,context,"LONG")
    elif q.data=="short": await scan(q,context,"SHORT")

def main():
    if not TOKEN: raise RuntimeError("Set TELEGRAM_BOT_TOKEN as a private hosting environment variable.")
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("help",help_cmd))
    app.add_handler(CommandHandler("scan",scan_cmd)); app.add_handler(CommandHandler("btc",btc_cmd))
    app.add_handler(CommandHandler("long",long_cmd)); app.add_handler(CommandHandler("short",short_cmd))
    app.add_handler(CommandHandler("check",check_cmd)); app.add_handler(CallbackQueryHandler(buttons))
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
