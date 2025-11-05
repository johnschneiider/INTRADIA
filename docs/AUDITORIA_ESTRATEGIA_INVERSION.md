# 🔍 AUDITORÍA DE ESTRATEGIA DE INVERSIÓN

## Fecha: 2025-01-XX
## Sistema: INTRADIA - Bot de Trading Automatizado

---

## 📋 RESUMEN EJECUTIVO

La estrategia de inversión utiliza un **sistema híbrido multi-estrategia** con 4 estrategias diferentes que compiten por generar la mejor señal. El sistema incluye múltiples capas de filtros adaptativos, protección de riesgo y control de capital.

### ⚠️ HALLAZGOS PRINCIPALES

1. **✅ Fortalezas:**
   - Sistema multi-estrategia robusto
   - Filtros adaptativos dinámicos
   - Control de riesgo multicapa
   - Selección automática de mejor estrategia

2. **⚠️ Áreas de Mejora:**
   - Complejidad elevada (puede generar conflictos)
   - Umbrales de confianza variables por estrategia
   - Falta de validación cruzada entre estrategias
   - Algunos filtros pueden ser redundantes

---

## 🎯 ARQUITECTURA DE DECISIÓN

### 1. FLUJO DE DECISIÓN PRINCIPAL

```
┌─────────────────────────────────────────┐
│ 1. VALIDACIONES PRELIMINARES            │
│    - Balance suficiente ($1.00 mínimo) │
│    - Winrate últimos 20 trades >= 52%  │
│    - Top 5 símbolos si winrate < 52%   │
│    - No en pausa (drawdown < 15%)       │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│ 2. GENERACIÓN DE SEÑALES (4 estrategias)│
│    - Statistical Hybrid                 │
│    - EMA200 Extrema                     │
│    - Tick-Based                         │
│    - Momentum Reversal                  │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│ 3. SELECCIÓN DE MEJOR SEÑAL             │
│    - Elige la señal con mayor confianza │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│ 4. FILTROS DE VALIDACIÓN                │
│    - Confianza mínima (0.40-0.60)        │
│    - Modo conservador (0.58-0.62)       │
│    - Volatilidad (ATR)                  │
│    - Intervalo entre trades             │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│ 5. PROTECCIÓN DE RIESGO                 │
│    - Portfolio risk (15% máximo)        │
│    - Posiciones simultáneas (10 max)   │
│    - Correlación entre símbolos         │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│ 6. CÁLCULO DE MONTO                     │
│    - Basado en últimos 20 trades       │
│    - Rango: $0.35 - $1.00               │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│ 7. EJECUCIÓN                            │
└─────────────────────────────────────────┘
```

---

## 📊 ESTRATEGIAS IMPLEMENTADAS

### 1. STATISTICAL HYBRID STRATEGY (Principal)

**Ubicación:** `engine/services/statistical_strategy.py`

**Parámetros Base:**
- `z_score_threshold`: 2.5 desviaciones estándar
- `momentum_threshold`: 0.020% (2.0%)
- `confidence_minimum`: 0.6 (60%)
- `ticks_to_analyze`: 50 ticks

**Tipos de Señales:**

#### A) Mean Reversion (Reversión a la Media)
- **Condición:** `|z_score| > 2.5`
- **Lógica:** Precio desviado → esperar reversión
- **Filtros:**
  - ✅ Tendencia principal debe estar alineada
  - ✅ RSI extremo (80+ o 20-) rechaza
  - ✅ EMA muy cerca (< 0.0001%) rechaza
  - ✅ Confidence mínima adaptativa (0.6-0.8)

#### B) Momentum (Tendencias Continuas)
- **Condición:** Momentum confirmado + dirección clara
- **Lógica:** Seguir tendencia establecida
- **Filtros:**
  - ✅ Momentum > 0.35% (confidence inicial)
  - ✅ Tendencia principal alineada
  - ✅ Precio vs EMA (CALL > EMA, PUT < EMA)
  - ✅ RSI debe estar mejorando
  - ✅ Rachas mínimas (up_streak >= 1, down_streak >= 1)

