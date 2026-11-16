from fastapi.testclient import TestClient
from app.main import app
from app.risk import RiskLimits, validate_order
from app.strategy import backtest
from app.demo import candles

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
