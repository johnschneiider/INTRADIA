# 📐 ESTRATEGIA TÉCNICA COMPLETA - INTRADIA Trading System

## 🎯 Resumen Ejecutivo

Este documento describe en detalle técnico y matemático la estrategia de trading implementada en el sistema INTRADIA, que combina análisis de zonas de liquidez, detección de liquidity sweeps, y un sistema bayesiano de filtros estadísticos para generar señales de entrada con alta probabilidad de éxito.

---

## 📊 1. ARQUITECTURA GENERAL DEL SISTEMA

### 1.1 Flujo de Ejecución Principal

```python
PROCESS_TRADING_LOOP(symbol):
    // 1. OBTENER DATOS
    zone ← Obtener_Última_Zona(symbol)
    candles_intraday ← Obtener_Velas_M5(symbol, lookback=200)
    
    // 2. DETECTAR SWEEP
    sweep ← DETECT_LIQUIDITY_SWEEP(symbol, zone, candles_intraday)
    IF NOT sweep:
        RETURN {'status': 'no_sweep'}
    
    // 3. EVALUAR FILTROS
    decision ← DECIDE_ENTRY_AFTER_SWEEP(
        direction=sweep.direction,
        zone=zone,
        candles=candles_intraday,
        use_advanced_filters=True
    )
    
    IF NOT decision:
        RETURN {'status': 'no_entry'}
    
    // 4. EJECUTAR ORDEN
    order_response ← PLACE_ORDER_THROUGH_GATEWAY(
        symbol, decision.side, decision.entry_level,
        decision.stop_level, decision.tp_level
    )
    
    RETURN {'status': 'ordered', 'response': order_response}
```

### 1.2 Componentes del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    INTRADIA Trading System                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Zone        │───▶│  Sweep       │───▶│  Bayesian    │  │
│  │  Detector    │    │  Detector    │ динамика│  Filter      │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                   │                     │           │
│         ▼                   ▼                     ▼           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         INDICATOR CALCULATOR                        │    │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐         │    │
│  │  │ ATR │ │EMA  │ │RSI  │ │MACD │ │BB   │ ...     │    │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘         │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                   │
│                           ▼                                   │
│                  ┌─────────────────┐                         │
│                  │  Entry Decision │                         │
│                  │  Execution      │                         │
│                  └─────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗂️ 2. DETECCIÓN DE ZONAS DE LIQUIDEZ

### 2.1 Definición Matemática

Una **zona de liquidez** `Z` se define como un intervalo de precios `[Z_low, Z_high]` donde:

```
Z_low  = min(O_i, C_i)  - padding
Z_high = max(O_i, C_i)  + padding
Z_height = Z_high - Z_low
```

Donde:
- `O_i` = Precio de apertura del período `i` (diario/semanal)
- `C_i` = Precio de cierre del período `i`
- `padding` = Tolerancia basada en volatilidad

### 2.2 Algoritmo de Detección

```python
FUNCTION compute_zones(symbol, zone_period, candles):
    
    // Paso 1: Extraer OHLC del período
    O_period ← candles[0].open
    C_period ← candles[-1].close
    H_period ← MAX(candles.high)
    L_period ← MIN(candles.low)
    
    // Paso 2: Calcular ATR del período
    ATR_14 ← CALCULATE_ATR(candles, period=14)[-1]
    
    // Paso 3: Determinar zona base
    IF |O_period - C_period| < 0.2 * ATR_14:
        // Vela dentro del rango -> usar merging con padding
        Z_low ← L_period - 0.5 * ATR_14
        Z_high ← H_period + 0.5 * ATR_14
    ELSE:
        // Vela con movimiento claro
        Z_low ← MIN(O_period, C_period)
        Z_high ← MAX(O_period, C_period)
    
    Z_height ← Z_high - Z_low
    
    // Paso 4: Crear objeto Zone
    zone ← Zone(
        symbol=symbol,
        zone_period=zone_period,  // 'DAY' o 'WEEK'
        zone_low=Z_low,
        zone_high=Z_high,
        zone_height=Z_height,
        timestamp=candles[-1].timestamp
    )
    
    RETURN zone
```

### 2.3 Propiedades de las Zonas

**Condiciones de validez:**
- `Z_height > 0`: La zona debe tener ancho positivo
- `Z_height > 0.1 * ATR_14`: El ancho debe ser significativo vs volatilidad
- Al menos 2 toques previos: La zona debe haber sido probada

---

