"""Read-only, closed-candle NIFTY options research setup. Never places orders."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from .market_data import nearest_nifty_future, option_chain
from .strategy import enrich


IST = ZoneInfo("Asia/Kolkata")
MIN_BARS = 21


def _stamp(value) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


def trade_setup(broker, now: datetime | None = None) -> dict:
    now = (now or datetime.now(IST)).astimezone(IST)
    base = {"source": "KITE_RESEARCH", "status": "WAIT", "reason": "", "signal": "WAIT",
            "future": None, "candle_time": None, "closed_candles": 0, "strike": None,
            "option_symbol": None, "entry_ask": None, "stop": None, "target": None,
            "lot_size": None, "max_loss": None, "reward": None, "quote_time": None,
            "automation": False, "tradeable": False,
            "note": "Research watch only. Premium levels are illustrative and untested. Account P&L and positions are not reconciled."}

    if now.weekday() >= 5 or not time(9, 20) <= now.time() < time(15, 30):
        return {**base, "reason": "Outside NIFTY market hours; setup evaluation is paused."}
    future = nearest_nifty_future(broker, now.date())
    if not future or not future.get("instrument_token"):
        return {**base, "reason": "Current NIFTY futures instrument token is unavailable."}
    base["future"] = future["symbol"]
    start = datetime.combine(now.date(), time(9, 15), IST)
    raw = broker.historical_data(future["instrument_token"], start, now, "5minute")
    bars = []
    for item in raw:
        candle_time = _stamp(item["date"])
        if candle_time.date() != now.date() or candle_time < start or candle_time + timedelta(minutes=5) > now:
            continue
        bars.append({"time": candle_time, "open": item["open"], "high": item["high"],
                     "low": item["low"], "close": item["close"], "volume": item["volume"]})
    bars.sort(key=lambda item: item["time"])
    base["closed_candles"] = len(bars)
    if bars:
        base["candle_time"] = bars[-1]["time"].isoformat()
    if len(bars) < MIN_BARS:
        return {**base, "reason": f"Need {MIN_BARS} completed 5-minute futures candles; have {len(bars)}."}
    if now - bars[-1]["time"] - timedelta(minutes=5) > timedelta(minutes=10):
        return {**base, "reason": "Latest completed futures candle is more than 10 minutes old."}
    if any(not isinstance(bar["volume"], (int, float)) or bar["volume"] <= 0 for bar in bars):
        return {**base, "reason": "Futures volume is missing; the breakout filter cannot be evaluated."}

    latest = enrich(pd.DataFrame(bars)).iloc[-1]
    base["signal"] = latest.signal
    base["checks"] = {"future_close": round(float(latest.close), 2),
                      "vwap": round(float(latest.vwap), 2),
                      "ema9": round(float(latest.ema9), 2),
                      "ema21": round(float(latest.ema21), 2),
                      "previous_high": round(float(latest.previous_high), 2),
                      "previous_low": round(float(latest.previous_low), 2),
                      "volume": int(latest.volume), "prior_10_bar_avg_volume": round(float(latest.volume_avg), 0)}
    if latest.signal == "WAIT":
        return {**base, "reason": "Latest completed candle did not pass breakout, VWAP, EMA and volume checks."}

    chain = option_chain(broker, today=now.date())
    if chain["source"] != "KITE_SNAPSHOT" or chain.get("missing_quotes") or chain.get("undated_quotes"):
        return {**base, "reason": "Current, complete NIFTY option quotes are unavailable."}
    if (not chain.get("spot_timestamp") or
            now - _stamp(chain["spot_timestamp"]) > timedelta(minutes=5)):
        return {**base, "reason": "NIFTY spot quote is more than 5 minutes old."}
    side = "ce" if latest.signal == "CE" else "pe"
    candidates = []
    for row in chain["rows"]:
        quote = row.get(side)
        if not quote or not quote["dated_today"]:
            continue
        if not quote.get("timestamp") or now - _stamp(quote["timestamp"]) > timedelta(minutes=5):
            continue
        bid, ask = quote["bid"], quote["ask"]
        if (not bid or not ask or not 80 <= ask <= 150 or ask <= bid or
                ask - bid > max(1.5, ask * 0.02) or
                (quote.get("volume") or 0) <= 0 or (quote.get("oi") or 0) <= 0 or
                (quote.get("lot_size") or 0) <= 0):
            continue
        candidates.append((abs(row["strike"] - chain["spot"]), row["strike"], quote))
    if not candidates:
        return {**base, "reason": "Breakout detected, but no displayed option has a dated ₹80–₹150 ask, two-sided spread, volume and OI."}
    _, strike, quote = min(candidates, key=lambda item: (item[0], item[1]))
    ask = float(quote["ask"])
    lot_size = quote["lot_size"]
    stop_gap = min(20.0, 2000.0 / lot_size)
    return {**base, "status": "WATCH", "reason": "Closed-candle screen passed. Review manually; execution stays locked.",
            "strike": strike, "option_symbol": quote["symbol"], "expiry": chain["expiry"],
            "entry_ask": round(ask, 2), "stop": round(ask - stop_gap, 2),
            "target": round(ask + 40, 2), "lot_size": lot_size,
            "max_loss": round(stop_gap * lot_size, 2), "reward": round(40 * lot_size, 2),
            "quote_time": quote["timestamp"], "spread": round(ask - quote["bid"], 2)}
