from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
import hashlib
import json


# Métricas Prometheus
ORDER_COUNTER = Counter('orders_total', 'Total orders placed', ['symbol', 'side', 'status'])
ORDER_LATENCY = Histogram('order_latency_seconds', 'Order execution latency')
PNL_GAUGE = Gauge('pnl_total', 'Total P&L')
DRAWDOWN_GAUGE = Gauge('max_drawdown_percent', 'Maximum drawdown percentage')
WINRATE_GAUGE = Gauge('winrate_percent', 'Win rate percentage')


def hash_payload(payload: dict) -> str:
    """Genera hash del payload para auditoría"""
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def record_order(symbol: str, side: str, accepted: bool):
    """Registra métrica de orden"""
    status = 'accepted' if accepted else 'rejected'
    ORDER_COUNTER.labels(symbol=symbol, side=side, status=status).inc()


def record_latency(seconds: float):
    """Registra latencia de orden"""
    ORDER_LATENCY.observe(seconds)


def update_pnl_metrics(pnl: float, drawdown: float, winrate: float):
    """Actualiza métricas de P&L"""
    PNL_GAUGE.set(pnl)
    DRAWDOWN_GAUGE.set(drawdown)
    WINRATE_GAUGE.set(winrate)


def get_metrics():
    """Devuelve métricas en formato Prometheus"""
    return generate_latest()