## 🌊 3. DETECCIÓN DE LIQUIDITY SWEEPS

### 3.1 Definición Matemática

Un **liquidity sweep** `S` es un evento donde el precio:

1. **Rompe temporalmente** una zona de liquidez `Z`
2. **Retorna rápidamente** dentro de la zona

**Ecuaciones para sweep alcista (dirección 'long'):**
```
Sweep Alcista:
    candle.low < (Z_low - ε)  ∧  candle.close ≥ Z_low
```

**Ecuaciones para sweep bajista (dirección 'short'):**
```
Sweep Bajista:
    candle.high > (Z_high + ε)  ∧  candle.close ≤ Z_high
```

Donde `ε` (epsilon) es la tolerancia de sweep:
```
ε = 0.2 * ATR_14(intraday)
```

### 3.2 Interpretación del Sweep

El sweep representa la **"limpieza de stops"**:

- **Sweep Alcista**: Los stops por debajo de `Z_low` son activados (líquidos barridos)
- **Sweep Bajista**: Los stops por encima de `Z_high` son activados (líquidos barridos)

**Hipótesis de mercado:**
Después de limpiar los stops, el precio tiende a **revertirse** en dirección opuesta al sweep, ya que:
1. Los operadores contrarios entran con stops limpios
2. Los grandes traders establecen posiciones esperando esta reversión
3. La zona de liquidez ahora actúa como soporte/resistencia reforzada

### 3.3 Algoritmo de Detección

```python
FUNCTION detect_liquidity_sweep(symbol, zone, intraday_candles):
    
    // Extraer series de precios
    highs ← [candle.high for candle in intraday_candles]
    lows ← [candle.low for candle in intraday_candles]
    closes ← [candle.close for candle in intraday_candles]
    
    // Calcular tolerancia epsilon
    ATR_intraday ← CALCULATE_ATR(highs, lows, closes, period=14)[-1]
    ε ← 0.2 * ATR_intraday
    
    // Buscar sweeps
    FOR EACH candle IN intraday_candles:
        
        // Sweep Alcista (limpieza de stops bajistas)
        IF candle.low < (zone.zone_low - ε) AND 
           candle.close >= zone.zone_low:
            RETURN SweepEvent(
                symbol=symbol,
                zone_id=zone.id,
                sweep_time=candle.timestamp,
                direction='long'
            )
        
        // Sweep Bajista (limpieza de stops alcistas)
        IF candle.high > (zone.zone_high + ε) AND 
           candle.close <= zone.zone_high:
            RETURN SweepEvent(
                symbol=symbol,
                zone_id=zone.id,
                sweep_time=candle.timestamp,
                direction='short'
            )
    
    RETURN None  // No se detectó sweep
```

### 3.4 Características del Sweep

**Sweep válido debe cumplir:**
1. **Rompe la zona**: Precio va más allá de la zona
2. **Retorna rápido**: El cierre de la vela está dentro de la zona
3. **Velocidad**: El retorno ocurre en la misma vela o máximo 2 velas
4. **Volumen**: Idealmente con volumen aumentado (confirmación)

---

## 📊 4. SISTEMA BAYESIANO DE FILTROS

### 4.1 Arquitectura del Sistema de Puntuación

El sistema utiliza un enfoque de **puntuación ponderada** basado en teoría bayesiana para combinar múltiples señales:

```
SCORE_TOTAL = Σ(w_i × signal_i) + Σ(w_j × penalty_j)
```

Donde:
- `w_i` = Peso del indicador `i` (positivo o negativo)
- `signal_i` = Valor binario del indicador (0 o 1)
- `penalty_j` = Penalización si el indicador contradice la señal

### 4.2 Indicadores del Sistema

El sistema evalúa **7 indicadores principales**:

| Indicador | Variable | Peso Base | Función |
|-----------|----------|-----------|---------|
| **Engulfing** | `E(t)` | `w_E = 2.0` | Patrón de reversión |
| **MACD** | `M(t)` | `w_M = 2.0` | Confirmación de impulso |
| **RSI** | `R(t)` | `w_R = 1.5` | Condiciones extremas |
| **Estocástico** | `S(t)` | `w_S = 1.0` | Sobrecompra/sobreventa |
| **Bollinger** | `B(t)` | `w_B = 1.5` | Posición en volatilidad |
| **EMA** | `E_MA(t)` | `w_{EMA} = 1.0` | Dirección de tendencia |
| **Volumen** | `V(t)` | `w_V = 0.5` | Confirmación de fuerza |

