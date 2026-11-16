from fastapi.testclient import TestClient
from app.main import app
from app.risk import RiskLimits, validate_order
from app.strategy import backtest
from app.demo import candles
from urllib.parse import parse_qs, urlparse
import app.main as terminal

client = TestClient(app)

def test_home():
    assert client.get('/').status_code == 200
    assert client.get('/healthz').json() == {'ok': True}
    assert client.get('/api/market').json()['spot'] is None
    assert client.get('/api/status').json()['orders_enabled'] is False

def test_chart_and_backtest():
    assert len(client.get('/api/candles').json()['candles']) == 75
    assert client.get('/api/backtest').json()['count'] >= 0

def test_live_order_fails_closed():
    payload={'symbol':'NIFTY26NOV25000CE','quantity':65,'lot_size':65,'entry_premium':100,'stop_premium':90}
    assert client.post('/api/orders',json=payload).status_code == 423
    assert client.post('/api/orders',json={}).status_code == 423
    assert client.get('/api/broker/check').status_code == 401

def test_risk_rejects_large_loss():
    errors=validate_order(premium=100,stop_premium=50,quantity=65,lot_size=65,
        realized_pnl=-10000,orders_today=0,open_positions=0,limits=RiskLimits())
    assert any('circuit breaker' in x for x in errors)
    assert any('Per-trade' in x for x in errors)

def test_backtest_returns_proxy():
    assert 'Spot-point proxy' in backtest(candles())['disclaimer']

def test_broker_setup_and_invalid_callback(monkeypatch):
    monkeypatch.delenv('KITE_API_KEY', raising=False)
    monkeypatch.delenv('KITE_API_SECRET', raising=False)
    assert client.get('/api/kite/connect').status_code == 503
    assert client.get('/api/kite/callback?request_token=bad&nonce=bad', follow_redirects=False).headers['location'] == '/?kite=failed'
    assert client.get('/api/market').json()['source'] == 'UNAVAILABLE'

def test_read_only_kite_session(monkeypatch):
    monkeypatch.setenv('KITE_API_KEY', 'test-key')
    monkeypatch.setenv('KITE_API_SECRET', 'test-secret')
    monkeypatch.setattr(terminal, 'login_url', lambda key, nonce: 'https://kite.zerodha.com/connect/login?nonce=' + nonce)
    monkeypatch.setattr(terminal, 'exchange_request_token', lambda key, secret, token: {'access_token': 'server-only-token', 'user_id': 'AB1234'})
    class FakeBroker:
        def __init__(self, key, token):
            assert token == 'server-only-token'
        def quote(self, instruments):
            return {'NSE:NIFTY 50': {'last_price': 25000.5, 'net_change': 10.5, 'timestamp': '2026-11-16 09:30:00', 'ohlc': {'close': 24990}}}
    monkeypatch.setattr(terminal, 'KiteBroker', FakeBroker)
    with TestClient(app, base_url='https://testserver') as browser:
        start = browser.get('/api/kite/connect', follow_redirects=False)
        assert start.status_code == 303
        assert 'httponly' in start.headers['set-cookie'].lower()
        assert 'secure' in start.headers['set-cookie'].lower()
        nonce = parse_qs(urlparse(start.headers['location']).query)['nonce'][0]
        assert browser.get('/api/kite/callback', params={'request_token': 'one-time', 'redirect_params': 'nonce=wrong'}, follow_redirects=False).headers['location'] == '/?kite=failed'
        start = browser.get('/api/kite/connect', follow_redirects=False)
        nonce = parse_qs(urlparse(start.headers['location']).query)['nonce'][0]
        done = browser.get('/api/kite/callback', params={'request_token': 'one-time', 'redirect_params': 'nonce=' + nonce}, follow_redirects=False)
        assert done.headers['location'] == '/?kite=connected'
        assert browser.get('/api/status').json()['broker_connected'] is True
        assert 'server-only-token' not in browser.get('/api/status').text
        assert browser.get('/api/market').json()['spot'] == 25000.5
        assert browser.post('/api/orders', json={}).status_code == 423
        assert browser.post('/api/kite/disconnect').json()['connected'] is False
        assert browser.get('/api/status').json()['broker_connected'] is False
