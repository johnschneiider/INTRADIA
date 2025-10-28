Suposiciones y parámetros por defecto

- Símbolos y timeframes disponibles son compatibles con Deriv demo.
- Comisiones por trade: 0.02% (configurable)
- Slippage aleatorio uniforme entre 0.02% y 0.1%
- Latencia aleatoria uniforme entre 50ms y 300ms
- Risk per trade: 0.5%
- RR mínimo: 1.5
- ATR periodo: 14
- Epsilon sweep: 0.2 * ATR intradía
- entry_offset: min(0.3*ATR, 0.25*zone_height)
- vol_factor: 1.2
- Kill switch desactiva ejecución y cerrará posiciones cuando se integre broker real

Limitaciones actuales
- Conector Deriv es un stub (paper). No coloca órdenes reales.
- Backtester minimalista: usa última zona disponible en lugar de rolling por período.
- Métricas en /engine/metrics son placeholders.