**Puntuación máxima teórica:** `MAX_SCORE = 10.0`

### 4.3 Cálculo de Puntuación: Pseudocódigo Detallado

```python
FUNCTION calculate_bayesian_score(
    direction: str,
    engulfing_pattern: str | None,
    macd_line: float,
    signal_line: float,
    rsi_val: float,
    stochastic_k: float,
    stochastic_d: float,
    bb_position: str,
    current_price: float,
    ema_value: float,
    volume_factor: float
) -> SignalScore:
    
    // Inicialización
    score := 0.0
    scores_dict := {}
    
    // ──────────────────────────────────────────────────────
    // 1. FILTRO ENGULFING
    // ──────────────────────────────────────────────────────
    IF engulfing_pattern IS NOT None:
        IF (direction == 'long' AND engulfing_pattern == 'bullish') OR
           (direction == 'short' AND engulfing_pattern == 'bearish'):
            scores_dict['engulfing'] := 2.0
            score += 2.0
        ELSE:
            scores_dict['engulfing'] := -1.0  // Contradice
            score -= 1.0
    ELSE:
        scores_dict['engulfing'] := 0.5
        score += 0.5  // Neutral
    
    // ──────────────────────────────────────────────────────
    // 2. FILTRO MACD (Moving Average Convergence Divergence)
    // ──────────────────────────────────────────────────────
    histogram := macd_line - signal_line
    
    IF direction == 'long':
        IF histogram > 0 AND macd_line > signal_line:
            scores_dict['macd'] := 2.0  // Impulso alcista
            score += 2.0
        ELIF histogram < 0 AND macd_line < signal_line:
            scores_dict['macd'] := -1.0  // Impulso bajista (contradice)
            score -= 1.0
        ELSE:
            scores_dict['macd'] := 0.5
            score += 0.5
    ELSE:  // direction == 'short'
        IF histogram < 0 AND macd_line < signal_line:
            scores_dict['macd'] := 2.0  // Impulso bajista
            score += 2.0
        ELIF histogram > 0 AND macd_line > signal_line:
            scores_dict['macd'] := -1.0  // Impulso alcista (contradice)
            score -= 1.0
        ELSE:
            scores_dict['macd'] := 0.5
            score += 0.5
    
    // ──────────────────────────────────────────────────────
    // 3. FILTRO RSI (Relative Strength Index)
    // ──────────────────────────────────────────────────────
    // RSI ∈ [0, 100]
    // < 30: sobreventa (posible rebote alcista)
    // > 70: sobrecompra (posible rebote bajista)
    
    IF direction == 'long':
        IF rsi_val < 30:
            scores_dict['rsi'] := 1.5  // Zona de rebote alcista
            score += 1.5
        ELIF rsi_val > 75:
            scores_dict['rsi'] := -0.5  // Muy sobrecomprado
            score -= 0.5
        ELSE:
            scores_dict['rsi'] := 0.5
            score += 0.5
    ELSE:  // short
        IF rsi_val > 70:
            scores_dict['rsi'] := 1.5  // Zona de rebote bajista
            score += 1.5
        ELIF rsi_val < 25:
            scores_dict['rsi'] := -0.5  // Muy sobrevendido
            score -= 0.5
        ELSE:
            scores_dict['rsi'] := 0.5
            score += 0.5
    
    // ──────────────────────────────────────────────────────
    // 4. FILTRO ESTOCÁSTICO
    // ──────────────────────────────────────────────────────
    // stochastic_k, stochastic_d ∈ [0, 100]
    // < 20: sobreventa
    // > 80: sobrecompra
    
    IF direction == 'long':
        IF stochastic_k < 20 AND stochastic_k > stochastic_d:
            scores_dict['stochastic'] := 1.0  // Confirmación cruzada
            score += 1.0
        ELIF stochastic_k > 80:
            scores_dict['stochastic'] := -0.5  // Contradice
            score -= 0.5
        ELSE:
            scores_dict['stochastic'] := 0.25
            score += 0.25
    ELSE:  // short
        IF stochastic_k > 80 AND stochastic_k < stochastic_d:
            scores_dict['stochastic'] := 1.0
 True
    score += 1.0
        ELIF stochastic_k < 20:
            scores_dict['stochastic'] := -0.5
            score -= 0.5
        ELSE:
            scores_dict['stochastic'] := 0.25
            score += 0.25
    
    // ──────────────────────────────────────────────────────
    // 5. FILTRO BOLLINGER BANDS
    // ──────────────────────────────────────────────────────
    // bb_position ∈ {'upper', 'middle', 'lower'}
    
    IF direction == 'long':
        IF bb_position == 'lower':
            scores_dict['bollinger'] := 1.5  // Precio cerca del extremo
            score += 1.5
        ELIF bb_position == 'middle':
            scores_dict['bollinger'] := 0.5
            score += 0.5
        ELSE:
            scores_dict['bollinger'] := 0.0
    ELSE:  // short
        IF bb_position == 'upper':
            scores_dict['bollinger'] := 1.5
            score += 1.5
        ELIF bb_position == 'middle':
            scores_dict['bollinger'] := 0.5
            score += 0.5
        ELSE:
            scores_dict['bollinger'] := 0.0
    
    // ──────────────────────────────────────────────────────
    // 6. FILTRO EMA (Exponential Moving Average)
    // ──────────────────────────────────────────────────────
    // EMA se usa para confirmar la dirección de la tendencia
    
    IF direction == 'long':
        IF current_price > 0.999 * ema_value:
            scores_dict['ema'] := 1.0  // Encima de EMA (alcista)
            score += 1.0
        ELSE:
            scores_dict['ema'] := 0.0
    ELSE:  // short
        IF current_price < 1.001 * ema_value:
            scores_dict['ema'] := 1.0  // Debajo de EMA (bajista)
            score += 1.0
        ELSE:
            scores_dict['ema'] := 0.0
    
    // ──────────────────────────────────────────────────────
    // 7. FILTRO VOLUMEN
    // ──────────────────────────────────────────────────────
    // volume_factor = V_actual / V_promedio
    
    IF volume_factor > 1.2:
        scores_dict['volume'] := 0.5  // Volumen alto confirma
        score += 0.5
    ELIF volume_factor > 0.8:
        scores_dict['volume'] := 0.25
        score += 0.25
    ELSE:
        scores_dict['volume'] := 0.0
    
    // ──────────────────────────────────────────────────────
    // NORMALIZAR Y EVALUAR
    // ──────────────────────────────────────────────────────
    IF score < 0:
        score := 0.0  // No permitir puntuación negativa
    
    max_score := 10.0
    passed := (score >= 4.0)  // Umbral mínimo: 40%
    
    confidence := score / max_score
    
    // Determinar calidad
    IF confidence >= 0.7:
        quality := 'high'
    ELIF confidence >= 0.5:
        quality := 'medium'
    ELSE:
        quality := 'low'
    
    RETURN SignalScore(
        total_score=score,
        max_score=max_score,
        score_breakdown=scores_dict,
        passed=passed,
        reason=f"Score: {score}/{max_score} | Quality: {quality}"
    )
```

