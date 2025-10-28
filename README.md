# 🚀 INTRADIA - Trading System v2.0

Sistema de trading automatizado con análisis de zones de liquidez, detección de liquidity sweeps y filtros bayesianos avanzados.

## 📋 Características

- ✅ Detección automática de zones de liquidez (Daily/Weekly)
- ✅ Identificación de liquidity sweeps (limpieza de stops)
- ✅ Sistema bayesiano de 9 filtros estadísticos
- ✅ Indicadores: MACD, RSI, Bollinger Bands, Estocástico, EMA
- ✅ Filtros de tendencia macro (EMA200) y volatilidad
- ✅ Límite de operaciones diarias por símbolo
- ✅ Gestión de riesgo con R:R mínimo 1.5
- ✅ Backtesting integrado

## 🌐 Producción

- **Dominio:** [www.vitalmix.com.co](https://www.vitalmix.com.co)
- **IP:** 92.113.39.100
- **Stack:** Django + Gunicorn + Nginx
- **Base de Datos:** PostgreSQL

## 📊 Win Rate Esperado

| Versión | Win Rate | Trades/Mes | Profit Factor |
|---------|----------|------------|---------------|
| v1.0 (Filtros básicos) | 50% | 114-144 | 1.0 |
| **v2.0 (Optimizado)** | **55-60%** | **70-100** | **1.3-1.5** |

## 🎯 Sistema de Filtros

El sistema utiliza un enfoque bayesiano combinando **9 indicadores**:

1. **Engulfing** (2.0) - Patrones de reversión
2. **MACD** (2.0) - Confirmación de impulso
3. **RSI** (1.5) - Condiciones extremas
4. **Bollinger Bands** (1.5) - Posición en volatilidad
5. **Estocástico** (1.0) - Sobrecompra/sobreventa
6. **EMA(10)** (1.0) - Tendencia corto plazo
7. **Volumen** (0.5) - Confirmación
8. **EMA(200)** (+1.0/-2.0) - Tendencia macro
9. **ATR Volatility** (-1.0) - Momentum

**Umbral de aceptación:** 5.5 / 11.0 (50% de confirmación mínima)

## 🚀 Inicio Rápido

### Desarrollo Local

```bash
# 1. Clonar repositorio
git clone https://github.com/johnschneiider/INTRADIA.git
cd INTRADIA

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar base de datos
python manage.py migrate

# 5. Crear superusuario
python manage.py createsuperuser

# 6. Iniciar servidor
python manage.py runserver
```

### Producción (VPS)

Ver **[DEPLOYMENT.md](./DEPLOYMENT.md)** para instrucciones completas.

## 📚 Documentación

- **[INDICE_DOCUMENTACION.md](./INDICE_DOCUMENTACION.md)** - Índice completo
- **[ESTRATEGIA_TECNICA_COMPLETA.md](./ESTRATEGIA_TECNICA_COMPLETA.md)** - Manual técnico (1069 líneas)
- **[MEJORAS_IMPLEMENTADAS.md](./MEJORAS_IMPLEMENTADAS.md)** - Optimizaciones v2.0
- **[RESEARCH_ESTADISTICAS_FILTROS.md](./RESEARCH_ESTADISTICAS_FILTROS.md)** - Investigación teórica

## 🔧 Configuración

### Variables de Entorno

Crear archivo `.env`:

```env
DEBUG=False
SECRET_KEY=tu-secret-key-aqui
DJANGO_ALLOWED_HOSTS=vitalmix.com.co,www.vitalmix.com.co,92.113.39.100

# Base de datos
POSTGRES_HOST=localhost
POSTGRES_DB=intradia
POSTGRES_USER=intradia
POSTGRES_PASSWORD=tu-password

# Deriv API
DERIV_API_TOKEN=tu-token
DERIV_ACCOUNT_ID=tu-account-id
```

## 📊 Estrategia

El sistema implementa la estrategia: **Zones → Liquidity Sweep → Retest → Entry**

**Flujo:**
1. Detectar zones de liquidez en timeframe diario/semanal
2. Esperar liquidity sweep (rompe y retorna)
3. Aplicar 9 filtros bayesianos
4. Si score >= 5.5, ejecutar orden con R:R >= 1.5

## 📈 Uso

### Terminal 1 - Trading Loop
```bash
python manage.py trading_loop
```

### Terminal 2 - Celery Worker (Opcional)
```bash
celery -A config worker -l info
```

### Terminal 3 - Celery Beat (Opcional)
```bash
celery -A config beat -l info
```

## 🛠️ Scripts Útiles

```bash
# Reiniciar métricas
python scripts/reset_all_orders.py

# Ver estado de órdenes
python scripts/check_orders_status.py

# Backtesting
python scripts/backtest.py

# Monitoreo
python scripts/monitor_trading.py
```

## 🔒 Seguridad

- ✅ `.gitignore` configurado
- ✅ Variables sensibles en `.env` (no en git)
- ✅ `DEBUG=False` en producción
- ✅ ALLOWED_HOSTS configurados

## 📦 Requisitos

- Python 3.11+
- Django 5.2+
- PostgreSQL (producción)
- Redis (opcional, para Celery)
- Nginx + Gunicorn (producción)

## 📞 Soporte

- **Repositorio:** [github.com/johnschneiider/INTRADIA](https://github.com/johnschneiider/INTRADIA)
- **Documentación:** Ver archivos `.md` en raíz del proyecto

## 📄 Licencia

Proyecto privado - Todos los derechos reservados

---

**Versión:** 2.0.0  
**Fecha:** 2025-01-28  
**Estado:** ✅ Production Ready
