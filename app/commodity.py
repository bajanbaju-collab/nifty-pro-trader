"""Read-only MCX CRUDEOIL futures and options snapshots."""

import re
from datetime import date, datetime
from threading import Lock

from .market_data import IST, _contract_quote, _date


_lock = Lock()
_day: date | None = None
_contracts: list[dict] = []


def _crude_contracts(broker, today: date) -> list[dict]:
    global _day, _contracts
    with _lock:
        if _day == today:
            return _contracts
        found = []
        for item in broker.instruments("MCX"):
            symbol = item.get("tradingsymbol") or ""
            if (item.get("exchange") != "MCX" or
                    not (item.get("name") == "CRUDEOIL" or re.match(r"^CRUDEOIL\d", symbol)) or
                    item.get("instrument_type") not in ("FUT", "CE", "PE")):
                continue
            try:
                expiry = _date(item["expiry"])
                strike = float(item.get("strike") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if expiry < today or not symbol:
                continue
            kind = item["instrument_type"]
            if kind in ("CE", "PE") and strike <= 0:
                continue
            found.append({"expiry": expiry.isoformat(), "strike": strike, "type": kind,
                          "symbol": symbol, "lot_size": int(item.get("lot_size") or 0)})
        _contracts = found
        _day = today
        return found


def crude_oil_snapshot(broker, expiry: str | None = None, today: date | None = None) -> dict:
    today = today or datetime.now(IST).date()
    contracts = _crude_contracts(broker, today)
    futures = sorted((c for c in contracts if c["type"] == "FUT"), key=lambda c: c["expiry"])
    options = [c for c in contracts if c["type"] in ("CE", "PE")]
    expiries = sorted({c["expiry"] for c in options})
    if expiry and expiry not in expiries:
        raise ValueError("Expiry is not in the current MCX CRUDEOIL instrument master")
    selected = expiry or (expiries[0] if expiries else None)
    if not futures:
        return {"source": "UNAVAILABLE", "reason": "No current MCX CRUDEOIL futures contract in Kite instrument master",
                "expiries": expiries[:8], "rows": [], "tradeable": False}
    future = next((c for c in futures if not selected or c["expiry"] >= selected), futures[0])
    future_quote = broker.quote(["MCX:" + future["symbol"]]).get("MCX:" + future["symbol"]) or {}
    reference = future_quote.get("last_price")
    if not isinstance(reference, (int, float)) or reference <= 0:
        return {"source": "UNAVAILABLE", "reason": "MCX CRUDEOIL futures quote unavailable",
                "future": future, "expiry": selected, "expiries": expiries[:8],
                "rows": [], "tradeable": False}
    by_strike: dict[float, dict] = {}
    for item in options:
        if item["expiry"] == selected:
            by_strike.setdefault(item["strike"], {})[item["type"]] = item
    strikes = sorted(by_strike)
    selected_strikes = []
    atm = None
    if strikes:
        atm_index = min(range(len(strikes)), key=lambda i: abs(strikes[i] - reference))
        atm = strikes[atm_index]
        first = max(0, min(atm_index - 7, len(strikes) - 15))
        selected_strikes = strikes[first:first + 15]
    symbols = ["MCX:" + by_strike[strike][side]["symbol"] for strike in selected_strikes
               for side in ("CE", "PE") if side in by_strike[strike]]
    quotes = broker.quote(symbols) if symbols else {}
    rows = [{"strike": strike, "atm_approx": strike == atm,
             "ce": _contract_quote(by_strike[strike].get("CE"), quotes, exchange="MCX"),
             "pe": _contract_quote(by_strike[strike].get("PE"), quotes, exchange="MCX")}
            for strike in selected_strikes]
    times = [side["timestamp"] for row in rows for side in (row["ce"], row["pe"])
             if side and side["timestamp"]]
    return {"source": "KITE_SNAPSHOT", "market": "MCX CRUDEOIL", "unit": "INR_PER_BARREL",
            "future": {"symbol": future["symbol"], "expiry": future["expiry"],
                       "lot_size": future["lot_size"], "last_price": reference,
                       "timestamp": str(future_quote.get("timestamp") or "") or None,
                       "change": future_quote.get("net_change")},
            "expiry": selected, "expiries": expiries[:8], "rows": rows,
            "quote_time": max(times) if times else None,
            "missing_quotes": max(0, len(symbols) - len(quotes)), "tradeable": False,
            "note": "MCX futures reference is the nearest listed futures expiry on or after the option expiry. "
                    "The highlighted strike is an approximation. Kite quotes are snapshots; no trade signal."}