### 4.4 Umbral de Aceptación

**Decisión de entrada:**
```
IF score_total >= 4.0:
    ENTRAR  // 40% de confirmación mínima
ELSE:
    RECHAZAR
```

**Clasificación de calidad:**
- **High**: `score ≥ 7.0` (70%+ de confirmación)
- **Medium**: `5.0 ≤ score < 7.0` (50-69%)
- **Low**: `4.0 ≤ score < 5.0` (40-49%)

---

## 🎯 5. CÁLCULO DE NIVELES DE ENTRADA

### 5.1 Parámetros Base

Una vez que se acepta una señal, se calculan los niveles de entrada:

**Para dirección 'long' (alcista):**
```
entry_level = Z_low + entry_offset
stop_level = Z_low - risk_distance
tp_level = entry_level + (RR_min × risk_distance)
```

**Para dirección 'short' (bajista):**
```
entry_level = Z_high - entry_offset
stop_level = Z_high + risk_distance
tp_level = entry_level - (RR_min × risk_distance)
```

Donde:
- `entry_offset` = Offset desde la zona
- `risk_distance` = Distancia al stop loss
- `RR_min` = Risk/Reward mínimo (típicamente 1.5 o 2.0)

### 5.2 Cálculo de Offset y Distancia de Riesgo

```python
FUNCTION calculate_entry_parameters(zone, atr_value):
    
    // Offset de entrada
    entry_offset := MIN(0.3 × ATR, 0.25 × Z_height)
    
 paracurricular zona := zona_height
    
    risk_distance := MAX(0.5 × ATR, 0.1 × Z_height)
    
    RETURN entry_offset, risk_distance
```

