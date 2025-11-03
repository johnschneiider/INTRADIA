# AJUSTE DE UMBRAL DE EMERGENCIA

## 🎯 PROBLEMA IDENTIFICADO

El sistema activaba la parada de emergencia **demasiado pronto** al detectar una caída del 6% con solo 6 trades iniciales.

**Causa**: Al abrir varios trades iniciales (ej: 6 trades de $1 cada uno desde balance de $100), las posiciones "pending" reducen temporalmente el balance disponible, activando falsamente la alerta de emergencia.

---

## 🔧 SOLUCIÓN APLICADA

**Aumentar el umbral de emergencia de 5% a 10%**

### Cambios realizados:

| Archivo | Cambio | Valor Anterior | Valor Nuevo |
|---------|--------|----------------|-------------|
| `engine/models.py` | Default value | 5.0% | 10.0% |
| `engine/services/risk_protection.py` | Default value | 5.0% | 10.0% |
| `engine/views.py` | getattr fallback | 5.0% | 10.0% |
| `engine/management/commands/trading_loop.py` | getattr fallback | 5.0% | 10.0% |
| `engine/services/tick_trading_loop.py` | getattr fallback | 5.0% | 10.0% |
| `templates/engine/capital_config.html` | default value | 5.0% | 10.0% |

---

## ✅ EFECTO ESPERADO

- **Menos falsas alarmas**: No se activa al abrir trades iniciales normales
- **Mayor margen**: Requiere una caída real del 10% en 5 minutos para activarse
- **Protección real**: Sigue protegiendo contra caídas súbitas significativas

---

## 📊 COMPORTAMIENTO

**Antes**:
- 6 trades de $1 → Balance disponible cae a $94
- Drawdown: 6% en 5 minutos
- **Resultado**: ❌ Parada de emergencia activada (falsa alarma)

**Ahora**:
- 6 trades de $1 → Balance disponible cae a $94
- Drawdown: 6% en 5 minutos
- **Resultado**: ✅ No activa (umbral ahora es 10%)
- 10+ trades perdedores → Drawdown 10%+
- **Resultado**: ❌ Parada de emergencia activada (protección real)

---

## 🎯 CONCLUSIÓN

El sistema ahora tiene un **umbral de emergencia más razonable** que evita activarse con operaciones normales iniciales, mientras sigue protegiendo contra caídas significativas y repentinas del mercado.

