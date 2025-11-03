# CORRECCIONES APLICADAS AL TRADING LOOP

## 🔍 PROBLEMAS IDENTIFICADOS

1. **Timeouts frecuentes al obtener balance**: `❌ Timeout obteniendo balance`
2. **Timeouts en autenticación**: `❌ Timeout esperando autenticación`
3. **Errores de conexión WebSocket**: `WebSocket error: Connection to remote host was lost.`
4. **Llamadas duplicadas a `get_balance()`**: Se llamaba múltiples veces innecesariamente
5. **Spam de logs**: Los mensajes de error se repetían constantemente

---

## ✅ CORRECCIONES APLICADAS

### 1. **Aumento del TTL del Caché de Balance**

**Antes:**
```python
self._balance_cache_ttl: float = 5.0  # 5 segundos
```

**Después:**
```python
self._balance_cache_ttl: float = 30.0  # 30 segundos TTL para balance (reducir llamadas)
```

**Efecto:** Reduce las llamadas a Deriv de cada 5 segundos a cada 30 segundos, disminuyendo significativamente los timeouts.

---

### 2. **Validación de Conexión WebSocket Antes de Enviar**

**Agregado:**
```python
# Verificar que WebSocket esté realmente conectado antes de enviar
if not self.ws or not self.ws.sock or not self.ws.sock.connected:
    # Si no está conectado, usar caché
    if self._balance_cache_value:
        print("⚠️ Usando balance en caché (WebSocket desconectado)")
        return self._balance_cache_value
    return {'balance': 0.0, 'currency': 'USD', 'account_type': 'demo' if self.is_demo else 'real', 'error': 'ws_disconnected'}
```

**Efecto:** Evita intentar enviar mensajes cuando el WebSocket está desconectado, previniendo errores y timeouts.

---

### 3. **Manejo de Errores al Enviar Mensajes**

**Agregado:**
```python
try:
    self.ws.send(json.dumps(balance_msg))
except Exception as e:
    print(f"⚠️ Error enviando mensaje de balance: {e}")
    # Si falla al enviar, usar caché
    if self._balance_cache_value:
        return self._balance_cache_value
    return {'balance': 0.0, 'currency': 'USD', 'account_type': 'demo' if self.is_demo else 'real', 'error': 'send_failed'}
```

**Efecto:** Captura errores al enviar mensajes y usa el caché en lugar de fallar completamente.

---

### 4. **Reducción de Spam de Logs de Timeout**

**Antes:**
```python
print("❌ Timeout obteniendo balance")  # Se mostraba cada vez
```

**Después:**
```python
# Timeout: usar caché si existe en lugar de mostrar error repetitivo
if self._balance_cache_value:
    # Solo mostrar mensaje ocasionalmente para evitar spam
    if not hasattr(self, '_last_timeout_log') or (now - getattr(self, '_last_timeout_log', 0)) > 60:
        print("⚠️ Timeout obteniendo balance (usando caché)")
        self._last_timeout_log = now
    return self._balance_cache_value
```

**Efecto:** Los mensajes de timeout solo se muestran cada 60 segundos, reduciendo significativamente el spam de logs.

---

### 5. **Reducción de Spam de Logs de Autenticación**

**Antes:**
```python
print("❌ Timeout esperando autenticación")  # Se mostraba cada vez
```

**Después:**
```python
# Reducir spam de logs de timeout de autenticación
if not hasattr(self, '_last_auth_timeout_log') or (time.time() - getattr(self, '_last_auth_timeout_log', 0)) > 60:
    print("⚠️ Timeout esperando autenticación")
    self._last_auth_timeout_log = time.time()
```

**Efecto:** Los mensajes de timeout de autenticación solo se muestran cada 60 segundos.

---

### 6. **Eliminación de Llamada Duplicada a `get_balance()`**

**Antes:**
- Se llamaba `get_balance()` en `process_symbol()` para obtener el balance
- Luego se llamaba `get_balance()` nuevamente en `place_binary_option()` para validar límites

