# NIFTY Pro Trader — browser research terminal

FastAPI serves a responsive Simple/Pro dashboard based on the NIFTY Pro Trader reference layout. Its market overview, strike finder, order book, option chain, Greeks, flows, automation and risk sections show unavailable values until the corresponding data and validation exist. A read-only Kite login can supply a NIFTY spot quote snapshot. The chart, signals and backtest under **Backtest** use deterministic synthetic data, not live NSE quotes or option performance. The market decision remains NO TRADE. `POST /api/orders` always returns 423; no code path calls Kite order placement.

## Local development

Python 3.12 is recommended. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest -q
```

Open `http://127.0.0.1:8000`. No account or broker credentials are needed for the demo. `/healthz` is the hosting health check.

## GitHub + Render Free deployment

1. Push this directory to a GitHub repository. `.env` is ignored and must never be committed.
2. In Render, create a **Blueprint** from this repository and use `render.yaml`, or create a **Web Service** with Python runtime and Free plan. Build: `pip install -r requirements.txt`. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log`. Health path: `/healthz`. Disable access logs because Kite's one-time request token arrives in a callback URL.
3. Visit the HTTPS `onrender.com` address from the office laptop or Android Chrome. There is no local installation. Browser access to Render may be restricted by an office network policy.

No credentials are required for the research dashboard. To enable the visible **Connect Kite** button, create a Kite Connect app and register `https://nifty-pro-trader.onrender.com/api/kite/callback` as its redirect URL. Put `KITE_API_KEY` and `KITE_API_SECRET` in **Render environment variables**, never in GitHub, frontend code or chat. Redeploy, then select Connect Kite and complete Zerodha login on Zerodha's site. The server exchanges the request token and keeps the access token only in its process memory, associated with a random HttpOnly Secure cookie. It never returns the token to the browser. A server restart or sleep requires reconnecting; Kite access tokens also expire. Only a read-only NIFTY spot quote snapshot is wired; it is not a streaming feed. No trading switch is available. The legacy `GET /api/broker/check` remains protected by `ADMIN_TOKEN` and is optional.

Render Free may sleep after 15 minutes idle, taking about a minute on the next visit. Its filesystem is ephemeral, so this app stores no positions or durable results. Free hosting is for this demo and research interface, not time-critical alerts or automated execution.

## Research scope

- Simple: market overview, decision, strike finder, data quality and planning risk values.
- Pro: option chain, order book, OI, FII/DII, Greeks, GEX/DEX and navigation panels with clear missing-data labels.
- Synthetic 5-minute chart, signal examples and spot-point proxy backtest. The proxy excludes option premium, bid/ask, IV, theta, fills, charges and taxes.
- Illustrative risk parameters: ₹2,000 per trade, ₹10,000 daily loss, ₹30,000 daily profit, one position. These are **not enforced against a brokerage account**.

Before any future live trading release: licensed market/option data, dated instrument master and lot sizes, realistic premium backtesting, authenticated user sessions, persistent broker reconciliation, protective exits, idempotency, outage handling and regulatory/broker checks need separate implementation and review.