**Interpretación:**
- `entry_offset`: Permite evitar el rebote inmediato y entrar en la zona con seguridad
- `risk_distance`: Define el stop loss basado en la volatilidad (ATR) y el tamaño de la zona

### 5.3 Ejemplo Numérico

**Supuestos:**
- Zona de liquidez: `Z_low = 1.2000`, `Z_high = 1.2050`
- `Z_height = 0.0050` (50 pips)
- `ATR = 0.0020` (20 pips)
- Sweep alcista detectado
- `RR_min = 1.5`

**Cálculos:**
```
entry_offset = MIN(0.3 × 0.0020, 0.25 × 0.0050)
            = MIN(0.0006, 0.00125)
            = 0.0006  (6 pips)

risk_distance = MAX(0.5 × 0.0020, 0.1 × 0.0050)
              = MAX(0.0010, 0.0005)
              = 0.0010  (10 pips)

entry_level = 1.2000 + 0.0006 = 1.2006
stop_level = 1.2000 - 0.0010 = 1.1990
tp_level = 1.2006 + (1.5 × 0.0010) = 1.2021

Risk: 10 pips
Reward: 15 pips
R:R = 1:1.5
```

---

## 📈 6. CÁLCULO DE INDICADORES TÉCNICOS

### 6.1 ATR (Average True Range)

**Fórmula matemática:**
```
TR_i = MAX(
    H_i - L_i,
    |H_i - C_{i-1}|,
    |L_i - C_{i-1}|
)

ATR_n = EMA_n(TR)
```

Donde:
- `TR_i` = True Range de la vela `i`
- `H_i`, `L_i`, `C_i` = High, Low, Close de la vela `i`
- `EMA_n` = Media móvil exponencial de período `n` (default: 14)

**Propósito:** Medir la volatilidad del instrumento.

### 6.2 EMA (Exponential Moving Average)

**Fórmula matemática:**
```
EMA_t = α × P_t + (1 - α) × EMA_{t-1}

α = 2 / (n + 1)
```

Donde:
- `EMA_t` = EMA en tiempo `t`
- `P_t` = Precio en tiempo `t`
- `α` = Factor de suavizado
- `n` = Período

**Propósito:** Dar más peso a precios recientes.

### 6.3 RSI (Relative Strength Index)

**Fórmula matemática:**
```
RSI_t = 100 - (100 / (1 + RS_t))

RS_t = AG_t / AL_t

AG_t = Promedio de ganancias en los últimos n períodos
AL_t = Promedio de pérdidas en los últimos n períodos
```

Donde:
- `RS_t` = Relative Strength en tiempo `t`
- `AG_t` = Average Gain
- `AL_t` = Average Loss
- `n` = Período (default: 14)

**Interpretación: Magic Johnson**
- `RSI < 30`: Sobreventa (posible rebote alcista)
- `RSI > 70`: Sobrecompra (posible rebote bajista)
- `30 ≤ RSI ≤ 70`: Rango neutral

### 6.4 MACD (Moving Average Convergence Divergence)

**Componentes:**
```
MACD_Line = EMA_{12}(Price) - EMA_{26}(Price)
Signal_Line = EMA_9(MACD_Line)
Histogram = MACD_Line - Signal_Line
```

**Interpretación:**
- `MACD > Signal`: Momentum alcista
- `MACD < Signal`: Momentum bajista
- `Histogram > 0`: Aceleración de tendencia positiva
- `Histogram < 0`: Aceleración de tendencia negativa

### 6.5 Bollinger Bands

**Fórmula matemática:**
```
BB_Middle = SMA_n(Price)
BB_Upper = BB_Middle + (k × σ_n)
BB_Lower = BB_Middle - (k × σ_n)

σ_n = √(Σ(P_i - BB_Middle)² / n)
```

Donde:
- `SMA_n` = Media móvil simple de período `n` (default: 20)
- `σ_n` = Desviación estándar de los últimos `n` precios
- `k` = Multiplicador (default: 2.0)

**Interpretación:**
- Precio cerca de `BB_Upper`: Posible sobrecompra
- Precio cerca de `BB_Lower`: Posible sobreventa
- Ancho de bandas: Indicador de volatilidad

### 6.6 Estocástico

**Fórmula matemática:**
```
%K_t = ((C_t - LL_n) / (HH_n - LL_n)) × 100
%D_t = SMA_3(%K)

LL_n = Mínimo más bajo en los últimos n períodos
HH_n = Máximo más alto en los últimos n períodos
```

Donde:
- `%K_t` = Velocidad del movimiento
- `%D_t` = Media móvil de %K
- `n` = Período (default: 14)

