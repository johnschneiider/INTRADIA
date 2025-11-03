# RESUMEN DETALLADO: MANEJO DE RIESGO CON WIN RATE BAJO

## 📊 Sistema de Gestión de Riesgo Adaptativo

El proyecto implementa un **Sistema Híbrido Adaptativo** que ajusta dinámicamente los filtros y el tamaño de posición cuando el rendimiento cae.

---

## 🎯 ACTIVACIÓN DEL MODO CONSERVADOR

El sistema activa el modo conservador cuando **cualquiera** de estos criterios se cumple:las operaciones realiz

### Criterios de Activación:
1. **Win Rate Global < 52%** (últimas 50 operaciones)
2. **Win Rate Reciente < 52%** (últimas 20 operaciones)
3. **Balance < Balance Inicial** (pérdida desde inicio de sesión)
4. **Drawdown > 5%** (pérdida desde el pico máximo)
5. **Racha Perdedora ≥ 3** (3 pérdidas consecutivas)

---

## 🔧 AJUSTES APLICADOS EN MODO CONSERVADOR

### 1. Ajuste de Umbrales de Filtros

Cuando se activa el modo conservador, los umbrales se hacen **más estrictos**:

| Parámetro | Modo Normal | Modo Conservador | Cambio |
|-----------|-------------|------------------|--------|
| **Z-Score Threshold** | 2.5 | 3.125 (aumenta 25%) | Más estricto |
| **Momentum Threshold** | 2.0% | 2.66% (aumenta 33%) | Más estricto |
| **Confidence Minimum** | 0.6 | 0.8 (aumenta +0.2) | Más estricto |

**Efecto:** Solo se ejecutan trades con señales **más fuertes y confiables**, reduciendo la cantidad de trades pero aumentando la calidad.

### 2. Reducción de Tamaño de Posición

El tamaño de posición se reduce **escalonadamente** según el drawdown:

| Drawdown | Multiplicador | Tamaño Final |
|----------|---------------|--------------|
| **< 5%** | 100% (1.0x) | Tamaño normal |
| **5% - 10%** | 75% (0.75x) | 25% de reducción |
| **10% - 15%** | 50% (0.5x) | 50% de reducción |
| **> 15%** | 25% (0.25x) | 75% de reducción |

**Ejemplo con Balance $100:**
- **Normal:** $1.00 por trade (1% del balance)
- **Drawdown 5-10%:** $0.75 por trade
- **Drawdown 10-15%:** $0.50 por trade
- **Drawdown >15%:** $0.25 por trade

**⚠️ IMPORTANTE:** Sin embargo, Deriv tiene un **mínimo de $1.00** por trade, por lo que:
- Si el cálculo da menos de $1.00, se ajusta al mínimo de $1.00
- **Pero el sistema debería rechazar el trade si el balance es insuficiente**

---

## 💰 CÁLCULO DEL MONTO POR TRADE

### Proceso de Cálculo (en orden):

1. **Capital Manager calcula riesgo base:**
   - Método: `kelly_fractional` (intenta Kelly, fallback a Fixed Fractional)
   - Risk Per Trade: **1.0%** del balance (fallback si Kelly no viable)
   - Ejemplo: Balance $100 → $1.00

2. **Aplicar multiplicador adaptativo:**
   - Según drawdown actual (ver tabla arriba)
   - Ejemplo: Drawdown 10% → Multiplicador 0.5x → $1.00 × 0.5 = **$0.50**

3. **Aplicar límites:**
   - **Mínimo:** $1.00 (requisito de Deriv)
   - **Máximo:** $1000.00 (configurable)
   - **Max Risk:** 2.0% del balance ($2.00 en balance de $100)

4. **Validación final:**
   - Si el monto calculado < $1.00 → Se ajusta a **$1.00**
   - Si el monto calculado > balance disponible → **Rechaza el trade**

---

## 🚨 PAUSADO AUTOMÁTICO DE TRADING

El sistema **pausa automáticamente** el trading cuando:

1. **Drawdown > 15%** (ya está en el nivel mínimo de posición: 25%)
2. **Racha Perdedora ≥ 5** (5 pérdidas consecutivas)

En estos casos, el sistema **no ejecuta nuevos trades** hasta que las condiciones mejoren.

---

## 📈 RECUPERACIÓN GRADUAL

Cuando el rendimiento mejora, el sistema sale del modo conservador **gradualmente**:

### Condiciones para Iniciar Recuperación:
1. **Win Rate Global ≥ 52%**
2. **Win Rate Reciente ≥ 52%**
3. **Balance ≥ Balance Inicial**
4. **Drawdown < 2%**

### Proceso de Recuperación:
- **Pasos:** 10 pasos graduales
- **Progreso:** Cada paso aumenta el progreso en 10%
- **Efecto:** Los umbrales se ajustan gradualmente de vuelta a valores normales
- **Cuando se completa:** Se restaura el modo normal completamente

---

## ⚠️ LIMITACIONES DE DERIV API

### Monto Mínimo por Trade:
Según la documentación oficial de Deriv:
- **Comisión mínima:** $0.10 USD/EUR/GBP (en la moneda de la cuenta)
- **Monto mínimo posible:** Técnicamente podría ser menor a $1.00 (por ejemplo, $0.10 + stake)
- **En la práctica:** El sistema está configurado con un **mínimo de $1.00** por trade

### Configuración Actual del Sistema:
- **Mínimo configurado:** $1.00 (en `min_position_size`)
- **Redondeo:** El código redondea el `amount` a 2 decimales antes de enviar a Deriv
- **Validación:** Si el monto calculado < $1.00, se ajusta al mínimo de $1.00

### Verificación en el Código:
```python
# En tick_trading_loop.py, línea 526:
amount = round(float(amount), 2)  # Redondea a 2 decimales

# El sistema usa min_position_size = $1.00 por defecto
```

