# 📊 Investigación: Ecuaciones Estadísticas para Refinar Filtros de Entrada

## 🔬 Resumen Ejecutivo

Tras investigar métodos estadísticos aplicables a trading, se identificaron varias ecuaciones y enfoques que pueden mejorar los filtros de entrada actuales basados en:
- Zones → Liquidity Sweep → Retest
- Patrón Engulfing
- EMA, RSI, Z-Score (ya implementados)

---

## 📈 Ecuaciones Estadísticas Identificadas

### 1. **Bandas de Bollinger (Bollinger Bands)**

#### Ecuación Base:
```
BB_Upper = SMA(n) + (k × σ)
BB_Lower = SMA(n) - (k × σ)
BB_Middle = SMA Wiesbaden, Germany, during the early 1980s.

where:
- n = período (típicamente 20)
- σ = desviación estándar
- k = multiplicador (típicamente 2.0)
```

#### Aplicación como Filtro:
- **Filtro de Confirmación**: Solo entrar cuando el Engulfing se forma cerca de las bandas
- **Regla**: Engulfing alcista cerca de banda inferior + RSI < 30 = señal fuerte
- **Regla**: Engulfing bajista cerca de banda superior + RSI > 70 = señal fuerte

#### Ventaja Estadística:
- Usa desviación estándar para crear niveles dinámicos de soporte/resistencia
- Identifica condiciones extremas basadas en volatilidad histórica

---

### 2. **Índice de Fuerza Relativa (RSI)** - Mejora actual

#### Ecuación:
```
RS = Average Gain / Average Loss
RSI = 100 - (100 / (1 + RS))

where:
- Average Gain = promedio de aumentos de precio en n períodos
- Average Loss = promedio de disminuciones de precio en n períodos
- n = período (típicamente 14)
```

#### Filtros Adicionales Identificados:
1. **Divergencias con RSI**: Precio hace nuevo máximo pero RSI no → señal de debilidad
2. **RSI crude zones**: 
   - Zona extrema: < 10 o > 90 (muy fuerte)
   - Zona fuerte: < 20 o > 80 (fuerte)
   - Zona normal: 20-80 (neutral)

#### Implementación Sugerida:
```python
# Filtro adicional: Conflicto RSI
if direction == 'long' and rsi > 75:
    reject_signal("RSI demasiado alto para entrada alcista")
if direction == 'short' and rsi < 25:
    reject_signal("RSI demasiado bajo para entrada bajista")
```

---

### 3. **Media Móvil Convergencia Divergencia (MACD)**

#### Ecuación:
```
EMA_12 = Exponential Moving Average (12 períodos)
EMA_26 = Exponential Moving Average (26 períodos)
MACD Line = EMA_12 - EMA_26
Signal Line = EMA(9 períodos) of MACD Line
Histogram = MACD Line - Signal Line
```

#### Aplicación como Filtro:
- **Cruce MACD**: Solo entrar cuando MACD cruza señal en dirección esperada
- **Histograma Positivo**: MACD > Signal para CALL
- **Histograma Negativo**: MACD < Signal para PUT

#### Ventaja:
- Evalúa impulso mediante dos medias exponenciales
- Cruce de señales puede predecir giros de tendencia

---

### 4. **VWAP (Volume Weighted Average Price)**

#### Ecuación:
```
VWAP = Σ(Price × Volume) / Σ(Volume)

where:
- Price = precio de cada transacción
- Volume = volumen de cada transacción
```

#### Aplicación como Filtro:
- **Precio debajo de VWAP**: Sesgo bajista
- **Precio arriba de VWAP**: Sesgo alcista
- **Desviación de VWAP**: Diferencia porcentual indica fuerza

#### Filtro Sugerido:
```python
deviation = (price - VWAP) / VWAP * 100

# Si sweep alcista pero precio está muy por encima de VWAP (> 0.5%)
if direction == 'long' and deviation > 0.5:
    reject_signal("Precio demasiado sobrevalorado vs VWAP")
```

---

### 5. **Probabilidad Condicional (Bayesiana)**

#### Concepto:
Calcular la probabilidad de éxito dado múltiples confirmaciones.

#### Ecuación Base:
```
P(Éxito | Señales) = P(Señales | Éxito) × P(Éxito) / P(Señales)

where:
P(Éxito | Señales) = probabilidad de éxito dado las señales
P(Señales | Éxito) = probabilidad de ver estas señales cuando hay éxito
P(Éxito) = probabilidad base de éxito (winrate histórico)
P(Señales) = probabilidad de ver estas señales
```

#### Aplicación:
Calcular probabilidad de éxito cuando hay:
- Sweep detectado: P1
- Engulfing confirma: P2
- RSI en zona: P3
- EMA favorable: P4

#### Combinación de Probabilidades:
```python
# Probabilidad conjunta (simplificada)
p_success = (p1 sacue sweep × p2 engulfing × p3 rsi × p4 ema) / normalization_factor

# Umbral mínimo
if p_success < 0.65:  # 65% probabilidad mínima
    reject_signal("Probabilidad insuficiente")
```

---

### 6. **Estadístico de Sharpe Mejorado**

#### Ecuación:
```
Sharpe Ratio = (Return - Risk_free_rate) / Volatility

Adjusted Sharpe = Sharpe × √(número de señales válidas / número de señales totales)
```

