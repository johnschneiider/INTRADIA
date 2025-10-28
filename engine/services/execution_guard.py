from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class AccountState:
    balance: Decimal
    free_margin: Decimal
    open_positions_count: int
    exposure_pct: float


@dataclass
class OrderIntent:
    symbol: str
    side: str  # 'buy' or 'sell'
    entry: Decimal
    stop: Decimal
    take_profit: Decimal | None
    risk_percent: float


class GuardResult:
    def __init__(self, allowed: bool, reason: str | None = None):
        self.allowed = allowed
        self.reason = reason


def validate_intent(account: AccountState, intent: OrderIntent, *,
                    max_risk_percent: float = 0.5,
                    max_concurrent_positions: int = 3,
                    max_exposure_pct: float = 30.0) -> GuardResult:
    # Hard caps
    if account.open_positions_count >= max_concurrent_positions:
        return GuardResult(False, 'max_concurrent_positions')
    if account.exposure_pct >= max_exposure_pct:
        return GuardResult(False, 'max_exposure')
    if intent.risk_percent > max_risk_percent:
        return GuardResult(False, 'risk_percent_exceeds')
    # Basic sanity: stop distance must be > 0
    if intent.side == 'buy' and intent.stop >= intent.entry:
        return GuardResult(False, 'invalid_stop_distance')
    if intent.side == 'sell' and intent.stop <= intent.entry:
        return GuardResult(False, 'invalid_stop_distance')
    return GuardResult(True)

