"""Deterministic synthetic data for UI/testing; never represented as NSE market data."""
import numpy as np
import pandas as pd

def candles(n=180):
    rng = np.random.default_rng(42)
    times = pd.date_range('2026-11-13 09:15', periods=n, freq='5min', tz='Asia/Kolkata')
    # Use a single illustrative session for research; 75 bars max within 09:15-15:30.
    times = times[:75]
    steps = rng.normal(0.5, 17, len(times))
    close = 25000 + np.cumsum(steps)
    op = np.r_[25000,close[:-1]]
    high = np.maximum(op,close) + rng.uniform(1,10,len(times))
    low = np.minimum(op,close) - rng.uniform(1,10,len(times))
    return pd.DataFrame({'time':times.astype(str),'open':op,'high':high,'low':low,'close':close,'volume':rng.integers(5000,25000,len(times))})