#### Aplicación:
- **Filtro de Calidad**: Solo entrar cuando Adjusted Sharpe > 1.0
- **Filtro de Confianza**: Mayor Sharpe = mayor confianza en la entrada

---

### 7. **Prueba de Hipótesis (T-Student)**

#### Concepto:
Verificar si la diferencia entre medias es estadísticamente significativa.

#### Ecuación:
```
t = (μ1 - μ2) / √((s1²/n1) + (s2²/n2))

where:
μ1, μ2 = medias de dos grupos
s1, s2 = desviaciones estándar
n1, n2 = tamaños de muestra
```

#### Aplicación:
- **Comparar grupos**: Trades con Engulfing vs trades sin Engulfing
- **Verificar significancia**: t > 2.0 (p < 0.05) = diferencia significativa
- **Si significativo**: Usar Engulfing como filtro obligatorio
- **Si no significativo**: Engulfing no aporta valor estadístico

---

### 8. **Indicador Estocástico**

#### Ecuación:
```
%K = ((Close - Lowest Low) / (Highest High - Lowest Low)) × 100
%D = SMA(%K, 3 períodos)

where:
Lowest Low = mínimo de los últimos n períodos
Highest High = máximo de los últimos n períodos
n = período (típicamente 14)
```

#### Aplicación:
- **Sobreventa**: %K < 20 → señal de compra
- **Sobrecompra**: %K > 80 → señal de venta
- **Filtro cruzado**: %K cruza %D en dirección esperada

---

### 9. **Enfoque de Múltiples Confirmaciones (AND Logic)**

#### Filtro Compuesto:
```
ENTRADA = Sweep AND Engulfing AND RSI_Zone AND EMA_Direction AND Volume_Confirm

where:
- Cada condición es un filtro binario (0 o 1)
- Todos deben ser 1 para entrada
```

#### Ventaja:
- Reduce falsos positivos al requerir múltiples confirmaciones
- Aumenta precisión pero reduce frecuencia de señales

---

### 10. **Sistema de Puntuación (Score-based)**

#### Ecuación:
```
Score = w1×Sweep + w2×Engulfing + w3×RSI + w4×EMA + w5×Volume

where:
w1-w5 = pesos de cada factor (determinados por backtesting)
Sweep, Engulfing, etc = 0 o 1 (presencia de la señal)

Score_threshold = umbral mínimo (ej: 3.0 de 5.0)
```

#### Aplicación:
- **Puntuación Alta**: Mayor confianza en la señal
- **Puntuación Baja**: Rechazar entrada
- **Pesos**: Optimizar mediante machine learning o backtesting exhaustivo

---

## 🎯 Recomendaciones de Implementación Prioritarias

### Fase 1 (Impacto Alto - Dificultad Baja):
1. ✅ **Ajustar umbrales RSI** (ya implementado)
2. ✅ **Añadir MACD** como filtro adicional
3. ✅ **Ajustar filtro Engulfing** (solo cuando es significativo)

### Fase 2 (Impacto Medio - Dificultad Media):
4. **Bandas de Bollinger**: Filtrar entradas cerca de bandas
5. **Volumen**: Confirmar con volumen significativo
6. **Estocástico**: Detección de sobrecompra/sobreventa

### Fase 3 (Impacto Alto - Dificultad Alta):
7. **Probabilidad Bayesiana**: Combinar probabilidades de múltiples señales
8. **T-Student**: Verificar significancia estadística de filtros
9. **VWAP**: Validar precio contra volumen ponderado

### Fase 4 (Impacto Alto - Dificultad Muy Alta):
10. **Sistema de Puntuación**: Optimizar pesos mediante backtesting/ML
11. **Sharpe Ratio Ajustado**: Filtro de calidad de entrada

---

## 📊 Métricas para Evaluar Filtros

Para cada nuevo filtro, medir:
1. **Win Rate**: Antes vs después del filtro
2. **Profit Factor**: Ratio ganancias/pérdidas
3. **Sharpe Ratio**: Retorno ajustado por riesgo
4. **Frecuencia de Señales**: Cuántas señales se generan
5. **Diferencia Estadísticamente Significativa**: T-test para verificar mejora real

---

## 🔍 Ecuaciones de Validación

### Verificar Mejora del Win Rate:
```python
# Distribución binomial
from scipy import stats

# Antes del filtro: 45% win rate con 200 trades
n_before = 200
p_before = 0.45

# Después del filtro: 55% win rate con 150 trades
n_after = 150
p_after = 0.55

# ¿Es significativa la mejora?
t_stat, p_value = stats.ttest_ind_from_stats(
    mean1=p_before, std1=np.sqrt(p_before*(1-p_before)), nobs1=n_before,
    mean2=p_after, std2=np.sqrt(p_after*(1-p_after)), nobs2=n_after
)

if p_value < 0.05:
    print("Mejora estadísticamente significativa")
```

---

## 💡 Conclusión

Las ecuaciones más prometedoras para el sistema actual son:
1. **MACD**: Fácil de implementar, confirmación de impulso
2. **Bandas de Bollinger**: Contexto de volatilidad y extremos
3. **Sistema de Puntuación**: Permite optimización gradual
4. **Probabilidad Bayesiana**: Combina múltiples señales de forma inteligente

La clave es implementar gradualmente y **medir el impacto real** de cada filtro usando pruebas estadísticas.

