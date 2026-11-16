"""Closed-candle 5-minute VWAP/EMA breakout research signal (not a profitability claim)."""
import numpy as np
import pandas as pd

def enrich(frame: pd.DataFrame) -> pd.DataFrame:
    d = frame.copy().sort_values('time').reset_index(drop=True)
    d['ema9'] = d.close.ewm(span=9, adjust=False).mean()
    d['ema21'] = d.close.ewm(span=21, adjust=False).mean()
    # Reset VWAP each trading session, not across days.
    session = pd.to_datetime(d.time).dt.date
    typical = (d.high + d.low + d.close) / 3
    d['vwap'] = (typical * d.volume).groupby(session).cumsum() / d.volume.groupby(session).cumsum().replace(0, np.nan)
    d['previous_high'] = d.high.shift(1).rolling(5).max()
    d['previous_low'] = d.low.shift(1).rolling(5).min()
    d['volume_avg'] = d.volume.shift(1).rolling(10).mean()
    d['signal'] = 'WAIT'
    bullish = (d.close > d.previous_high) & (d.close > d.vwap) & (d.ema9 > d.ema21) & (d.volume > d.volume_avg * 1.2)
    bearish = (d.close < d.previous_low) & (d.close < d.vwap) & (d.ema9 < d.ema21) & (d.volume > d.volume_avg * 1.2)
    d.loc[bullish, 'signal'] = 'CE'
    d.loc[bearish, 'signal'] = 'PE'
    return d

def backtest(frame: pd.DataFrame, stop_points: float = 35, target_points: float = 70) -> dict:
    """Research-only SPOT point proxy; not an option premium or executable P&L backtest.
    Entry at next candle open; exits on subsequent candle OHLC; stop wins ties.
    """
    d = enrich(frame)
    trades = []
    i = 21
    while i < len(d) - 1:
        side = d.iloc[i]['signal']
        if side == 'WAIT':
            i += 1
            continue
        entry_index = i + 1
        entry = float(d.iloc[entry_index].open)
        direction = 1 if side == 'CE' else -1
        stop = entry - direction * stop_points
        target = entry + direction * target_points
        result = None
        exit_price = None
        exit_index = None
        # No overnight positions; force exit at last bar of entry session.
        session = str(d.iloc[entry_index].time)[:10]
        for j in range(entry_index, len(d)):
            bar = d.iloc[j]
            if str(bar.time)[:10] != session:
                break
            stop_hit = bar.low <= stop if direction == 1 else bar.high >= stop
            target_hit = bar.high >= target if direction == 1 else bar.low <= target
            if stop_hit:
                result, exit_price = 'STOP', stop
            elif target_hit:
                result, exit_price = 'TARGET', target
            elif j == len(d)-1 or (j+1 < len(d) and str(d.iloc[j+1].time)[:10] != session):
                result, exit_price = 'SESSION_EXIT', float(bar.close)
            if result:
                exit_index = j
                break
        if result is None:
            i += 1
            continue
        points = round((exit_price - entry) * direction, 2)
        trades.append({'time':str(d.iloc[entry_index].time),'side':side,'entry':entry,'exit':exit_price,'reason':result,'points':points})
        i = exit_index + 1
    wins = sum(t['points'] > 0 for t in trades)
    return {'disclaimer':'Spot-point proxy only; excludes options premium, IV, theta, spreads, slippage, fees and fills. Not live-ready performance.', 'trades':trades[-100:], 'count':len(trades),'win_rate':round(wins/len(trades)*100,2) if trades else 0,'net_spot_points':round(sum(t['points'] for t in trades),2)}
