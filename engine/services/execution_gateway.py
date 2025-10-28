from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Any

from connectors.deriv_client import DerivClient, OrderRequest
from engine.services.execution_guard import AccountState, OrderIntent, validate_intent


def compute_position_size(balance: Decimal, entry: Decimal, stop: Decimal, risk_percent: float, *, min_unit: float = 1.0) -> float:
    risk_amount = float(balance) * (risk_percent / 100.0)
    risk_per_unit = abs(float(entry) - float(stop))
    if risk_per_unit <= 0:
        return 0.0
    units = risk_amount / risk_per_unit
    # redondeo a unidad mínima
    return max(min_unit, (units // min_unit) * min_unit)


def place_order_through_gateway(symbol: str, side: str, entry: Decimal, stop: Decimal, take_profit: Decimal | None,
                                risk_percent: float, *, order_type: str = 'limit') -> Dict[str, Any]:
    client = DerivClient()
    bal = client.get_balance()['balance']
    account = AccountState(balance=Decimal(str(bal)), free_margin=Decimal(str(bal)), open_positions_count=0, exposure_pct=0.0)
    intent = OrderIntent(symbol=symbol, side='buy' if side == 'buy' else 'sell', entry=entry, stop=stop,
                         take_profit=take_profit, risk_percent=risk_percent)
    guard = validate_intent(account, intent)
    if not guard.allowed:
        return {'accepted': False, 'reason': guard.reason}

    size = compute_position_size(account.balance, entry, stop, risk_percent)
    if size <= 0:
        return {'accepted': False, 'reason': 'invalid_size'}

    req = OrderRequest(symbol=symbol, side=side, size=size, type=order_type, price=float(entry),
                       stop=float(stop) if take_profit is not None else float(stop),
                       take_profit=float(take_profit) if take_profit is not None else None,
                       client_id=None)
    resp = client.place_order(req)
    return resp | {'size': size}

