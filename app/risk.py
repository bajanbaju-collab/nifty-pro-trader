from dataclasses import dataclass

@dataclass
class RiskLimits:
    max_daily_loss: float = 10000
    max_daily_profit: float = 30000
    max_trade_risk: float = 2000
    max_orders_per_day: int = 6
    max_open_positions: int = 1
    max_order_lots: int = 1

def validate_order(*, premium: float, stop_premium: float, quantity: int, lot_size: int,
                   realized_pnl: float, orders_today: int, open_positions: int,
                   limits: RiskLimits) -> list[str]:
    errors = []
    if quantity <= 0 or lot_size <= 0 or quantity % lot_size:
        errors.append('Quantity must be a positive multiple of current exchange lot size')
    if lot_size > 0 and quantity > limits.max_order_lots * lot_size:
        errors.append('Order exceeds maximum lots')
    if premium <= 0 or stop_premium < 0 or stop_premium >= premium:
        errors.append('Invalid long-option entry/stop premiums')
    if quantity * max(0, premium-stop_premium) > limits.max_trade_risk:
        errors.append('Per-trade risk exceeded')
    if realized_pnl <= -limits.max_daily_loss:
        errors.append('Daily loss circuit breaker')
    if realized_pnl >= limits.max_daily_profit:
        errors.append('Daily profit circuit breaker')
    if orders_today >= limits.max_orders_per_day:
        errors.append('Daily order count exceeded')
    if open_positions >= limits.max_open_positions:
        errors.append('Open-position limit reached')
    return errors
