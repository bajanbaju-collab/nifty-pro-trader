"""Read-only browser terminal. No endpoint can place orders."""
import os
import secrets
from datetime import datetime, time, timedelta
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .brokers import KiteBroker, exchange_request_token, login_url
from .demo import candles
from .strategy import backtest, enrich

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
IST = ZoneInfo("Asia/Kolkata")
SESSION_COOKIE = "nifty_kite_session"
_sessions: dict[str, dict] = {}
_sessions_lock = Lock()
app = FastAPI(title="NIFTY Pro Trader — Research Terminal")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def privacy_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def _configured() -> bool:
    return bool(os.getenv("KITE_API_KEY") and os.getenv("KITE_API_SECRET"))


def _session(request: Request) -> dict:
    sid = request.cookies.get(SESSION_COOKIE, "")
    with _sessions_lock:
        session = _sessions.get(sid)
        if session and session.get("expires_at") and datetime.now(IST) >= session["expires_at"]:
            session.pop("access_token", None)
            session.pop("user_id", None)
        return session.copy() if session else {}


def _connected(request: Request) -> bool:
    return bool(_configured() and _session(request).get("access_token"))


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/healthz")
def health():
    return {"ok": True}


@app.get("/api/status")
def status(request: Request):
    connected = _connected(request)
    return {
        "mode": "RESEARCH", "orders_enabled": False, "auto_trading": False,
        "broker": "Zerodha Kite", "data_source": "Kite read-only snapshot" if connected else "UNAVAILABLE",
        "broker_configured": _configured(), "broker_connected": connected,
        "user_id": _session(request).get("user_id") if connected else None,
        "note": "Connecting Kite never enables trading. No orders can be placed.",
    }


@app.get("/api/kite/status")
def kite_status(request: Request):
    return status(request)


@app.get("/api/kite/connect")
def kite_connect(request: Request):
    if not _configured():
        raise HTTPException(503, "Kite Connect app keys are not configured on the server")
    sid = request.cookies.get(SESSION_COOKIE)
    nonce = secrets.token_urlsafe(32)
    with _sessions_lock:
        if not sid or sid not in _sessions:
            sid = secrets.token_urlsafe(32)
        _sessions[sid] = {"nonce": nonce, "pending_until": datetime.now(IST) + timedelta(minutes=10)}
    response = RedirectResponse(login_url(os.environ["KITE_API_KEY"], nonce), status_code=303)
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, secure=True, samesite="lax", max_age=86400)
    return response


@app.get("/api/kite/callback")
def kite_callback(request: Request, request_token: str | None = None):
    sid = request.cookies.get(SESSION_COOKIE, "")
    params = parse_qs(request.query_params.get("redirect_params", ""))
    nonce = (params.get("nonce") or [request.query_params.get("nonce")])[0]
    with _sessions_lock:
        pending = _sessions.get(sid, {}).copy()
        if sid in _sessions:
            _sessions[sid].pop("nonce", None)
            _sessions[sid].pop("pending_until", None)
    if (not _configured() or not request_token or not nonce or
            not secrets.compare_digest(nonce, pending.get("nonce", "")) or
            datetime.now(IST) > pending.get("pending_until", datetime.min.replace(tzinfo=IST))):
        return RedirectResponse("/?kite=failed", status_code=303)
    try:
        data = exchange_request_token(os.environ["KITE_API_KEY"], os.environ["KITE_API_SECRET"], request_token)
        now = datetime.now(IST)
        expiry_date = now.date() + timedelta(days=1 if now.time() >= time(6) else 0)
        with _sessions_lock:
            _sessions[sid] = {"access_token": data["access_token"], "user_id": data.get("user_id"),
                              "expires_at": datetime.combine(expiry_date, time(6), IST)}
        return RedirectResponse("/?kite=connected", status_code=303)
    except Exception:
        return RedirectResponse("/?kite=failed", status_code=303)


@app.post("/api/kite/disconnect")
def kite_disconnect(request: Request):
    with _sessions_lock:
        _sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
    return {"connected": False}


@app.get("/api/market")
def market(request: Request):
    unavailable = {
        "source": "UNAVAILABLE", "timestamp": None, "spot": None, "change": None,
        "previous_close": None, "high": None, "low": None, "trend": None,
        "renko": None, "vwap": None, "oi": None, "gex": None, "dex": None,
        "fii": None, "dii": None, "strike": None, "premium": None,
        "signal": "NO TRADE", "tradeable": False,
        "reason": "Live market and options confirmations are incomplete.",
    }
    session = _session(request)
    if not _configured() or not session.get("access_token"):
        return unavailable
    try:
        quote = KiteBroker(os.environ["KITE_API_KEY"], session["access_token"]).quote(["NSE:NIFTY 50"])
        item = quote.get("NSE:NIFTY 50")
        if not item:
            return unavailable
        ohlc = item.get("ohlc") or {}
        return {**unavailable, "source": "KITE_SNAPSHOT", "timestamp": str(item.get("timestamp") or "") or None,
                "spot": item.get("last_price"), "change": item.get("net_change"),
                "previous_close": ohlc.get("close"), "high": ohlc.get("high"), "low": ohlc.get("low")}
    except Exception:
        return unavailable


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