**Confluencia de Señales:**
- Score = Suma de señales confirmadas (máx 3)
- Confidence = max(confidence_inicial, 0.35 + 0.2 × score)

---

### 2. EMA200 EXTREMA STRATEGY

**Ubicación:** `engine/services/ema200_extrema_strategy.py`

**Parámetros:**
- `lookback_ticks`: 200 ticks
- `extrema_window`: 60 ticks (EMA100 configurado)
- `ema_period`: 100

**Lógica:**
- Precio < EMA200 + cerca de máximo reciente → PUT
- Precio > EMA200 + cerca de mínimo reciente → CALL

**Confianza:**
- Distancia a EMA (40% peso)
- Cercanía al extremo (50% peso)
- Volatilidad (ATR) (10% peso)

**Umbral de Confianza:** 0.60 (60%)

---

### 3. TICK-BASED STRATEGY

**Ubicación:** `engine/services/tick_based_strategy.py`

**Parámetros:**
- `ticks_to_analyze`: 50 ticks
- `trend_threshold_pct`: 65% de ticks en misma dirección
- `force_threshold_pct`: 0.0008% de fuerza promedio

**Lógica:**
- Analiza últimos 50 ticks
- Calcula % de ticks alcistas vs bajistas
- Si >= 65% en una dirección → señal
- Fuerza = promedio de cambios porcentuales

**Umbral de Confianza:** 0.40 (40%) - **Más laxo**

---

### 4. MOMENTUM REVERSAL STRATEGY

**Ubicación:** `engine/services/momentum_reversal_strategy.py`

**Parámetros:**
- `fatigue_threshold`: 5 ticks consecutivos
- `momentum_extreme_threshold`: 0.05%
- `rsi_extreme_high`: 75.0
- `rsi_extreme_low`: 25.0

**Tipos de Señales:**
1. **Fatiga:** 5+ ticks consecutivos + momentum extremo
2. **Breakout:** Consolidación → ruptura (ATR x2)
3. **Momentum Extremo:** Movimiento extremo → reversión
4. **Divergencia:** Corto plazo vs largo plazo

**Umbral de Confianza:** 0.50 (50%)

---

## 🎯 SELECCIÓN DE MEJOR SEÑAL

**Lógica Actual:**
```python
# Compara todas las señales y elige la de mayor confianza
if signal_primary.confidence > signal_secondary.confidence:
    signal = signal_primary
else:
    signal = signal_secondary
```

**Problema Identificado:** 
- No valida si múltiples estrategias están de acuerdo
- Solo considera confianza, no consistencia
- Puede elegir señal aislada con alta confianza

**Recomendación:** 
- Considerar validación cruzada (2+ estrategias deben estar de acuerdo)
- O dar bonus de confianza si múltiples estrategias coinciden

---

## 🔍 FILTROS DE VALIDACIÓN

### 1. FILTRO DE CONFIANZA MÍNIMA

**Por Estrategia:**
- **Statistical Hybrid:** 0.50 (50%)
- **EMA200 Extrema:** 0.60 (60%)
- **Tick-Based:** 0.40 (40%) - **Más laxo**
- **Momentum Reversal:** 0.50 (50%)

**Modo Conservador:**
- Normal: 0.62 (62%)
- Recuperación: 0.58 (58%)
- Si sin trades 10 min: -0.04 (relajar)

**Problema:** Umbrales inconsistentes pueden generar señales débiles

---

### 2. FILTRO DE VOLATILIDAD (ATR)

**Forex (frx):**
- Rango: 0.00015 - 0.0220 (0.015% - 2.2%)
- Si fuera de rango → rechazar (a menos que confianza >= 0.75)

**Otros Símbolos:**
- Rango: 0.0015 - 0.0550 (0.15% - 5.5%)
- Misma lógica

**Problema:** Rangos muy específicos pueden rechazar oportunidades válidas

---

### 3. FILTRO DE INTERVALO ENTRE TRADES

**Lógica Dinámica:**
- Score >= 0.65 → 15 segundos
- Score <= 0.45 → 90 segundos
- Score medio → 30 segundos

