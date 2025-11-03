# IMPLEMENTACIÓN DE MARTINGALA Y FOREX 1 MINUTO

## 📊 ANÁLISIS ESTADÍSTICO REALIZADO

### Resultados del Historial:
- **Total trades**: 50
- **Win Rate**: 52.0%
- **Racha máxima perdedora**: 4 pérdidas consecutivas
- **Probabilidad de 5 pérdidas seguidas**: 2.55% (muy baja)

### Recomendación Estadística:
✅ **Multiplicador óptimo**: 2.0x o 2.5x  
✅ **Profundidad máxima**: 5-6 niveles  
✅ **Monto base**: $0.10 USD

---

## 🔧 IMPLEMENTACIÓN

### 1. Soporte para Forex de 1 Minuto

**Archivo**: `engine/services/tick_trading_loop.py`

**Cambio**: Todos los símbolos que empiezan con `frx` ahora usan **60 segundos** (1 minuto) de duración.

```python
if symbol.startswith('frx'):
    # Forex: usar 1 minuto (60 segundos) para opciones binarias
    base = 60
    allowed = [60]  # 1 minuto para forex en binarias
```

---

### 2. Sistema de Martingala

#### Campos Agregados al Modelo (`engine/models.py`):

- `enable_martingale` (Boolean): Activar/desactivar martingala
- `martingale_multiplier` (Float, default: 2.0): Multiplicador después de pérdida
- `martingale_base_amount` (Decimal, default: 0.10): Monto base ($0.10)
- `martingale_max_levels` (Integer, default: 5): Profundidad máxima
- `martingale_reset_on_win` (Boolean, default: True): Resetear después de ganancia

#### Lógica de Martingala (`engine/services/advanced_capital_manager.py`):

**Funcionamiento**:
1. **Trade gana**: 
   - Si `reset_on_win = True` → Volver a nivel 0 (monto base)
   - Si `reset_on_win = False` → Mantener nivel actual

2. **Trade pierde**:
   - Aumentar nivel: `nivel += 1`
   - Calcular nuevo monto: `base_amount × (multiplier ^ nivel)`
   - Si alcanza `max_levels` → Resetear a nivel 0

**Ejemplo con multiplicador 2.0x**:
- Nivel 0: $0.10 (pierde) →
- Nivel 1: $0.20 (pierde) →
- Nivel 2: $0.40 (pierde) →
- Nivel 3: $0.80 (pierde) →
- Nivel 4: $1.60 (pierde o gana)

**Si gana en cualquier nivel**: Recupera todas las pérdidas anteriores + ganancia

---

### 3. Cálculo de Monto con Martingala

**Capital necesario para 4 pérdidas con 2.0x**:
- Nivel 1: $0.10
- Nivel 2: $0.20
- Nivel 3: $0.40
- Nivel 4: $0.80
- **Total**: $1.50

**Capital necesario para 5 pérdidas con 2.0x**:
- Nivel 1-4: $1.50
- Nivel 5: $1.60
- **Total**: $3.10

---

### 4. Protecciones Implementadas

✅ **Límite de profundidad**: Máximo 5 niveles (configurable)  
✅ **Límite de balance**: Si el monto excede el 95% del balance, resetea a nivel base  
✅ **Reset automático**: Después de ganancia (opcional)  
✅ **Monto mínimo**: $0.10 cuando martingala está activa (vs $1.00 normal)

---

## ⚙️ CONFIGURACIÓN

### Para Activar Martingala:

1. **Desde la base de datos**:
```python
from engine.models import CapitalConfig
config = CapitalConfig.get_active()
config.enable_martingale = True
config.martingale_multiplier = 2.0  # o 2.5
config.martingale_base_amount = Decimal('0.10')
config.martingale_max_levels = 5
config.martingale_reset_on_win = True
config.save()
```

2. **O usar position_sizing_method = 'martingale'**:
```python
config.position_sizing_method = 'martingale'
config.save()
```

---

## 📈 VENTAJAS Y RIESGOS

### ✅ Ventajas:
- **Recuperación de pérdidas**: Si gana después de pérdidas, recupera todo + ganancia
- **Monto inicial bajo**: $0.10 permite operar con poco capital
- **Aprovecha rachas perdedoras cortas**: Con win rate 52%, la probabilidad de 5 pérdidas es solo 2.55%

### ⚠️ Riesgos:
- **Requiere capital suficiente**: Para 5 pérdidas con 2.0x necesitas ~$3.10
- **Riesgo exponencial**: Cada nivel duplica el monto
- **Si alcanza el máximo**: Puede perder todo el capital invertido en la racha

### 🛡️ Protecciones Implementadas:
- **Profundidad máxima**: Evita rachas infinitas
- **Reset automático**: Reduce exposición después de ganancia
- **Validación de balance**: No permite montos que excedan el capital disponible

---

## 🎯 RECOMENDACIÓN FINAL

**Configuración óptima según estadísticas**:
- `enable_martingale`: `True`
- `martingale_multiplier`: `2.0` (más seguro) o `2.5` (más agresivo)
- `martingale_base_amount`: `0.10`
- `martingale_max_levels`: `5`
- `martingale_reset_on_win`: `True`

**Capital mínimo recomendado**: $5.00 USD (para cubrir hasta 5 niveles con 2.0x)

---

## 📝 NOTAS IMPORTANTES

1. **Forex de 1 minuto**: Todos los símbolos `frx*` ahora operan con duración de 60 segundos
2. **Monto mínimo**: Con martingala activa, el sistema permite montos desde $0.10 (vs $1.00 normal)
3. **Actualización automática**: El sistema actualiza el nivel de martingala cuando los contratos expiran
4. **Migración aplicada**: Los nuevos campos ya están en la base de datos

---

## ✅ PRÓXIMOS PASOS

1. Activar martingala desde la configuración de capital
2. Asegurar balance suficiente (mínimo $5.00 recomendado)
3. Reiniciar el trading loop para aplicar cambios
4. Monitorear el rendimiento y ajustar si es necesario

