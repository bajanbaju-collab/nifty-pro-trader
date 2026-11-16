import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import app.main as terminal
import app.market_data as market_data
from app.demo import candles
from app.risk import RiskLimits, validate_order
from app.strategy import backtest


class PrivateTerminalTests(unittest.TestCase):
    def setUp(self):
        with terminal._sessions_lock:
            terminal._sessions.clear()
        self.env = patch.dict(os.environ, {
            "KITE_API_KEY": "test-key", "KITE_API_SECRET": "test-secret",
            "ALLOWED_KITE_USER_ID": "AB1234",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_public_health_and_private_dashboard(self):
        with TestClient(terminal.app, base_url="https://testserver") as visitor:
            self.assertEqual(visitor.get("/healthz").json(), {"ok": True})
            self.assertIn("Sign in with Zerodha Kite", visitor.get("/").text)
            for path in ("/api/status", "/api/market", "/api/option-chain", "/api/candles", "/api/ideas", "/api/backtest"):
                self.assertEqual(visitor.get(path).status_code, 401, path)
            self.assertEqual(visitor.get("/static/index.html", follow_redirects=False).status_code, 303)
            self.assertEqual(visitor.post("/api/orders", json={}).status_code, 401)
            self.assertEqual(visitor.get("/docs", follow_redirects=False).status_code, 303)

    def test_missing_owner_fails_closed(self):
        with patch.dict(os.environ, {"ALLOWED_KITE_USER_ID": ""}):
            with TestClient(terminal.app, base_url="https://testserver") as visitor:
                self.assertIn("Sign in with Zerodha Kite", visitor.get("/").text)
                self.assertEqual(visitor.get("/api/kite/connect").status_code, 503)
                self.assertEqual(visitor.get("/api/status").status_code, 401)

    @patch.object(terminal, "login_url", side_effect=lambda key, nonce: "https://kite.zerodha.com/connect/login?nonce=" + nonce)
    @patch.object(terminal, "exchange_request_token")
    def test_owner_only_oauth_and_locked_orders(self, exchange, _login):
        exchange.return_value = {"access_token": "server-only-token", "user_id": "OTHER1"}
        with TestClient(terminal.app, base_url="https://testserver") as owner:
            start = owner.get("/api/kite/connect", follow_redirects=False)
            self.assertEqual(start.status_code, 303)
            self.assertIn("httponly", start.headers["set-cookie"].lower())
            self.assertIn("secure", start.headers["set-cookie"].lower())
            nonce = parse_qs(urlparse(start.headers["location"]).query)["nonce"][0]
            bad = owner.get("/api/kite/callback", params={"request_token": "one-time", "nonce": "wrong"}, follow_redirects=False)
            self.assertEqual(bad.headers["location"], "/?kite=failed")

            start = owner.get("/api/kite/connect", follow_redirects=False)
            nonce = parse_qs(urlparse(start.headers["location"]).query)["nonce"][0]
            denied = owner.get("/api/kite/callback", params={"request_token": "one-time", "nonce": nonce}, follow_redirects=False)
            self.assertEqual(denied.headers["location"], "/?kite=unauthorized")
            self.assertEqual(owner.get("/api/status").status_code, 401)

            exchange.return_value = {"access_token": "server-only-token", "user_id": "AB1234"}
            start = owner.get("/api/kite/connect", follow_redirects=False)
            nonce = parse_qs(urlparse(start.headers["location"]).query)["nonce"][0]
            done = owner.get("/api/kite/callback", params={"request_token": "one-time", "nonce": nonce}, follow_redirects=False)
            self.assertEqual(done.headers["location"], "/?kite=connected")
            self.assertIn("NIFTY Pro Trader", owner.get("/").text)
            self.assertNotIn("Sign in with Zerodha Kite", owner.get("/").text)
            self.assertEqual(owner.get("/static/index.html").status_code, 200)
            status = owner.get("/api/status")
            self.assertTrue(status.json()["broker_connected"])
            self.assertFalse(status.json()["orders_enabled"])
            self.assertNotIn("server-only-token", status.text)
            self.assertEqual(owner.post("/api/orders", json={}).status_code, 423)
            self.assertEqual(len(owner.get("/api/candles").json()["candles"]), 75)
            with TestClient(terminal.app, base_url="https://testserver") as stranger:
                self.assertEqual(stranger.get("/api/status").status_code, 401)
                self.assertIn("Sign in with Zerodha Kite", stranger.get("/").text)
            self.assertEqual(owner.post("/api/kite/disconnect").json(), {"connected": False})
            self.assertEqual(owner.get("/api/status").status_code, 401)

    def test_research_and_risk_helpers(self):
        self.assertIn("Spot-point proxy", backtest(candles())["disclaimer"])
        errors = validate_order(premium=100, stop_premium=50, quantity=65, lot_size=65,
                                realized_pnl=-10000, orders_today=0, open_positions=0,
                                limits=RiskLimits())
        self.assertTrue(any("circuit breaker" in item for item in errors))
        self.assertTrue(any("Per-trade" in item for item in errors))


    def test_read_only_nifty_option_chain(self):
        from datetime import date

        class Broker:
            def instruments(self, exchange):
                self.exchange = exchange
                return [dict(exchange="NFO", segment="NFO-OPT", name="NIFTY",
                             instrument_type=side, tradingsymbol=f"NIFTY_TEST_25000{side}",
                             expiry=date(2026, 11, 19), strike=25000, lot_size=65)
                        for side in ("CE", "PE")]

            def quote(self, instruments):
                if instruments == ["NSE:NIFTY 50"]:
                    return {"NSE:NIFTY 50": {"last_price": 25002, "timestamp": "2026-11-16 15:30:00"}}
                self.requested = instruments
                return {symbol: {"last_price": 99.5, "oi": 13000, "volume": 750,
                                 "timestamp": "2026-11-16 15:29:00",
                                 "depth": {"buy": [{"price": 99, "quantity": 65, "orders": 2}],
                                           "sell": [{"price": 100, "quantity": 130, "orders": 3}]}}
                        for symbol in instruments}

        market_data._instrument_day = None
        broker = Broker()
        data = market_data.option_chain(broker, today=date(2026, 11, 16))
        self.assertEqual(broker.exchange, "NFO")
        self.assertEqual(broker.requested, ["NFO:NIFTY_TEST_25000CE", "NFO:NIFTY_TEST_25000PE"])
        self.assertEqual(data["source"], "KITE_SNAPSHOT")
        self.assertFalse(data["tradeable"])
        self.assertEqual(data["rows"][0]["ce"]["oi"], 13000)
        self.assertEqual(data["rows"][0]["pe"]["depth"]["sell"][0]["price"], 100)
        with self.assertRaises(ValueError):
            market_data.option_chain(broker, expiry="2026-12-01", today=date(2026, 11, 16))


if __name__ == "__main__":
    unittest.main()
