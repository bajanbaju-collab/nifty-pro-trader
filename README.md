# NIFTY Pro Trader — browser research terminal

FastAPI serves a responsive Simple/Pro dashboard based on the NIFTY Pro Trader reference layout. A read-only Kite login supplies a NIFTY spot quote, nearest-expiry NIFTY futures OI, India VIX, and a limited option-chain snapshot with LTP, OI, volume and five-level depth where Kite quotes provide them. A separate MCX CRUDEOIL view shows the listed futures contract and, when available, its option-chain snapshots and depth. Crude oil prices are quoted in rupees per barrel; the futures quote is not spot. The NIFTY premium screen filters displayed quotes but does not generate trade signals. A displayed-strike PCR appears only when the displayed CE/PE OI quotes are dated and complete; it is not whole-market PCR. ATM CE bid/ask quantities use available five-level depth. Futures OI is a snapshot, not OI change. Greeks, FII/DII, validated signals and automation remain unavailable. The chart, signals and backtest under **Backtest** use deterministic NIFTY synthetic data, not live NSE or MCX performance. Signal evaluation remains NOT EVALUATED. `POST /api/orders` always returns 423; no code path calls Kite order placement.

## Local development

Python 3.12 is recommended. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
python -m unittest discover -s tests -v
```

Open `http://127.0.0.1:8000`. The sign-in page appears without credentials. To enter the dashboard locally, configure a Kite Connect app, its redirect URL, and all three variables below. The Secure cookie requires HTTPS for a full local login test. `/healthz` is the hosting health check.

## GitHub + Render Free deployment

1. Push this directory to a GitHub repository. `.env` is ignored and must never be committed.
2. In Render, create a **Blueprint** from this repository and use `render.yaml`, or create a **Web Service** with Python runtime and Free plan. Build: `pip install -r requirements.txt`. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log`. Health path: `/healthz`. Disable access logs because Kite's one-time request token arrives in a callback URL.
3. Visit the HTTPS `onrender.com` address from the office laptop or Android Chrome. There is no local installation. Browser access to Render may be restricted by an office network policy.

The public URL shows only a sign-in page until the authorized Zerodha account logs in. Create a Kite Connect app and register `https://nifty-pro-trader.onrender.com/api/kite/callback` as its redirect URL. Set `KITE_API_KEY`, `KITE_API_SECRET`, and `ALLOWED_KITE_USER_ID` (the exact Zerodha user ID returned by Kite for the owner) in **Render environment variables**, never in GitHub, frontend code or chat. With no allowed user ID, the app fails closed. A different Kite account is rejected after authentication. The GitHub code repository remains public; making it private is a separate choice and does not replace app authentication.

The server exchanges the request token and keeps the access token only in its process memory, associated with a random HttpOnly Secure cookie. It never returns the token to the browser. A server restart or sleep requires reconnecting; Kite access tokens also expire. Direct API and static dashboard requests require the allowed session. Spot, futures and option quotes are read-only manual snapshots, not a streaming feed. NFO and MCX instrument masters are cached per day in memory. If the Kite MCX instrument list or quotes are unavailable, the crude oil panel reports that explicitly. No trading switch is available. The legacy `GET /api/broker/check` also requires the allowed session and `ADMIN_TOKEN`.

Render Free may sleep after 15 minutes idle, taking about a minute on the next visit. Its filesystem is ephemeral, so this app stores no positions or durable results. Free hosting is for this demo and research interface, not time-critical alerts or automated execution.

## Research scope

- Simple: NIFTY market overview, MCX crude oil futures reference, decision, strike finder, data quality and planning risk values.
- Pro: NIFTY option chain, MCX CRUDEOIL futures/option chain, contract depth, OI, FII/DII, Greeks, GEX/DEX and navigation panels with clear missing-data labels. Crude oil has no validated trade setup or backtest.
- Synthetic 5-minute chart, signal examples and spot-point proxy backtest. The proxy excludes option premium, bid/ask, IV, theta, fills, charges and taxes.
- Illustrative risk parameters: ₹2,000 per trade, ₹10,000 daily loss, ₹30,000 daily profit, one position. These are **not enforced against a brokerage account**.

Before any future live trading release: licensed market/option data, dated instrument master and lot sizes, realistic premium backtesting, durable authenticated sessions, persistent broker reconciliation, protective exits, idempotency, outage handling and regulatory/broker checks need separate implementation and review.
