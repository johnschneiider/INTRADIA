# DEBUG: TRADE RECHAZADO (REJECTED)

## 📊 INFORMACIÓN DEL TRADE RECHAZADO

**Símbolo:** RDBULL  
**Tipo:** CALL  
**Precio:** $1142.1003  
**Monto:** $1.00  
**Estado:** rejected  
**Hora:** 3:48:50 p.m.

---

## 🔍 POSIBLES CAUSAS DE RECHAZO

### 1. **Filtro de Confidence Mínima (Modo Conservador)**

El sistema está en **MODO CONSERVADOR** activado, lo que aumenta los umbrales de filtros:

**En los logs:**
```
❌ RDBULL: Momentum filtrado (Confidence 0.65 < mínimo 0.70)
```

**Análisis:**
- El sistema calcula primero la confidence inicial del momentum (`momentum['strength']`) = **0.65**
- El modo conservador requiere **confidence_minimum = 0.70**
- Como **0.65 < 0.70**, el trade se rechaza ANTES de calcular la confidence final con el score

**Problema identificado:**
El filtro de confidence mínima se aplica **ANTES** de calcular la confidence final con el score de confluencia. Esto significa que:

1. Confidence inicial (momentum): **0.65** ❌ (rechazado)
2. Si hubiera pasado, se calcularía confidence final con score: **0.97** (97.5%) ✅

**Código relevante:**
```python
# Línea 570: confidence = momentum['strength']  # 0.65
# Línea 573: if confidence < confidence_minimum:  # 0.65 < 0.70 ❌
# Línea 574: return None  # Rechazado aquí
# ...
# Línea 620: confidence = max(confidence, min(1.0, 0.35 + 0.2 * score))  # Esto nunca se ejecuta
```

---

### 2. **Filtros Adicionales que Pueden Rechazar**

#### a) **Filtro EMA (Exponential Moving Average)**
```python
# Línea 587-591: Si es CALL y precio está debajo de EMA
if ema and direction == 'CALL':
    if stats['current_price'] < ema * 1.000:
        print(f"❌ {symbol}: Momentum filtrado (CALL debajo de EMA)")
        return None
```

#### b) **Filtro RSI (Relative Strength Index)**
```python
# Línea 600-604: RSI debe estar alineado con la dirección
if rsi is not None and rsi_prev is not None:
    if direction == 'CALL' and not (rsi > rsi_prev):
        return None
```

#### c) **Filtro de Rachas**
```python
# Línea 607-610: Micro-confirmación por racha a favor
if direction == 'CALL' and up_streak < 2:
    return None
```

---

### 3. **Errores de Deriv API**

Si el trade pasa todos los filtros pero Deriv lo rechaza, puede ser por:

- **Balance insuficiente:** Aunque se valida antes, puede haber un desfase
- **Símbolo no disponible:** El símbolo puede no estar disponible en ese momento
- **Parámetros inválidos:** Duración, precio o monto fuera de los límites aceptables
- **Rate limiting:** Demasiadas solicitudes en poco tiempo

**Código que maneja errores de Deriv:**
```python
# Línea 668-673
if data.get('error'):
    print(f"  ❌ {symbol}: Error - {data['error']}")
    return {
        'accepted': False,
        'reason': f"ws_error: {data['error']}"
    }
```

---

## 🐛 PROBLEMA IDENTIFICADO: ORDEN DE FILTROS

### **Problema Actual:**
El filtro de confidence mínima se aplica **ANTES** de calcular la confidence final con el score de confluencia.

**Flujo actual (INCORRECTO):**
1. Calcular confidence inicial del momentum: **0.65**
2. **Aplicar filtro de confidence mínima: 0.65 < 0.70** ❌ → RECHAZADO
3. ~~Calcular confidence final con score~~ (nunca se ejecuta)
4. ~~Aplicar otros filtros (EMA, RSI, rachas)~~ (nunca se ejecuta)

**Flujo correcto (DEBERÍA SER):**
1. Calcular confidence inicial del momentum: **0.65**
2. Calcular confidence final con score: **0.97** (97.5%)
3. **Aplicar filtro de confidence mínima: 0.97 > 0.70** ✅ → PASA
4. Aplicar otros filtros (EMA, RSI, rachas)
5. Si todos pasan → Trade aceptado

---

## ✅ SOLUCIÓN PROPUESTA

**Mover el filtro de confidence mínima DESPUÉS de calcular la confidence final con el score:**

```python
# ANTES (INCORRECTO):
confidence = momentum['strength']  # 0.65
if confidence < confidence_minimum:  # 0.65 < 0.70 ❌
    return None
# ... cálculo de score ...
confidence = max(confidence, min(1.0, 0.35 + 0.2 * score))  # Nunca se ejecuta

# DESPUÉS (CORRECTO):
confidence = momentum['strength']  # 0.65
# ... cálculo de score ...
confidence = max(confidence, min(1.0, 0.35 + 0.2 * score))  # 0.97
if confidence < confidence_minimum:  # 0.97 > 0.70 ✅
    # Pasa el filtro
```

---

## 📝 LOGS ESPERADOS DESPUÉS DE CORRECCIÓN

**Antes:**
```
❌ RDBULL: Momentum filtrado (Confidence 0.65 < mínimo 0.70)
```

**Después:**
```
📊 RDBULL: Momentum | Δ%: 0.0389% | CALL | Conf: 97.5% | Score: 2 | ATR%: 0.040
✅ RDBULL CALL - Contract: 123456 - Balance: $99.00
```

---

## 🔧 PRÓXIMOS PASOS

1. **Revisar el código de `statistical_strategy.py`** (líneas 570-620)
2. **Mover el filtro de confidence mínima** después del cálculo del score
3. **Probar con un trade similar** para verificar que ahora pasa
4. **Monitorear logs** para confirmar que los trades se ejecutan correctamente

---

## 📊 RESUMEN

**Causa del rechazo:**
- Filtro de confidence mínima aplicado **ANTES** de calcular la confidence final con el score
- Confidence inicial (0.65) < Confidence mínima (0.70) → RECHAZADO
- Confidence final (0.97) nunca se calcula porque el trade ya fue rechazado

**Solución:**
- Mover el filtro de confidence mínima **DESPUÉS** del cálculo del score
- Esto permitirá que trades con score alto pasen, incluso si la confidence inicial es baja

