#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script para limpiar engine/views.py de caracteres corruptos"""

import re

# Leer el archivo
with open('engine/views.py', 'rb') as f:
    content = f.read()

# Decodificar ignorando errores
try:
    text = content.decode('utf-8')
except:
    text = content.decode('utf-8', errors='ignore')

# Buscar las funciones que tienen problemas
# Buscar desde services_logs_api hasta el final
pattern = r'def services_logs_api.*?(?=\n@login_required|\ndef |\Z)'
match = re.search(pattern, text, re.DOTALL)

if match:
    # Encontrar donde termina services_logs_api
    end_pos = match.end()
    
    # Buscar el siguiente bloque de funciones
    # Buscar desde active_trades_api
    active_trades_pattern = r'@login_required\s+def active_trades_api'
    close_trade_pattern = r'@login_required\s+@csrf_exempt\s+def close_trade_api'
    
    # Reemplazar caracteres corruptos en las funciones
    # Limpiar espacios extra y caracteres inválidos
    text_clean = text[:end_pos]
    
    # Agregar las funciones correctamente
    text_clean += '''

@login_required
def active_trades_api(request):
    """API para obtener trades activos/pendientes"""
    try:
        from monitoring.models import OrderAudit
        from django.utils import timezone
        
        # Obtener trades activos/pendientes
        active_trades = OrderAudit.objects.filter(
            status__in=['pending', 'active']
        ).order_by('-timestamp')[:50]
        
        trades_data = []
        for trade in active_trades:
            contract_id = None
            if trade.request_payload:
                contract_id = trade.request_payload.get('contract_id') or trade.request_payload.get('order_id')
            
            trades_data.append({
                'id': trade.id,
                'symbol': trade.symbol,
                'direction': trade.action.upper() if trade.action else 'N/A',
                'price': float(trade.price) if trade.price else 0.0,
                'amount': float(trade.size) if trade.size else 0.0,
                'timestamp': trade.timestamp.isoformat(),
                'status': trade.status,
                'contract_id': contract_id,
                'hours_ago': round((timezone.now() - trade.timestamp).total_seconds() / 3600, 2)
            })
        
        return JsonResponse({
            'success': True,
            'trades': trades_data,
            'count': len(trades_data)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
def close_trade_api(request):
    """API para cerrar un trade activo"""
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Método no permitido'
        }, status=405)
    
    try:
        import json
        from connectors.deriv_client import DerivClient
        from trading_bot.models import DerivAPIConfig
        from monitoring.models import OrderAudit
        
        data = json.loads(request.body)
        contract_id = data.get('contract_id')
        trade_id = data.get('trade_id')
        
        if not contract_id and not trade_id:
            return JsonResponse({
                'success': False,
                'error': 'Se requiere contract_id o trade_id'
            }, status=400)
        
        # Si solo tenemos trade_id, obtener contract_id del trade
        trade = None
        if not contract_id and trade_id:
            try:
                trade = OrderAudit.objects.get(id=trade_id)
                if trade.request_payload:
                    contract_id = trade.request_payload.get('contract_id') or trade.request_payload.get('order_id')
            except OrderAudit.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Trade no encontrado'
                }, status=404)
        
        if not contract_id:
            return JsonResponse({
                'success': False,
                'error': 'No se pudo obtener contract_id'
            }, status=400)
        
        # Obtener configuración de API
        config = DerivAPIConfig.objects.filter(is_active=True).first()
        if not config:
            return JsonResponse({
                'success': False,
                'error': 'No hay configuración de API activa'
            }, status=500)
        
        # Cerrar el contrato
        client = DerivClient(
            api_token=config.api_token,
            is_demo=config.is_demo,
            app_id=config.app_id
        )
        
        result = client.sell_contract(str(contract_id))
        
        if result.get('error'):
            return JsonResponse({
                'success': False,
                'error': result['error']
            }, status=500)
        
        # Actualizar el trade en la base de datos
        if trade_id:
            try:
                if not trade:
                    trade = OrderAudit.objects.get(id=trade_id)
                trade.status = 'won' if result.get('profit', 0) > 0 else 'lost'
                trade.pnl = Decimal(str(result.get('profit', 0)))
                
                # Guardar respuesta de la venta
                if not trade.response_payload:
                    trade.response_payload = {}
                trade.response_payload['sell_result'] = result
                
                trade.save()
            except OrderAudit.DoesNotExist:
                pass
        
        return JsonResponse({
            'success': True,
            'result': result,
            'message': f'Contrato {contract_id} cerrado exitosamente'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

'''
    
    # Guardar
    with open('engine/views.py', 'w', encoding='utf-8') as f:
        f.write(text_clean)
    print("✅ Archivo limpiado correctamente")
else:
    print("❌ No se encontró services_logs_api")

