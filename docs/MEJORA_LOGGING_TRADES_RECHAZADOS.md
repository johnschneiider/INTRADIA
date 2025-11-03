# MEJORA DE LOGGING PARA TRADES RECHAZADOS

## 🔍 PROBLEMA IDENTIFICADO

**Síntoma:** Los trades pasan todos los filtros de estrategia (confidence 100%, score alto) pero son rechazados por Deriv.

**Trades rechazados observados:**
1. **RDBULL** - CALL - $1142.1003 - $1.00 - Rechazado a las 3:48:50 p.m.
2. **JD75** - PUT - $21802.9100 - $1.00 - Rechazado a las 3:59:26 p.m.
3. **RDBEAR** - CALL - $988.0709 - $1.00 - Rechazado a las 3:59:38 p.m.

**En los logs:**
- `📊 JD75: Momentum | Δ%: 0.0944% | PUT | Conf: 100.0% | Score: 2` ✅ (Pasa filtros)
- `📊 RDBEAR: Momentum | Δ%: 0.1342% | CALL | Conf: 100.0% | Score: 2` ✅ (Pasa filtros)
- `📊 RDBULL: Momentum | Δ%: 0.0389% | CALL | Conf: 97.5% | Score: 2` ✅ (Pasa filtros)

**Pero luego:** Trade rechazado sin razón clara en los logs.

---

## ✅ MEJORAS IMPLEMENTADAS

### 1. **Verificación de Conexión WebSocket Antes de Enviar**

**Antes:**
```python
# Enviar orden directamente sin verificar conexión
client.ws.send(json.dumps(buy_msg))
```

**Después:**
```python
# Verificar que WebSocket esté conectado antes de enviar orden
if not client.ws or not client.ws.sock or not client.ws.sock.connected:
    # Intentar reconectar si no está conectado
    if not client.authenticate():
        error_msg = f"WebSocket desconectado y falló reconexión"
        print(f"  ❌ {symbol}: {error_msg}")
        return {
            'accepted': False,
            'reason': 'ws_disconnected',
            'error_message': error_msg
        }
```

**Efecto:** Previene intentar enviar órdenes cuando el WebSocket está desconectado.

---

### 2. **Manejo de Errores al Enviar**

**Antes:**
```python
# No había try/catch al enviar
client.ws.send(json.dumps(buy_msg))
```

**Después:**
```python
try:
    client.response_event.clear()
    client.ws.send(json.dumps(buy_msg))
    print(f"  📤 {symbol}: Orden enviada a Deriv | {side.upper()} | ${amount:.2f} | {duration}s")
except Exception as send_error:
    error_msg = f"Error enviando orden: {send_error}"
    print(f"  ❌ {symbol}: {error_msg}")
    return {
        'accepted': False,
        'reason': 'send_error',
        'error_message': error_msg
    }
```

**Efecto:** Captura errores al enviar y proporciona información clara.

---

### 3. **Logging Detallado de Errores de Deriv**

**Antes:**
```python
if data.get('error'):
    print(f"  ❌ {symbol}: Error - {data['error']}")
    return {
        'accepted': False,
        'reason': f"ws_error: {data['error']}"
    }
```

**Después:**
```python
if data.get('error'):
    error_info = data['error']
    error_code = error_info.get('code', 'unknown') if isinstance(error_info, dict) else 'unknown'
    error_message = error_info.get('message', str(error_info)) if isinstance(error_info, dict) else str(error_info)
    
    # Log detallado del error
    print(f"  ❌ {symbol}: Deriv rechazó la orden | Código: {error_code} | Mensaje: {error_message}")
    
    return {
        'accepted': False,
        'reason': f"ws_error: {error_code}",
        'error_code': error_code,
        'error_message': error_message,
        'error_data': error_info
    }
```

**Efecto:** Muestra el código de error y mensaje específico de Deriv, facilitando el diagnóstico.

---

### 4. **Logging de Respuestas Inesperadas**

**Antes:**
```python
else:
    return {'accepted': False, 'reason': 'no_response'}
```

**Después:**
```python
else:
    # Si no hay 'buy' ni 'error', puede ser que la respuesta sea inesperada
    print(f"  ⚠️ {symbol}: Respuesta inesperada de Deriv: {data}")
    return {
        'accepted': False,
        'reason': 'no_response',
        'response_data': data
    }
```

**Efecto:** Muestra la respuesta completa cuando no hay 'buy' ni 'error', ayudando a identificar problemas.

---

### 5. **Mejora en Guardado de Errores en OrderAudit**

**Antes:**
```python
error_message=str(result) if not result.get('accepted') else ''
```

**Después:**
```python
error_message=result.get('error_message', result.get('error_data', {}).get('message', str(result))) if not result.get('accepted') else '',
error_code=result.get('error_code', '') if not result.get('accepted') else ''
```

**Efecto:** Guarda el mensaje de error específico y código de error en la base de datos.

---

## 📊 LOGS ESPERADOS DESPUÉS DE MEJORAS

### **Caso 1: WebSocket Desconectado**
```
📊 JD75: Momentum | Δ%: 0.0944% | PUT | Conf: 100.0% | Score: 2
❌ JD75: WebSocket desconectado y falló reconexión
```

### **Caso 2: Error de Deriv (Balance Insuficiente)**
```
📊 RDBEAR: Momentum | Δ%: 0.1342% | CALL | Conf: 100.0% | Score: 2
📤 RDBEAR: Orden enviada a Deriv | CALL | $1.00 | 30s
❌ RDBEAR: Deriv rechazó la orden | Código: InsufficientBalance | Mensaje: Insufficient balance to purchase this contract
```

### **Caso 3: Error de Deriv (Símbolo No Disponible)**
```
📊 RDBULL: Momentum | Δ%: 0.0389% | CALL | Conf: 97.5% | Score: 2
📤 RDBULL: Orden enviada a Deriv | CALL | $1.00 | 30s
❌ RDBULL: Deriv rechazó la orden | Código: InvalidSymbol | Mensaje: Symbol is not available for trading
```

### **Caso 4: Timeout**
```
📊 JD75: Momentum | Δ%: 0.0944% | PUT | Conf: 100.0% | Score: 2
📤 JD75: Orden enviada a Deriv | PUT | $1.00 | 30s
❌ JD75: Timeout esperando respuesta de Deriv (10s)
```

### **Caso 5: Respuesta Inesperada**
```
📊 RDBEAR: Momentum | Δ%: 0.1342% | CALL | Conf: 100.0% | Score: 2
📤 RDBEAR: Orden enviada a Deriv | CALL | $1.00 | 30s
⚠️ RDBEAR: Respuesta inesperada de Deriv: {'msg_type': 'ping', ...}
```

---

## 🎯 RESULTADO ESPERADO

Con estas mejoras, ahora podremos ver **exactamente por qué** Deriv está rechazando los trades:

1. **Código de error específico** (ej: `InsufficientBalance`, `InvalidSymbol`, `RateLimit`)
2. **Mensaje de error detallado** de Deriv
3. **Información completa** guardada en `OrderAudit` para análisis posterior

Esto permitirá:
- Identificar patrones en los rechazos
- Corregir problemas específicos (ej: balance insuficiente, símbolos no disponibles)
- Mejorar la lógica de validación antes de enviar órdenes

---

## 📝 NOTAS

- Los errores ahora se guardan con más detalle en `OrderAudit`
- El campo `error_code` almacena el código de error de Deriv
- El campo `error_message` almacena el mensaje de error completo
- El campo `error_data` (en `response_payload`) almacena toda la información del error