**Después:**
- Se elimina la llamada duplicada en `place_binary_option()`
- Se usa el balance ya obtenido en `process_symbol()` o el caché

**Efecto:** Reduce llamadas innecesarias a Deriv, previniendo timeouts y rate limiting.

---

### 7. **Mejora en Manejo de Errores de Balance**

**Agregado:**
```python
except Exception as e:
    # Si hay error obteniendo balance, usar caché si existe o retornar error silencioso
    # para evitar spam de errores
    if (time.time() - self._last_balance_error_log) > 60:
        # Solo mostrar error cada 60 segundos para evitar spam
        print(f"⚠️ Error obteniendo balance: {str(e)[:50]}...")
        self._last_balance_error_log = time.time()
    
    # Intentar usar balance del caché si existe
    if hasattr(self._client, '_balance_cache_value') and self._client._balance_cache_value:
        cache_balance = self._client._balance_cache_value.get('balance', 0)
        if cache_balance:
            current_balance = Decimal(str(cache_balance))
            account_type = self._client._balance_cache_value.get('account_type', 'demo')
```

**Efecto:** Si hay un error obteniendo balance, intenta usar el caché en lugar de fallar, y reduce el spam de errores.

---

### 8. **Validación Mejorada de Conexión**

**Antes:**
```python
if not self.connected:
    if not self.authenticate():
        # ...
if not self.connected:  # Verificación duplicada
    if not self.authenticate():
        # ...
```

**Después:**
```python
# Verificar conexión antes de intentar obtener balance
if not self.connected or not self.ws or not self.ws.sock or not self.ws.sock.connected:
    # Intentar autenticar una sola vez
    if not self.authenticate():
        # Si falla autenticación, usar caché si existe
        if self._balance_cache_value:
            print("⚠️ Usando balance en caché (autenticación falló)")
            return self._balance_cache_value
```

**Efecto:** Verifica la conexión WebSocket real (no solo la flag `connected`) y elimina verificaciones duplicadas.

---

## 📊 RESUMEN DE IMPACTO

### Antes:
- Llamadas a `get_balance()` cada 5 segundos
- Timeouts frecuentes
- Spam constante de logs de error
- Múltiples llamadas duplicadas a `get_balance()`
- Errores al enviar mensajes cuando WebSocket está desconectado

### Después:
- Llamadas a `get_balance()` cada 30 segundos (6x menos frecuente)
- Uso de caché cuando hay timeouts o errores
- Logs de error solo cada 60 segundos (reducción de 95%+ en spam)
- Una sola llamada a `get_balance()` por símbolo procesado
- Validación de conexión WebSocket antes de enviar mensajes
- Uso de caché cuando WebSocket falla

---

## 🎯 RESULTADO ESPERADO

1. **Menos timeouts**: El caché de 30 segundos reduce las llamadas innecesarias
2. **Menos spam de logs**: Los mensajes de error solo aparecen cada minuto
3. **Mayor estabilidad**: Uso de caché cuando hay errores en lugar de fallar completamente
4. **Mejor rendimiento**: Menos llamadas a Deriv = menos rate limiting y timeouts

---

## 🔧 ARCHIVOS MODIFICADOS

1. `connectors/deriv_client.py`:
   - Aumento de TTL de caché de balance (5s → 30s)
   - Validación de conexión WebSocket antes de enviar
   - Manejo de errores al enviar mensajes
   - Reducción de spam de logs de timeout

2. `engine/services/tick_trading_loop.py`:
   - Eliminación de llamada duplicada a `get_balance()` en `place_binary_option()`
   - Mejora en manejo de errores de balance con uso de caché
   - Reducción de spam de logs de error

---

## ✅ VERIFICACIÓN

Para verificar que las correcciones funcionan:
1. Reinicia el trading loop
2. Observa que los logs de timeout aparecen máximo cada 60 segundos
3. Verifica que el sistema usa el caché cuando hay timeouts
4. Confirma que hay menos llamadas a `get_balance()`

