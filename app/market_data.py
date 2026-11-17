"""Read-only NIFTY option quotes; no order or signal generation."""

from datetime import date, datetime
from threading import Lock
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
_instrument_lock = Lock()
_instrument_day: date | None = None
_nifty_options: list[dict] = []
_nifty_futures: list[dict] = []


def _date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _contracts(broker, today: date) -> list[dict]:
    global _instrument_day, _nifty_options, _nifty_futures
    with _instrument_lock:
        if _instrument_day == today:
            return _nifty_options
        rows = []
        futures = []
        for item in broker.instruments("NFO"):
            if item.get("exchange") != "NFO" or item.get("name") != "NIFTY":
                continue
            try:
                expiry = _date(item["expiry"])
            except (KeyError, TypeError, ValueError):
                continue
            if expiry < today or not item.get("tradingsymbol"):
                continue
            if item.get("segment") == "NFO-FUT" and item.get("instrument_type") == "FUT":
                futures.append({"expiry": expiry.isoformat(), "symbol": item["tradingsymbol"],
                                "lot_size": int(item.get("lot_size") or 0),
                                "instrument_token": item.get("instrument_token")})
            elif item.get("segment") == "NFO-OPT" and item.get("instrument_type") in ("CE", "PE"):
                try:
                    strike = float(item["strike"])
                except (KeyError, TypeError, ValueError):
                    continue
                if strike <= 0:
                    continue
                rows.append({"expiry": expiry.isoformat(), "strike": strike,
                             "type": item["instrument_type"], "symbol": item["tradingsymbol"],
                             "lot_size": int(item.get("lot_size") or 0)})
        _nifty_options = rows
        _nifty_futures = sorted(futures, key=lambda c: c["expiry"])
        _instrument_day = today
        return rows


def nearest_nifty_future(broker, today: date) -> dict | None:
    _contracts(broker, today)
    return _nifty_futures[0].copy() if _nifty_futures else None


def derivatives_snapshot(broker, today: date | None = None) -> dict:
    today = today or datetime.now(IST).date()
    future = nearest_nifty_future(broker, today)
    symbols = ["NSE:INDIA VIX"] + (["NFO:" + future["symbol"]] if future else [])
    quotes = broker.quote(symbols)
    vix_quote = quotes.get("NSE:INDIA VIX") or {}
    future_quote = quotes.get("NFO:" + future["symbol"]) if future else None

    def dated(item):
        raw = str((item or {}).get("timestamp") or "")
        return raw if raw and not raw.startswith(("1970-", "0001-")) else None

    vix = {"value": vix_quote.get("last_price"), "timestamp": dated(vix_quote)} if vix_quote else None
    futures = ({"symbol": future["symbol"], "expiry": future["expiry"],
                "oi": future_quote.get("oi"), "last_price": future_quote.get("last_price"),
                "timestamp": dated(future_quote)} if future and future_quote else None)
    return {"source": "KITE_SNAPSHOT", "futures": futures, "vix": vix,
            "tradeable": False, "note": "OI is a snapshot, not daily change. India VIX is not ATM option IV."}


def _depth(levels) -> list[dict]:
    return [{"price": level.get("price"), "quantity": level.get("quantity"),
             "orders": level.get("orders")}
            for level in (levels or [])[:5] if (level.get("price") or 0) > 0]


def _contract_quote(contract: dict | None, quotes: dict, exchange: str = "NFO",
                    today: date | None = None) -> dict | None:
    if not contract:
        return None
    item = quotes.get(exchange + ":" + contract["symbol"])
    if not item:
        return None
    depth = item.get("depth") or {}
    bid, ask = _depth(depth.get("buy")), _depth(depth.get("sell"))
    raw_time = str(item.get("timestamp") or "")
    timestamp = raw_time if raw_time and not raw_time.startswith(("1970-", "0001-")) else None
    return {"symbol": contract["symbol"], "lot_size": contract["lot_size"],
            "last_price": item.get("last_price"), "volume": item.get("volume"),
            "oi": item.get("oi"), "timestamp": timestamp,
            "dated_today": bool(timestamp and today and timestamp[:10] == today.isoformat()),
            "bid": bid[0]["price"] if bid else None, "ask": ask[0]["price"] if ask else None,
            "bid_qty": bid[0]["quantity"] if bid else None,
            "ask_qty": ask[0]["quantity"] if ask else None,
            "depth": {"buy": bid, "sell": ask}}


def option_chain(broker, expiry: str | None = None, today: date | None = None) -> dict:
    today = today or datetime.now(IST).date()
    contracts = _contracts(broker, today)
    expiries = sorted({item["expiry"] for item in contracts})
    if not expiries:
        return {"source": "UNAVAILABLE", "reason": "No current NIFTY option contracts in Kite instrument master",
                "expiries": [], "rows": [], "tradeable": False}
    if expiry and expiry not in expiries:
        raise ValueError("Expiry is not in the current Kite instrument master")
    selected = expiry or expiries[0]
    spot_item = broker.quote(["NSE:NIFTY 50"]).get("NSE:NIFTY 50") or {}
    spot = spot_item.get("last_price")
    if not isinstance(spot, (int, float)) or spot <= 0:
        return {"source": "UNAVAILABLE", "reason": "NIFTY spot quote unavailable",
                "expiries": expiries, "expiry": selected, "rows": [], "tradeable": False}
    by_strike: dict[float, dict] = {}
    for item in contracts:
        if item["expiry"] == selected:
            by_strike.setdefault(item["strike"], {})[item["type"]] = item
    strikes = sorted(by_strike)
    atm_index = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
    first = max(0, min(atm_index - 7, len(strikes) - 15))
    selected_strikes = strikes[first:first + 15]
    symbols = ["NFO:" + by_strike[strike][side]["symbol"] for strike in selected_strikes
               for side in ("CE", "PE") if side in by_strike[strike]]
    quotes = broker.quote(symbols) if symbols else {}
    rows = [{"strike": strike, "atm": strike == strikes[atm_index],
             "ce": _contract_quote(by_strike[strike].get("CE"), quotes, today=today),
             "pe": _contract_quote(by_strike[strike].get("PE"), quotes, today=today)}
            for strike in selected_strikes]
    times = [side["timestamp"] for row in rows for side in (row["ce"], row["pe"])
             if side and side["timestamp"]]
    sides = [side for row in rows for side in (row["ce"], row["pe"]) if side]
    missing = len(symbols) - len(quotes)
    undated = sum(not side["timestamp"] or side["timestamp"][:10] != today.isoformat() for side in sides)
    no_depth = sum(not side["bid"] or not side["ask"] for side in sides)
    return {"source": "KITE_SNAPSHOT", "expiry": selected, "expiries": expiries[:8],
            "spot": spot, "spot_timestamp": str(spot_item.get("timestamp") or "") or None,
            "quote_time": max(times) if times else None, "rows": rows,
            "missing_quotes": max(0, missing), "undated_quotes": undated,
            "without_depth": no_depth, "tradeable": False,
            "note": "Kite snapshot, not streaming. OI is quantity, not OI change. IV and Greeks are not supplied."}
