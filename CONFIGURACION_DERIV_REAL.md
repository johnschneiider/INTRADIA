# 🔴 CONFIGURACIÓN DERIV PARA DATOS REALES

## ✅ Estado Actual:
- Dashboard funcionando
- Tabla histórica lista
- WebSocket activo
- Servicios corriendo

## ❌ Falta:
- Token API válido de Deriv
- Conexión funcional a Deriv
- Datos en tiempo real

---

## 📋 PASOS PARA OBTENER DATOS REALES DE DERIV:

### 1. Crear cuenta en Deriv
- Ve a: https://deriv.com/register
- Crea una cuenta (gratis, opción demo disponible)
- Verifica tu email

### 2. Obtener Token API
**Opción A: Token de aplicación**
- Ve a: https://app.deriv.com/
- Settings → API Token
- Genera un nuevo token
- Copia el token

**Opción B: Token demo (para testing)**
- Usa el token demo: ya tienes uno configurado
- Puede no funcionar si ha expirado

### 3. Configurar Token en tu proyecto

**Edita `connectors/deriv_client.py` línea 29:**
```python
self.api_token = 'TU_TOKEN_AQUI'
```

O crea archivo `.env` en raíz del proyecto:
```
DERIV_API_TOKEN=tu_token_aqui
```

### 4. Iniciar guardado de ticks
Ejecuta en una nueva terminal:
```bash
python scripts/save_realtime_ticks.py
```

### 5. Verificar que funciona
Abre otra terminal y ejecuta:
```bash
python manage.py shell -c "from market.models import Tick; print(f'Total ticks: {Tick.objects.count()}')"
```

Si ves ticks incrementando, está funcionando.

---

## 🎯 RESULTADO ESPERADO:

Si todo funciona correctamente:

**Terminal del script:**
```
✅ WebSocket conectado a Deriv
📊 Suscrito a R_10
📊 Suscrito a R_25
✅ Guardados 10 ticks nuevos
  R_10 @ 9.2345 - 14:30:15
  R_10 @ 9.2348 - 14:30:20
  ...
```

**Dashboard:**
- Precio actualizado cada segundo
- Tabla histórica mostrando nuevos ticks
- Datos en tiempo real

---

## ⚠️ SI NO FUNCIONA:

### Error: "No module named 'django'"
**Solución:** Activa el entorno virtual
```bash
cd E:\INTRADIA
.venv\Scripts\Activate.ps1
```

### Error: "Authentication failed"
**Solución:** Token no válido
- Genera nuevo token en Deriv
- Actualiza en el código

### Error: "Connection refused"
**Solución:** 
- Verifica conexión a internet
- Firewall bloqueando conexión
- Deriv down (verificar status)

---

## 📊 SÍMBOLOS DISPONIBLES EN DERIV:

- Volatility Indices: R_10, R_25, R_50, R_75, R_100
- Synthetic Indices: CRASH1000, BOOM1000, CRASH500, BOOM500
- Forex: EURUSD, GBPUSD, USDJPY, AUDUSD, etc.
- Commodities: GOLD, SILVER, OIL
- Cryptocurrencies: BTCUSD, ETHUSD

---

## 🔄 FLUJO DE DATOS:

```
Deriv WebSocket → save_realtime_ticks.py → Base de Datos → Dashboard
```

- Los ticks se guardan cada vez que llegan (tiempo real)
- El dashboard consulta la BD cada 2 segundos
- Verás los precios actualizados automáticamente

---

## 💡 PRÓXIMOS PASOS:

1. Obtener token válido de Deriv
2. Ejecutar `python scripts/save_realtime_ticks.py`
3. Ver dashboard: http://127.0.0.1:8000/engine/
4. Ver ticks en tabla histórica

**Una vez tengas datos reales, el sistema:**
- Mostrará precios actualizados
- Podrá hacer análisis técnico
- Podrá ejecutar operaciones automáticas
- Calculará métricas reales