**Interpretación:**
- `%K < 20`: Sobreventa
- `%K > 80`: Sobrecompra
- Cruce `%K > %D`: Momentum alcista
- Cruce `%K < %D`: Momentum bajista

---

## 🔍 7. CRITERIOS DE VALIDACIÓN Y FILTROS

### 7.1 Validaciones Pre-Entrada

**Checklist de validación:**

```
1. Zona válida:
   □ Existe una zona de liquidez activa
   □ Z_height > 0.1 × ATR
   □ Zona tiene al menos 2 toques históricos

2. Sweep detectado:
   □ Precio rompió la zona
   □ Precio retornó dentro de la zona
   □ Sweep ocurrió recientemente (< 24 horas)

3. Indicadores disponibles:
   □ ATR calculado correctamente
   □ Al menos 35 velas para MACD
   □ Al menos 20 velas para Bollinger
   □ Al menos 14 velas para RSI

4. Puntuación:
   □ score_total >= 4.0
   □ No hay contradicciones graves (score < 0)
```

### 7.2 Filtros de Rechazo

**Señal se rechaza si:**

1. **Filtro Engulfing contradictorio:**
   - `direction == 'long'` AND `engulfing == 'bearish'`
   - `direction == 'short'` AND `engulfing == 'bullish'`

2. **MACD en contra:**
   - `direction == 'long'` AND `histogram < 0`
   - `direction == 'short'` AND `histogram > 0`

3. **RSI en zona extrema contraria:**
   - `direction == 'long'` AND `rsi > 75`
   - `direction == 'short'` AND `rsi < 25`

4. **Puntuación insuficiente:**
   - `score_total < 4.0`

5. **Volumen insuficiente:**
   - `volume_factor < 0.5` (opcional, relajado para opciones binarias)

---

## 🎲 8. TEORÍA Y FUNDAMENTOS

### 8.1 Audacia Teórica del Liquidity Sweep

El concepto de **liquidity sweep** se basa en la teoría de:
1. **Market Microstructure**: Los grandes participantes colocan órdenes para activar stops
2. **Order Flow Imbalance**: Desequilibrios de liquidez que causan reversiones
3. **Smart Money Concept**: "Limpiar" stops antes de mover el precio en la dirección contraria

### 8.2 Probabilidad Bayesiana

El sistema utiliza un enfoque bayesiano para combinar evidencia:

```
P(Éxito | Señales) = P(Señales | Éxito) × P(Éxito) / P(Señales)
```

**Interpretación:**
- Cada indicador aumenta o disminuye la probabilidad de éxito
- Los pesos representan la importancia de cada evidencia
- La puntuación final estima la probabilidad de éxito

### 8.3 Hipótesis de Trading

**Hipótesis principal:**
> "Después de un liquidity sweep, el precio revierte en dirección opuesta con probabilidad > 65% si hay múltiples confirmaciones técnicas."

**Evidencia esperada:**
- Sweep alcista + confirmaciones → Entrada PUT (esperando caída)
- Sweep bajista + confirmaciones → Entrada CALL (esperando subida)

### 8.4 Gestión de Riesgo

**Parámetros de riesgo:**
- **Riesgo por trade**: 0.5% del capital
- **Stop Loss**: Basado en ATR (0.5 × ATR)
- **Take Profit**: Mínimo R:R = 1.5
- **Posiciones simultáneas**: Máximo 3

---

## 📊 9. FLUJO COMPLETO DE EJECUCIÓN

### 9.1 Diagrama de Secuencia Detallado

```
[Market Data]    [Zone Detector]    [Sweep Detector]    [Filter System]    [Execution]
      |                |                   |                    |                |
      ├───────────────>│                   │                    │                |
      │                │                   │                    │                |
      │            [Compute Zones]         │                    │                |
      │                │                   │                    │                |
      │<───────────────┤                   │                    │                |
      │                │                   │                    │                |
      ├───────────────────────────────────>│                    │                |
      │                │              [Detect Sweep]            │                |
      │                │                   │                    │                |
      │                │                   ├──────────────>│[Calculate Indicators]│
      │                │                   │                    │                |
      │                │                   │          [Calculate Score] │
      │                │                   │                    │                |
      │                │                   │                    ├───[Decide Entry]
      │                │                   │                    │                |
      │                │                   │                    │          [Place Order]
      │                │                   │                    │                |
      │<──────────────────────────────────────────────────────────────────────────┤
```

