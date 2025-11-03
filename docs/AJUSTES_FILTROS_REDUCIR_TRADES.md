# AJUSTES DE FILTROS PARA REDUCIR TRADES

## 🎯 OBJETIVO
Reducir significativamente el número de trades ejecutados, manteniendo solo operaciones de alta calidad y confianza.

---

## 🔧 CAMBIOS REALIZADOS

### 1. Umbrales de Z-Score y Momentum (Más Estrictos)

**Antes**:
- Z-Score Threshold: `1.5`
- Momentum Threshold: `0.010` (1.0%)

**Ahora**:
- Z-Score Threshold: `2.5` (+67%)
- Momentum Threshold: `0.020` (2.0%) (+100%)

**Efecto**: Las señales deben ser más extremas y con mayor momentum para ejecutarse.

---

### 2. Confianza Mínima (Más Estricta)

**Antes**:
- Confidence Minimum (default): `0.3`
- Momentum confidence inicial: `>0.20`
- should_enter_trade threshold: `0.25`

**Ahora**:
- Confidence Minimum (default): `0.6` (+100%)
- Momentum confidence inicial: `>0.35` (+75%)
- should_enter_trade threshold: `0.50` (+100%)

**Efecto**: Solo se aceptan señales con confianza considerable.

---

### 3. Confluencia de Señales (Más Estricta)

**Antes**:
- Confluence score mínimo: `1`

**Ahora**:
- Confluence score mínimo: `2` (+100%)

**Efecto**: Se requieren múltiples indicadores alineados para ejecutar un trade.

---

### 4. Parámetros Adaptativos Base

**Antes**:
- base_z_score_threshold: `2.0`
- base_momentum_threshold: `0.015` (1.5%)
- base_confidence_minimum: `0.5`

**Ahora**:
- base_z_score_threshold: `2.5` (+25%)
- base_momentum_threshold: `0.020` (2.0%) (+33%)
- base_confidence_minimum: `0.6` (+20%)

**Efecto**: Los parámetros base ahora son más estrictos desde el inicio.

---

## 📊 RESUMEN DE UMBRALES

| Parámetro | Antes | Ahora | Cambio |
|-----------|-------|-------|--------|
| **Z-Score** | 1.5 | 2.5 | +67% |
| **Momentum** | 1.0% | 2.0% | +100% |
| **Confidence (default)** | 30% | 60% | +100% |
| **Confidence (momentum)** | 20% | 35% | +75% |
| **Confidence (entrada)** | 25% | 50% | +100% |
| **Confluence Score** | 1 | 2 | +100% |
| **Z-Score Base (Adapt)** | 2.0 | 2.5 | +25% |
| **Momentum Base (Adapt)** | 1.5% | 2.0% | +33% |
| **Confidence Base (Adapt)** | 50% | 60% | +20% |

---

## 🎯 EFECTO ESPERADO

### Reducción Estimada de Trades

Con estos ajustes, se espera una **reducción del 60-80%** en el número de trades ejecutados, ya que:

1. **Z-Score más alto**: Solo detección de condiciones extremas más significativas
2. **Momentum más fuerte**: Solo tendencias con fuerza considerable
3. **Confianza alta**: Solo señales con certeza elevada
4. **Mayor confluencia**: Requiere múltiples indicadores alineados

### Calidad vs Cantidad

- **Menos operaciones**: Reduce exposición al mercado y comisiones
- **Mayor calidad**: Solo operaciones con señales fuertes y confiables
- **Mejor win rate potencial**: Al operar solo en condiciones óptimas
- **Menor riesgo**: Menos frecuencia de trades = menor exposición

---

## 🔄 MODO CONSERVADOR

Cuando se active el modo conservador, los umbrales serán aún más estrictos:

| Parámetro | Normal | Conservador |
|-----------|--------|-------------|
| **Z-Score** | 2.5 | 3.125 |
| **Momentum** | 2.0% | 2.66% |
| **Confidence** | 60% | 80% |

---

## ✅ CONCLUSIÓN

**El sistema ahora es significativamente más selectivo**, ejecutando solo operaciones con:
- Condiciones extremas bien definidas (Z-Score alto)
- Momentum fuerte y confirmado
- Alta confianza (60%+)
- Múltiples indicadores alineados (confluencia)

Esto debería resultar en **menos trades pero de mayor calidad**.

