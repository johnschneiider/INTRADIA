INTRADIA - Estrategia de zonas → sweep → retest → entry

Requisitos
- Python 3.12
- SQLite (incluido con Python)

Configuración Local (Sin Docker)
1. Activar entorno virtual: `.venv\Scripts\activate` (Windows) o `source .venv/bin/activate` (Linux/Mac)
2. Aplicar migraciones: `python manage.py migrate`
3. Crear datos de ejemplo: `python manage.py create_dashboard_data`
4. Iniciar servicios (ver README_SIN_DOCKER.md para scripts)

Endpoints clave:
   - GET /api/status
   - GET /engine/status
   - GET /engine/metrics
   - POST /engine/orders
   - POST /engine/backtest/run
   - POST /engine/trader/kill
   - POST /engine/trader/policy/promote

Estrategia (MVP Rule-based)
- Zonas DAY/WEEK: detección según open/close y padding con ATR si cuerpo < 0.2*ATR
- Sweep: intradía (1m/5m/15m/1h) wick que toma liquidez ± eps (0.2*ATR) y cierra de vuelta dentro de la zona
- Retest+Entrada: entry_offset = min(0.3*ATR, 0.25*zone_height), confirmación por volumen (≥ 1.2 * media 20)
- Stop: max(0.5*ATR, 0.1*zone_height), TP: RR_min=1.5 si no hay target semanal
- Sizing: riesgo fijo por trade 0.5% del balance

Backtester
- Simula comisiones, slippage aleatorio (0.02%–0.1%) y latencia (50–300ms)
- Script: python scripts/backtest.py SYMBOL 5m

Modo paper (demo)
- scripts/run_paper_demo.sh (inicia web, worker, beat)
- Conector Deriv stub, con rate limiting, reintentos y circuit-breaker básico

Observabilidad
- /engine/metrics con métricas placeholder (extender con Prometheus)

Notas
- Por defecto ejecuta en modo demo. Pasar a real requiere credenciales y confirmación manual.