### 9.2 Pseudocódigo Completo

```python
FUNCTION execute_trading_loop(symbol):
    
    WHILE True:
        
        // 1. Obtener datos
        candles_daily ← GET_CANDLES(symbol, timeframe='D1', limit=50)
        candles_intraday ← GET_CANDLES(symbol, timeframe='M5', limit=200)
        
        // 2. Detectar/Generar zona
        zone ← GET_OR_CREATE_ZONE(
            symbol=symbol,
            candles=candles_daily
        )
        
        IF NOT zone:
            SLEEP(60 seconds)
            CONTINUE
        
        // 3. Detectar sweep en intraday
        sweep ← DETECT_LIQUIDITY_SWEEP(
            symbol=symbol,
            zone=zone,
            intraday_candles=candles_intraday
        )
        
        IF NOT sweep:
            SLEEP(30 seconds)
            CONTINUE
        
        // 4. Calcular indicadores
        series_intraday ← EXTRACT_SERIES(candles_intraday)
        
        ATR_series ← CALCULATE_ATR(series_intraday)
        MACD_data ← CALCULATE_MACD(series_intraday.closes)
        RSI_series ← CALCULATE_RSI(series_intraday.closes)
        BB_data ← CALCULATE_BOLLINGER_BANDS(series_intraday.closes)
        STOCH_data ← CALCULATE_STOCHASTIC(series_intraday)
        
        engulfing ← DETECT_ENGULFING(
            series_intraday.opens,
            series_intraday.closes
        )
        
        volume_factor ← CALCULATE_VOLUME_FACTOR(
            series_intraday.volumes,
            period=20
        )
        
        // 5. Calcular puntuación bayesiana
        signal_score ← CALCULATE_BAYESIAN_SCORE(
            direction=sweep.direction,
            engulfing_pattern=engulfing,
            macd_line=MACD_data['macd_line'][-1],
            signal_line=MACD_data['signal_line'][-1],
            rsi_val=RSI_series[-1],
            stochastic_k=STOCH_data['k_percent'][-1],
            stochastic_d=STOCH_data['d_percent'][-1],
            bb_position=DETERMINE_BB_POSITION(
                series_intraday.closes[-1],
                BB_data
            ),
            current_price=series_intraday.closes[-1],
            ema_value=CALCULATE_EMA(series_intraday.closes, 10)[-1],
            volume_factor=volume_factor
        )
        
        // 6. Validar puntuación
        IF NOT signal_score.passed:
            LOG("Señal rechazada: " + signal_score.reason)
            SLEEP(30 seconds)
            CONTINUE
        
        // 7. Calcular niveles
        ATR_value ← ATR_series[-1]
        entry_params ← CALCULATE_ENTRY_PARAMETERS(zone, ATR_value)
        
        decision ← EntryDecision(
            side=sweep.direction,  // 'buy' o 'sell'
            entry_level=zone.zone_low + entry_params.offset,
            stop_level=zone.zone_low - entry_params.risk_distance,
            tp_level=entry_level + (1.5 × entry_params.risk_distance),
            risk_percent=0.5,
            confidence_score=signal_score.total_score / signal_score.max_score,
            signal_quality=DETERMINE_QUALITY(signal_score)
        )
        
        // 8. Ejecutar orden
        order_response ← PLACE_ORDER_THROUGH_GATEWAY(
            symbol=symbol,
            side=decision.side,
            entry=decision.entry_level,
            stop=decision.stop_level,
            tp=decision.tp_level,
            risk_percent=decision.risk_percent
        )
        
        // 9. Registrar resultado
        LOG_ORDER(
            symbol=symbol,
            decision=decision,
            response=order_response,
            score_breakdown=signal_score.score_breakdown
        )
        
        SLEEP(60 seconds)  // Esperar antes del siguiente ciclo
```

---

## 🧪 10. METODOLOGÍA DE EVALUACIÓN

### 10.1 Métricas de Rendimiento

**KPIs principales:**

```
1. Win Rate (Tasa de acierto):
   WR = W / (W + L) × 100%
   Donde: W = ganadores, L = perdedores

2. Profit Factor:
   PF = Σ(Gains) / Σ(Losses)
   Objetivo: PF > 1.5

3. Sharpe Ratio:
   SR = (Return - Risk_free) / Volatility
   Objetivo: SR > 1.0

4. Expectancy:
   E = (WR × Avg_Win) - ((1-WR) × Avg_Loss)
   Objetivo: E > 0

5. Maximum Drawdown:
   MDD = (Peak - Trough) / Peak
   Objetivo: MDD < 10%
```

