# FIX: OPERACIONES NO APARECEN EN TABLA FINALIZADAS

## 🎯 PROBLEMA IDENTIFICADO

Las operaciones realizadas **no estaban quedando en la tabla de operaciones finalizadas** en la plantilla.

**Causa**: El sistema creaba trades con status `pending` pero **NO verificaba** si los contratos de Deriv habían expirado para actualizar el status a `won` o `lost`.

---

## 🔧 SOLUCIÓN APLICADA

### 1. Agregado `proposal_open_contract` al listener WebSocket

**Archivo**: `connectors/deriv_client.py`

El callback `on_message` ahora escucha también `proposal_open_contract`:

```python
if any(key in data for key in ['authorize', 'buy', 'proposal', 'balance', 'proposal_open_contract', 'error']):
    self.response_data = data
    self.response_event.set()
```

**Efecto**: Permite obtener información de contratos que expiraron.

---

### 2. Implementada verificación de contratos expirados en PositionMonitor

**Archivo**: `engine/services/position_monitor.py`

Nueva lógica en `monitor_active_positions()`:

```python
# Verificar si el contrato ha expirado en Deriv
contract_id = self._get_contract_id(position)
if contract_id:
    contract_info = self._client.get_open_contract_info(contract_id)
    if contract_info and not contract_info.get('error'):
        if 'status' in contract_info and contract_info['status'] in ['won', 'lost']:
            # El contrato se vendió/cerró, actualizar status
            self._update_position_status(position, contract_info)
```

**Nuevos métodos**:
- `_get_contract_id()`: Extrae el contract_id de response_payload
- `_update_position_status()`: Actualiza status, P&L y exit_price

---

### 3. Corregida lógica de determinación de status

**Archivo**: `connectors/deriv_client.py` (método `get_open_contract_info`)

**Antes**: Siempre retornaba 'won' o 'lost' aunque el contrato no hubiera expirado.

**Ahora**: Solo determina status si `is_sold == True`:

```python
is_sold = contract_info.get('is_sold', False)
profit = contract_info.get('profit', 0)

if is_sold:
    status = 'won' if profit > 0 else 'lost'
else:
    status = None  # Aún no expiró
```

---

## ✅ CÓMO FUNCIONA AHORA

### Flujo de verificación de trades:

1. **Trade se crea**: Status = `pending`
2. **Cada iteración del loop**: PositionMonitor verifica contratos activos
3. **Para cada contrato**:
   - Obtiene `contract_id` del `response_payload`
   - Llama a `get_open_contract_info(contract_id)` en Deriv
   - Si Deriv responde con `is_sold: true` y `profit` > 0 o < 0
   - Actualiza status a `won` o `lost` automáticamente
4. **Trade finalizado**: Aparece en tabla de "completadas"

### Intervalo de verificación:

- **Trading loop**: Verifica cada 10 segundos (intervalo actual)
- **PositionMonitor**: Se ejecuta al inicio de cada iteración

---

## 📊 CAMPOS ACTUALIZADOS

Cuando un contrato expira, se actualizan:

| Campo | Valor |
|-------|-------|
| `status` | 'won' o 'lost' |
| `pnl` | Profit/pérdida del contrato |
| `exit_price` | Precio al cierre (para opciones binarias es igual a entry) |

---

## ✅ RESUMEN DE CAMBIOS

| Archivo | Cambio | Descripción |
|---------|--------|-------------|
| `connectors/deriv_client.py` | on_message listener | Agregado 'proposal_open_contract' |
| `connectors/deriv_client.py` | get_open_contract_info() | Corregida lógica de status |
| `engine/services/position_monitor.py` | monitor_active_positions() | Verificación de contratos expirados |
| `engine/services/position_monitor.py` | _get_contract_id() | Extrae contract_id |
| `engine/services/position_monitor.py` | _update_position_status() | Actualiza status y P&L |

---

## 🎯 RESULTADO

✅ **Las operaciones ahora aparecen correctamente en la tabla de finalizadas** después de 30 segundos (duración del contrato).

✅ **El sistema verifica automáticamente el estado de los contratos** en cada iteración del trading loop.

✅ **Los trades se actualizan de `pending` a `won`/`lost`** sin intervención manual.

