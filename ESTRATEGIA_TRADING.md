# 📈 ESTRATEGIA DE TRADING ALGORÍTMICO

## 🎯 Estrategia Principal: Zones → Liquidity Sweep → Retest → Entry → Stop → TP

### 📊 Flujo de la Estrategia:

```
1. ZONAS DE LIQUIDEZ → 2. LIQUIDITY SWEEP → 3. RETEST → 4. ENTRY → 5. STOP → 6. TP
```

---

## 🔍 1. DETECCIÓN DE ZONAS DE LIQUIDEZ

### Criterios de Zonas:
- **Timeframe diario/semanal**: Identificar niveles de soporte/resistencia
- **ATR-based padding**: Zona = High/Low ± (0.5 * ATR)
- **Volumen confirmado**: Zona válida si hay volumen significativo
- **Múltiples toques**: Mínimo 2-3 toques para confirmar zona

### Implementación:
```python
def compute_zones(symbol, timeframe, candles):
    # Calcular ATR
    atr = calculate_atr(candles, 14)
    
    # Identificar highs/lows significativos
    highs = find_significant_highs(candles)
    lows = find_significant_lows(candles)
    
    # Crear zonas con padding ATR
    zones = []
    for high in highs:
        zone_high = high + (0.5 * atr)
        zone_low = high - (0.5 * atr)
        zones.append({
            'type': 'resistance',
            'high': zone_high,
            'low': zone_low,
            'strength': count_touches(zone_low, zone_high, candles)
        })
    
    return zones
```

---

## 🌊 2. DETECCIÓN DE LIQUIDITY SWEEP

### Criterios de Sweep:
- **Precio rompe zona**: High/Low de la vela supera zona
- **Retorno rápido**: Precio vuelve dentro de la zona en 1-3 velas
- **Volumen confirmado**: Sweep con volumen significativo
- **Tolerancia ATR**: eps = 0.2 * ATR(intraday)

### Implementación:
```python
def detect_liquidity_sweep(symbol, zone, candles):
    atr = calculate_atr(candles, 14)
    eps = 0.2 * atr
    
    for i, candle in enumerate(candles):
        # Sweep de resistencia
        if (candle.high > zone.high + eps and 
            candle.close < zone.high - eps):
            return {
                'type': 'bearish_sweep',
                'timestamp': candle.timestamp,
                'sweep_price': candle.high,
                'zone': zone
            }
        
        # Sweep de soporte
        if (candle.low < zone.low - eps and 
            candle.close > zone.low + eps):
            return {
                'type': 'bullish_sweep',
                'timestamp': candle.timestamp,
                'sweep_price': candle.low,
                'zone': zone
            }
    
    return None
```

---

## 🔄 3. RETEST DE ZONA

### Criterios de Retest:
- **Después del sweep**: Precio vuelve a tocar la zona
- **Rechazo confirmado**: Precio se aleja de la zona
- **Patrón de vela**: Doji, Hammer, Shooting Star
- **Volumen decreciente**: Menor volumen en el retest

### Implementación:
```python
def detect_retest(sweep, candles):
    sweep_time = sweep['timestamp']
    zone = sweep['zone']
    
    # Buscar en velas posteriores al sweep
    post_sweep_candles = candles[candles.timestamp > sweep_time]
    
    for candle in post_sweep_candles[:10]:  # Buscar en próximas 10 velas
        # Verificar si toca la zona
        if (zone.low <= candle.low <= zone.high or 
            zone.low <= candle.high <= zone.high):
            
            # Verificar rechazo
            if is_rejection_candle(candle, zone, sweep['type']):
                return {
                    'timestamp': candle.timestamp,
                    'entry_price': candle.close,
                    'zone': zone,
                    'sweep': sweep
                }
    
    return None
```

---

## 🎯 4. ENTRY (ENTRADA)

### Criterios de Entry:
- **Después del retest**: Confirmación de rechazo
- **Direction**: Opuesta al sweep
- **Entry offset**: 0.1 * ATR del precio de entrada
- **Risk/Reward**: Mínimo 1:2

### Implementación:
```python
def decide_entry_after_sweep(sweep_direction, zone, highs, lows, closes, volumes):
    atr = calculate_atr(closes, 14)
    
    if sweep_direction == 'bearish_sweep':
        # Entrada en corto después de sweep bajista
        entry_level = zone.high - (0.1 * atr)
        stop_loss = zone.high + (0.5 * atr)
        take_profit = entry_level - (2 * atr)  # R:R = 1:2
        
        return {
            'side': 'sell',
            'entry_level': entry_level,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_reward': 2.0
        }
    
    elif sweep_direction == 'bullish_sweep':
        # Entrada en largo después de sweep alcista
        entry_level = zone.low + (0.1 * atr)
        stop_loss = zone.low - (0.5 * atr)
        take_profit = entry_level + (2 * atr)  # R:R = 1:2
        
        return {
            'side': 'buy',
            'entry_level': entry_level,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_reward': 2.0
        }
    
    return None
```

---

## 🛡️ 5. STOP LOSS