### Impacto en el Sistema:
Si el sistema calcula un monto menor a $1.00 (por ejemplo, $0.50 con drawdown alto):
- El sistema **ajusta al mínimo de $1.00** configurado
- **PERO** si el balance es muy bajo (ej: $0.50), el trade será **rechazado** por balance insuficiente
- **Nota:** Aunque Deriv técnicamente podría aceptar montos menores, el sistema está configurado para un mínimo de $1.00

### Recomendación:
1. **Para balances bajos (< $10):**
   - Considerar pausar trading si drawdown > 10% (en lugar de intentar reducir a menos de $1.00)
   - O aumentar el mínimo de balance para operar

2. **Si se quiere aprovechar montos menores a $1.00:**
   - Verificar con Deriv que acepta el monto deseado (ej: $0.10, $0.50)
   - Ajustar `min_position_size` en la configuración del sistema
   - **ADVERTENCIA:** Operar con montos muy pequeños puede no ser viable debido a comisiones

3. **Para el uso actual:**
   - El sistema funciona correctamente con el mínimo de $1.00
   - La reducción de posición funciona bien con balances > $100
   - Con balances < $100, la reducción está limitada por el mínimo de $1.00

---

## 📋 EJEMPLO PRÁCTICO: Balance $100 con Win Rate 45%

### Escenario:
- Balance: $100.00
- Win Rate Global: 45% (bajo umbral de 52%)
- Drawdown: 8% (desde pico de $108.70)
- Racha Perdedora: 3 trades

### Actuación del Sistema:

1. **Se activa Modo Conservador** ✅
   - Win Rate < 52% ✓
   - Drawdown > 5% ✓
   - Racha perdedora ≥ 3 ✓

2. **Ajuste de Filtros:**
   - Z-Score: 2.0 → **2.5** (solo señales más fuertes)
   - Momentum: 1.5% → **2.0%** (solo momentum más fuerte)
   - Confidence: 0.5 → **0.7** (solo señales más confiables)

3. **Reducción de Tamaño:**
   - Cálculo base: $100 × 1% = $1.00
   - Multiplicador (drawdown 8%): **0.75x**
   - Monto ajustado: $1.00 × 0.75 = **$0.75**
   - **Ajuste al mínimo:** $0.75 → **$1.00** (mínimo de Deriv)

4. **Resultado:**
   - Tamaño de trade: **$1.00** (1% del balance)
   - Cantidad de trades: **Reducida** (filtros más estrictos)
   - Calidad de trades: **Mayor** (solo señales fuertes)

---

## 🔍 EJEMPLO PRÁCTICO: Balance $100 con Drawdown 12%

### Escenario:
- Balance: $100.00 (pico fue $113.64)
- Drawdown: 12%
- Modo Conservador: ACTIVO

### Actuación del Sistema:

1. **Reducción de Tamaño:**
   - Cálculo base: $100 × 1% = $1.00
   - Multiplicador (drawdown 12%): **0.5x** (nivel 10-15%)
   - Monto ajustado: $1.00 × 0.5 = **$0.50**
   - **Ajuste al mínimo:** $0.50 → **$1.00** (mínimo de Deriv)

2. **Resultado:**
   - Tamaño de trade: **$1.00** (1% del balance)
   - **Nota:** El sistema no puede reducir más debido al límite mínimo de Deriv

---

## 📊 RESUMEN DE MONTOS SEGÚN BALANCE Y DRAWDOWN

| Balance | Drawdown | Multiplicador | Cálculo | Monto Final |
|---------|----------|---------------|---------|-------------|
| $100 | < 5% | 1.0x | $1.00 × 1.0 | **$1.00** |
| $100 | 8% | 0.75x | $1.00 × 0.75 | **$1.00** ⚠️ |
| $100 | 12% | 0.5x | $1.00 × 0.5 | **$1.00** ⚠️ |
| $100 | 18% | 0.25x | $1.00 × 0.25 | **$1.00** ⚠️ |
| $200 | 8% | 0.75x | $2.00 × 0.75 | **$1.50** |
| $200 | 12% | 0.5x | $2.00 × 0.5 | **$1.00** |
| $200 | 18% | 0.25x | $2.00 × 0.25 | **$0.50** → **$1.00** ⚠️ |

**⚠️ = Ajustado al mínimo de $1.00 debido a límite de Deriv**

---

## 🎯 CONCLUSIONES

1. **El sistema reduce agresivamente el riesgo** cuando el win rate baja o hay drawdown
2. **Los filtros se hacen más estrictos** para mejorar la calidad de trades
3. **El tamaño de posición se reduce** según el drawdown, **pero está limitado por el mínimo de $1.00 de Deriv**
4. **Con balances bajos (< $100), la reducción de posición es limitada** debido al mínimo de Deriv
5. **El sistema pausa automáticamente** si el drawdown es extremo (>15%) o hay 5 pérdidas consecutivas
6. **La recuperación es gradual** para evitar volver demasiado rápido al modo agresivo

---

## 🔧 RECOMENDACIONES PARA MEJORAR EL SISTEMA

1. **Con balances bajos (< $50), considerar:**
   - Pausar trading si drawdown > 10% (en lugar de intentar reducir a menos de $1.00)
   - O aumentar el mínimo de balance para operar

2. **Ajustar el sistema para:**
   - Si el monto calculado < $1.00 y el balance es bajo, **rechazar el trade** en lugar de ajustar
   - Esto evitaría operar cuando el riesgo ajustado no es viable

3. **Considerar umbrales dinámicos:**
   - Aumentar el mínimo de posición permitido cuando hay drawdown alto
   - O simplemente pausar trading hasta que se recupere el balance

