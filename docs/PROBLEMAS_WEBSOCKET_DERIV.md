# PROBLEMAS CON WEBSOCKET DE DERIV

## 🔍 PROBLEMAS IDENTIFICADOS

### 1. **Conexiones WebSocket Perdidas Frecuentemente**
```
WebSocket error: Connection to remote host was lost. - goodbye
```

**Causa:**
- Deriv está cerrando las conexiones WebSocket por inactividad
- Múltiples conexiones se crean simultáneamente sin reutilizar la misma conexión
- No hay heartbeat/ping para mantener la conexión viva

---

### 2. **Timeouts de Autenticación**
```
❌ Timeout esperando autenticación
⚠️ Deriv rechazó formato token:loginid, reintentando con token solo...
```

**Causa:**
- El formato `token:loginid` es rechazado por Deriv
- Se intenta reconectar pero falla por timeouts
- Múltiples intentos simultáneos de autenticación

---

### 3. **Múltiples Conexiones Simultáneas**

**Problema:**
- Cada llamada a `get_balance()` o `authenticate()` crea una nueva conexión WebSocket
- No se reutiliza la conexión existente
- Esto causa:
  - Rate limiting de Deriv
  - Conexiones perdidas
  - Timeouts frecuentes

---

## ✅ SOLUCIONES PROPUESTAS

### 1. **Reutilizar Conexión WebSocket Única**

**Antes:**
```python
# Cada vez que se llama get_balance(), se crea una nueva conexión
if not self.connected:
    self.authenticate()  # Crea nueva conexión
```

**Después:**
```python
# Reutilizar conexión existente si está viva
if not self._is_connection_alive():
    self._reconnect()
```

---

### 2. **Implementar Heartbeat/Ping**

**Problema:**
- Deriv cierra conexiones inactivas después de ~60 segundos
- No hay ping para mantener la conexión viva

**Solución:**
```python
def _start_heartbeat(self):
    """Enviar ping cada 30 segundos para mantener conexión viva"""
    def send_ping():
        while self.connected:
            time.sleep(30)
            if self.ws and self.ws.sock and self.ws.sock.connected:
                try:
                    self.ws.send(json.dumps({'ping': 1}))
                except:
                    self.connected = False
                    break
    threading.Thread(target=send_ping, daemon=True).start()
```

---

### 3. **Mejorar Detección de Conexión Viva**

**Problema:**
- El flag `self.connected` puede estar True pero la conexión real estar cerrada
- No se verifica el estado real del socket

**Solución:**
```python
def _is_connection_alive(self) -> bool:
    """Verificar si la conexión WebSocket está realmente viva"""
    if not self.ws or not self.connected:
        return False
    try:
        # Verificar estado real del socket
        if not self.ws.sock or not self.ws.sock.connected:
            return False
        # Opcional: enviar ping de prueba
        return True
    except:
        return False
```

---

### 4. **Implementar Pool de Conexiones o Singleton**

**Problema:**
- Múltiples instancias de `DerivClient` crean múltiples conexiones
- No hay un mecanismo para compartir la conexión

**Solución:**
```python
class DerivClient:
    _shared_connection = None
    _connection_lock = threading.Lock()
    
    def __init__(self, ...):
        # Si ya hay una conexión compartida, reutilizarla
        with self._connection_lock:
            if DerivClient._shared_connection is None:
                DerivClient._shared_connection = self
            else:
                # Reutilizar conexión existente
                self.ws = DerivClient._shared_connection.ws
                self.connected = DerivClient._shared_connection.connected
```

---

### 5. **Manejo Mejorado de Reconexión**

**Problema:**
- Cuando se pierde la conexión, se intenta reconectar pero falla
- No hay backoff exponencial para reintentos

**Solución:**
```python
def _reconnect_with_backoff(self, max_retries=3):
    """Reconectar con backoff exponencial"""
    for attempt in range(max_retries):
        try:
            if self.authenticate():
                return True
        except Exception as e:
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait_time)
    return False
```

---

## 📊 RECOMENDACIONES INMEDIATAS

1. **Usar una única conexión WebSocket global** compartida entre todas las instancias
2. **Implementar heartbeat/ping** cada 30 segundos
3. **Mejorar detección de conexión viva** antes de enviar mensajes
4. **Implementar backoff exponencial** para reconexiones
5. **Reducir frecuencia de llamadas** a `get_balance()` usando caché más largo

---

## 🔧 PRIORIDAD DE IMPLEMENTACIÓN

1. **ALTA**: Reutilizar conexión WebSocket única (evita múltiples conexiones)
2. **ALTA**: Implementar heartbeat/ping (mantiene conexión viva)
3. **MEDIA**: Mejorar detección de conexión viva (previene errores)
4. **MEDIA**: Backoff exponencial (mejora reconexiones)
5. **BAJA**: Pool de conexiones (optimización avanzada)

