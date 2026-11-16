"""Public research dashboard. No endpoint or broker adapter can place orders."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .brokers import KiteBroker
from .demo import candles
from .strategy import backtest, enrich

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="NIFTY Pro Trader — Research Terminal")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/healthz")
def health():
    return {"ok": True}


@app.get("/api/status")
def status():
    return {
        "mode": "RESEARCH", "orders_enabled": False, "auto_trading": False,
        "broker": "Zerodha Kite read-only scaffold", "data_source": "SYNTHETIC / DEMO",
        "broker_configured": bool(os.getenv("KITE_API_KEY") and os.getenv("KITE_ACCESS_TOKEN")),
        "note": "Configured credentials do not enable trading or a live feed.",
    }


@app.get("/api/market")
def market():
    return {
        "source": "SYNTHETIC", "timestamp": None, "spot": None, "trend": "WAIT",
        "renko": None, "vwap": None, "oi": None, "gex": None, "dex": None,
        "fii": None, "dii": None, "strike": None, "premium": None,
        "signal": "NO TRADE", "tradeable": False,
        "reason": "No validated live quote, option chain, liquidity or protective exits.",
    }


@app.get("/api/candles")
def chart():
    d = enrich(candles())
    cols = ["time", "open", "high", "low", "close", "volume", "ema9", "ema21", "vwap", "signal"]
    return {"source": "SYNTHETIC", "timeframe": "5m", "candles": d[cols].round(2).where(d[cols].notna(), None).to_dict(orient="records")}


@app.get("/api/ideas")
def ideas():
    d = enrich(candles())
    signals = d[d.signal != "WAIT"].tail(8)
    return {"source": "SYNTHETIC", "tradeable": False, "ideas": [
        {"time": str(r.time), "direction": r.signal, "spot_reference": round(float(r.close), 2),
         "rationale": "Closed-candle breakout + EMA + VWAP + volume filter",
         "strike": None, "entry": None, "stop": None, "target": None}
        for r in signals.itertuples()
    ]}


@app.get("/api/backtest")
def research():
    return backtest(candles())


@app.post("/api/orders")
def order():
    raise HTTPException(423, "LIVE_EXECUTION_LOCKED: No order placement is implemented.")


@app.get("/api/broker/check")
def broker_check(x_admin_token: str | None = Header(default=None)):
    secret = os.getenv("ADMIN_TOKEN", "")
    if not secret or secret == "replace-with-a-long-random-secret" or not secrets.compare_digest(x_admin_token or "", secret):
        raise HTTPException(401, "Admin token required")
    try:
        profile = KiteBroker(os.getenv("KITE_API_KEY", ""), os.getenv("KITE_ACCESS_TOKEN", "")).profile()
        return {"connected": True, "user_id": profile.get("user_id"), "broker": "Kite"}
    except Exception as exc:
        raise HTTPException(503, f"Kite connection failed: {type(exc).__name__}") from None