**Problema:** Puede ser demasiado restrictivo para buenos símbolos

---

### 4. FILTRO DE TENDENCIA PRINCIPAL

**Implementado en:** Statistical Strategy

**Lógica:**
- Detecta tendencia principal (últimos ~50 ticks)
- Solo permite operar a favor de la tendencia
- Mean Reversion: Filtra PUT si tendencia es CALL y viceversa
- Momentum: Solo permite si está alineado

**Fortaleza:** ✅ Reduce operaciones contra-tendencia

---

## 🛡️ PROTECCIÓN DE RIESGO

### 1. PORTFOLIO RISK

**Límite:** 15% del capital total en riesgo
**Implementación:** ✅ Correcta

### 2. POSICIONES SIMULTÁNEAS

**Límite:** 10 posiciones activas máximo
**Implementación:** ✅ Correcta

### 3. CORRELACIÓN

**Grupos:**
- Índices: R_10, R_25, R_50, R_75, R_100
- Crypto: cryBTCUSD, cryETHUSD
- Booms/Crashes: BOOM500, CRASH500, etc.
- JP Indices: JD10, JD25, JD50, JD75

**Límite:** 10% máximo en símbolos correlacionados
**Implementación:** ✅ Correcta

---

## ⚙️ PARÁMETROS ADAPTATIVOS

### Modo Conservador (Activación)

**Condiciones:**
- Winrate < 52% (últimas 50 operaciones)
- Balance < balance inicial
- Drawdown > 5%
- Racha perdedora >= 3

**Ajustes:**
- Z-Score threshold: +25% (2.5 → 3.125)
- Momentum threshold: +33% (0.020 → 0.0266)
- Confidence mínima: +0.2 (0.6 → 0.8)

### Modo Normal

**Parámetros Base:**
- Z-Score: 2.5
- Momentum: 0.020%
- Confidence: 0.6

---

## 💰 CÁLCULO DE MONTO

**Nueva Lógica (Últimos 20 Trades):**

1. Calcula score de desempeño del activo específico:
   - Win rate (40% peso)
   - P&L promedio (40% peso)
   - Consistencia (20% peso)

2. Convierte score (0-1) a monto ($0.35 - $1.00):
   ```
   amount = 0.35 + (0.65 × score)
   ```

3. Redondea a 2 decimales

**Fallbacks:**
- Sin datos del activo → promedio de todos
- Sin datos históricos → $0.35 mínimo

**Implementación:** ✅ Correcta

---

## ⚠️ PROBLEMAS IDENTIFICADOS

### 1. **CONFLICTOS ENTRE ESTRATEGIAS**

**Problema:** 
- 4 estrategias pueden generar señales opuestas
- Solo se elige la de mayor confianza
- No hay validación cruzada

**Ejemplo:**
- Statistical: CALL (conf: 0.65)
- EMA200: PUT (conf: 0.70) ← Se elige esta
- Pero puede estar en contra de la tendencia principal

**Recomendación:**
- Si múltiples estrategias coinciden → bonus de confianza
- Si estrategias principales (Statistical + EMA200) están de acuerdo → priorizar

---

### 2. **UMBRALES DE CONFIANZA INCONSISTENTES**

**Problema:**
- Tick-Based: 0.40 (muy laxo)
- EMA200: 0.60 (estricto)
- Statistical: 0.50 (medio)

**Impacto:**
- Tick-Based puede generar muchas señales débiles
- EMA200 puede perder oportunidades válidas

**Recomendación:**
- Unificar umbrales base (0.55-0.60)
- O ajustar según tipo de mercado (tendencial vs lateral)

---

### 3. **FILTRO DE TENDENCIA PRINCIPAL INCOMPLETO**

**Problema:**
- Solo implementado en Statistical Strategy
- Otras estrategias no lo consideran

**Recomendación:**
- Aplicar filtro de tendencia principal a TODAS las estrategias
- O al menos a las principales (Statistical + EMA200)

---

### 4. **FALTA DE VALIDACIÓN DE CONFLUENCIA**

