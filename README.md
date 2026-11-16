# NIFTY Pro Trader — browser research terminal

FastAPI serves a responsive Simple/Pro dashboard for desktop and Android browsers. The chart, signals and backtest use deterministic synthetic 5-minute NIFTY-like data. They are **not live NSE quotes or option performance**. The market decision is always NO TRADE. The Kite adapter can only query a profile through a protected server-side check. `POST /api/orders` always returns 423; no code path calls Kite order placement.

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
2. In Render, create a **Blueprint** from this repository and use `render.yaml`, or create a **Web Service** with Python runtime and Free plan. Build: `pip install -r requirements.txt`. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Health path: `/healthz`.
3. Visit the HTTPS `onrender.com` address from the office laptop or Android Chrome. There is no local installation. Browser access to Render may be restricted by an office network policy.

No credentials are required on Render for the public demo. If you later configure read-only Kite connectivity, put `KITE_API_KEY`, `KITE_ACCESS_TOKEN` and a long random `ADMIN_TOKEN` in **Render environment variables**, never in GitHub or browser code. `GET /api/broker/check` requires `X-Admin-Token` and returns only connection status and Kite user ID. A production authentication design is needed before any private account data is displayed on a public hosting URL. Kite access tokens expire and its official login/token exchange flow is not implemented here. No trading switch is available.

Render Free may sleep after 15 minutes idle, taking about a minute on the next visit. Its filesystem is ephemeral, so this app stores no positions or durable results. Free hosting is for this demo and research interface, not time-critical alerts or automated execution.

## Research scope

- Simple: decision, smart strike placeholders, confirmation and risk planning values.
- Pro: OI, FII/DII, Greeks, GEX/DEX and depth placeholders with clear missing-data labels.
- Synthetic 5-minute chart, signal examples and spot-point proxy backtest. The proxy excludes option premium, bid/ask, IV, theta, fills, charges and taxes.
- Illustrative risk parameters: ₹2,000 per trade, ₹10,000 daily loss, ₹30,000 daily profit, one position. These are **not enforced against a brokerage account**.

Before any future live trading release: licensed market/option data, dated instrument master and lot sizes, realistic premium backtesting, authenticated user sessions, persistent broker reconciliation, protective exits, idempotency, outage handling and regulatory/broker checks need separate implementation and review.