### 10.2 Evaluación de Filtros

**Análisis de contribución:**
```
Para cada indicador I:
    trades_with_I ← número de trades con I presente
    wins_with_I ← número de wins con I presente
    winrate_with_I ← wins_with_I / trades_with_I
    
    trades_without_I ← número de trades sin I
    wins_without_I ← número de wins sin I
    winrate_without_I ← wins_without_I / trades_without_I
    
    improvement_I ← winrate_with_I - winrate_without_I
```

**T-test de significancia:**
```
t_statistic = (winrate_with - winrate_without) / SE

SE = √(s²/n₁ + s²/n₂)
```

Si `|t_statistic| > 1.96` con `p < 0.05`, la mejora es estadísticamente significativa.

---

## 📚 11. REFERENCIAS Y FUENTES

### 11.1 Conceptos Teóricos

1. **Liquidity Sweep**: Tom Hougaard (Trading Psychology)
2. **Order Flow Analysis**: Market Microstructure Theory
3. **Smart Money Concept**: ICT (Inner Circle Trader)
4. **Bayesian Inference**: Probability Theory

### 11.2 Indicadores Técnicos

1. **RSI**: J. Welles Wilder (1978)
2. **MACD**: Gerald Appel (1970s)
3. **Bollinger Bands**: John Bollinger (1980s)
4. **ATR**: J. Welles Wilder (1978)

### 11.3 Gestión de Riesgo

1. **Kelly Criterion**: J.L. Kelly (1956)
2. **Modern Portfolio Theory**: Harry Markowitz (1952)
3. **VaR (Value at Risk)**: JPMorgan (1990s)

---

## ✅ 12. CONCLUSIÓN

Este documento describe técnicamente la estrategia de trading implementada en INTRADIA, que combina:

1. **Análisis de zonas de liquidez** para identificar niveles clave
2. **Detección de liquidity sweeps** para capturar la limpieza de stops
3. **Sistema bayesiano de filtros** para evaluar múltiples confirmaciones
4. **Gestión de riesgo** basada en ATR y relaciones risk/reward

**Objetivo:** Generar señales de alta calidad con win rate superior a 55% mediante filtros estadísticos que reducen falsas señales.

---

---

## 🚀 13. OPTIMIZACIONES IMPLEMENTADAS (v2.0)

### 13.1 Mejoras Críticas

**Versión 2.0** incluye las siguientes optimizaciones basadas en análisis cuantitativo:

#### 1. Umbral de Entrada Elevado
- **Versión 1.0**: `score >= 4.0` (40%)
- **Versión 2.0**: `score >= 5.5` (50% de puntuación máxima)
- **Justificación**: Reduce trades marginales en ~30-40%

#### 2. Filtro de Tendencia Macro
```
Nuevo filtro basado en EMA(200):

IF direction == 'long' AND price <= EMA_200:
    penalty = -2.0
    
IF direction == 'short' AND price >= EMA_200:
    penalty = -2.0
    
ELSE:
    bonus = +1.0
```

#### 3. Filtro de Volatilidad
```
atr_volatility_factor = ATR_actual / ATR_promedio_14

IF atr_volatility_factor < 0.8:
    penalty = -1.0
```

#### 4. Límite de Operaciones Diarias
```python
max_daily_trades_per_symbol = 5  # Configurable
```

### 13.2 Nueva Arquitectura de Puntuación

**Max Score**: 11.0 (antes 10.0)

| Componente | Puntos |
|------------|--------|
| Indicadores básicos | 10.0 |
| Trend filter positivo | +1.0 |
| **Máximo teórico** | **11.0** |

**Penalizaciones:**
- Trend contra: -2.0
- Volatilidad baja: -1.0
- Indicadores contra: -1.0 a -0.5

### 13.3 Impacto Esperado Tuee Mejoras

| Métrica | v1.0 | v2.0 | Mejora |
|---------|------|------|--------|
| Win Rate | 50% | **55-60%** | +5-10% |
| Trades | 114-144 | 70-100 | -30% |
| Profit Factor | 1.0 | **1.3-1.5** | +30-50% |
| P&L | Negativo | **Positivo** | ✅ |

---

**Versión:** 2.0.0  
**Fecha:** 2025-01-28  
**Estado:** ✅ OPTIMIZADA Y OPERATIVA  
**Autor:** INTRADIA Development Team