**Problema:**
- No valida si múltiples indicadores confirman la señal
- Puede entrar con solo un indicador positivo

**Recomendación:**
- Requerir mínimo 2 indicadores positivos:
  - Z-Score + Momentum
  - EMA + Extremo
  - Tendencia + RSI

---

### 5. **FILTRO DE VOLATILIDAD MUY ESTRICTO**

**Problema:**
- Rangos muy específicos (0.00015 - 0.0220 para forex)
- Puede rechazar oportunidades válidas en mercados laterales

**Recomendación:**
- Hacer rangos más flexibles
- O usar percentiles de volatilidad histórica

---

## ✅ FORTALEZAS DE LA ESTRATEGIA

1. **Sistema Multi-Estrategia:** Diversifica enfoques
2. **Filtros Adaptativos:** Se ajusta al rendimiento
3. **Control de Riesgo:** Múltiples capas de protección
4. **Selección de Símbolos:** Prioriza mejores activos
5. **Monto Dinámico:** Ajusta según desempeño
6. **Filtro de Tendencia Principal:** Reduce operaciones contra-tendencia

---

## 📈 RECOMENDACIONES DE MEJORA

### PRIORIDAD ALTA

1. **Validación Cruzada entre Estrategias**
   - Si 2+ estrategias coinciden → bonus de confianza +0.1
   - Si estrategias principales (Statistical + EMA200) están de acuerdo → priorizar

2. **Unificar Umbrales de Confianza**
   - Base: 0.55 para todas
   - Ajustar según modo conservador/normal

3. **Aplicar Filtro de Tendencia Principal a Todas las Estrategias**
   - Implementar en EMA200, Tick-Based y Momentum Reversal

### PRIORIDAD MEDIA

4. **Sistema de Confluencia**
   - Requerir mínimo 2 indicadores positivos
   - Score de confluencia (0-1) multiplica confianza

5. **Flexibilizar Filtro de Volatilidad**
   - Usar percentiles históricos (10-90%)
   - O rangos más amplios con advertencia

6. **Mejorar Selección de Estrategia**
   - Considerar no solo confianza, sino también:
     - Consistencia histórica de la estrategia
     - Win rate reciente de la estrategia
     - Alineación con tendencia principal

### PRIORIDAD BAJA

7. **Reducir Complejidad**
   - Evaluar si todas las estrategias son necesarias
   - Considerar desactivar estrategias con bajo win rate

8. **Logging Mejorado**
   - Registrar qué estrategia generó cada trade
   - Tracking de win rate por estrategia

---

## 🎯 CONCLUSIÓN

La estrategia actual es **robusta y bien estructurada**, con múltiples capas de protección y filtros adaptativos. Sin embargo, presenta **complejidad elevada** y algunos **conflictos potenciales** entre estrategias.

**Principales Fortalezas:**
- ✅ Sistema multi-estrategia sólido
- ✅ Filtros adaptativos dinámicos
- ✅ Control de riesgo efectivo
- ✅ Cálculo de monto basado en desempeño

**Principales Debilidades:**
- ⚠️ Falta validación cruzada entre estrategias
- ⚠️ Umbrales de confianza inconsistentes
- ⚠️ Filtro de tendencia principal incompleto
- ⚠️ Puede elegir señales aisladas sin confirmación

**Recomendación General:**
Implementar las mejoras de **Prioridad Alta** para mejorar la calidad de las señales y reducir falsos positivos.

---

## 📊 MÉTRICAS SUGERIDAS PARA MONITOREO

1. **Win Rate por Estrategia:**
   - Statistical Hybrid: __%
   - EMA200 Extrema: __%
   - Tick-Based: __%
   - Momentum Reversal: __%

2. **Tasa de Rechazo por Filtro:**
   - Confianza insuficiente: __%
   - Volatilidad fuera de rango: __%
   - Tendencia principal: __%
   - Portfolio risk: __%

3. **Confluencia de Estrategias:**
   - % de trades con 2+ estrategias de acuerdo
   - Win rate de trades con confluencia vs sin confluencia

---

*Documento generado automáticamente - Auditoría de Estrategia de Inversión*