### Criterios de Stop:
- **ATR-based**: Stop = 0.5 * ATR del precio de entrada
- **Más allá de la zona**: Stop debe estar fuera de la zona de liquidez
- **Máximo riesgo**: 1-2% del capital por trade
- **Trailing stop**: Activar después de 1:1 R:R

### Implementación:
```python
def calculate_stop_loss(entry_price, side, atr, zone):
    if side == 'buy':
        stop_loss = entry_price - (0.5 * atr)
        # Asegurar que esté fuera de la zona
        stop_loss = min(stop_loss, zone.low - (0.1 * atr))
    else:
        stop_loss = entry_price + (0.5 * atr)
        # Asegurar que esté fuera de la zona
        stop_loss = max(stop_loss, zone.high + (0.1 * atr))
    
    return stop_loss
```

---

## 🎯 6. TAKE PROFIT

### Criterios de TP:
- **Risk/Reward mínimo**: 1:2 (preferible 1:3)
- **Niveles múltiples**: TP1 (1:1), TP2 (1:2), TP3 (1:3)
- **ATR-based**: TP = Entry ± (R:R * ATR)
- **Trailing**: Mover TP a breakeven después de TP1

### Implementación:
```python
def calculate_take_profit(entry_price, side, atr, risk_reward=2.0):
    if side == 'buy':
        take_profit = entry_price + (risk_reward * atr)
    else:
        take_profit = entry_price - (risk_reward * atr)
    
    return take_profit
```

---

## 📊 INDICADORES TÉCNICOS UTILIZADOS

### 1. ATR (Average True Range):
```python
def calculate_atr(prices, period=14):
    high_low = high - low
    high_close = abs(high - close.shift())
    low_close = abs(low - close.shift())
    
    true_range = max(high_low, high_close, low_close)
    atr = true_range.rolling(window=period).mean()
    
    return atr
```

### 2. EMA (Exponential Moving Average):
```python
def calculate_ema(prices, period=20):
    return prices.ewm(span=period).mean()
```

### 3. SMA (Simple Moving Average):
```python
def calculate_sma(prices, period=20):
    return prices.rolling(window=period).mean()
```

### 4. RSI (Relative Strength Index):
```python
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi
```

---

## ⚙️ PARÁMETROS DE LA ESTRATEGIA

### Configuración Principal:
- **Timeframe diario**: Para detectar zonas
- **Timeframe intraday**: Para detectar sweeps (5m, 15m)
- **ATR Period**: 14
- **Zona padding**: 0.5 * ATR
- **Sweep tolerance**: 0.2 * ATR
- **Entry offset**: 0.1 * ATR
- **Stop loss**: 0.5 * ATR
- **Risk/Reward**: Mínimo 1:2

### Risk Management:
- **Max risk per trade**: 1-2% del capital
- **Max positions**: 3 simultáneas
- **Max drawdown**: 10%
- **Max exposure**: 6% del capital

---

## 🔄 FLUJO COMPLETO DE EJECUCIÓN

```
1. SCAN DIARIO (00:00 UTC):
   ├── Obtener velas diarias/semanales
   ├── Calcular zonas de liquidez
   └── Almacenar zonas en base de datos

2. SCAN INTRADIARIO (cada 5 minutos):
   ├── Obtener velas de 5m/15m
   ├── Detectar liquidity sweeps
   ├── Identificar retests
   └── Generar señales de entrada

3. EJECUCIÓN DE ÓRDENES:
   ├── Verificar risk management
   ├── Calcular posición size
   ├── Colocar orden en Deriv
   └── Registrar en auditoría

4. MONITOREO:
   ├── Seguir stops/takes
   ├── Actualizar métricas
   ├── Registrar resultados
   └── Ajustar parámetros si es necesario
```

---

## 📈 MÉTRICAS DE RENDIMIENTO

### KPIs Principales:
- **Win Rate**: % de trades ganadores
- **Risk/Reward**: Ratio promedio
- **Profit Factor**: Gross Profit / Gross Loss
- **Max Drawdown**: Máxima pérdida consecutiva
- **Sharpe Ratio**: Retorno ajustado por riesgo
- **Expectancy**: Ganancia promedio por trade

### Objetivos:
- **Win Rate**: > 40%
- **Risk/Reward**: > 1:2
- **Profit Factor**: > 1.5
- **Max Drawdown**: < 10%
- **Sharpe Ratio**: > 1.0

---

## 🚨 CIRCUIT BREAKER Y SEGURIDAD

### Condiciones de Parada:
- **Drawdown > 10%**: Parar trading automáticamente
- **Pérdidas consecutivas > 5**: Reducir tamaño de posición
- **Volatilidad extrema**: Suspender trading
- **Errores de API > 5**: Activar modo seguro

### Auditoría:
- **Registro completo**: Todas las operaciones
- **Hash de payload**: Integridad de datos
- **Timestamp preciso**: Para análisis posterior
- **Response completo**: Respuesta de Deriv API

---

**Esta estrategia está diseñada para ser sistemática, repetible y basada en principios sólidos de análisis técnico y gestión de riesgo.**
