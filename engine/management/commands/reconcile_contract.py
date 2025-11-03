from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Reconcilia manualmente un contrato (consulta Deriv y actualiza OrderAudit con won/lost).'

    def add_arguments(self, parser):
        parser.add_argument('contract_id', type=str, help='Contract ID en Deriv (por ejemplo, 70291360981)')

    def handle(self, *args, **options):
        contract_id = options['contract_id']

        # 1) Inicializar cliente Deriv usando la configuración activa en BD
        try:
            from connectors.deriv_client import DerivClient
            from trading_bot.models import DerivAPIConfig

            api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
            if not api_config:
                raise CommandError('No hay configuración de API activa en la base de datos.')

            client = DerivClient(
                api_token=api_config.api_token,
                is_demo=api_config.is_demo,
                app_id=api_config.app_id
            )
        except Exception as e:
            raise CommandError(f'Error inicializando DerivClient: {e}')

        # 2) Consultar estado del contrato (con pequeños reintentos)
        try:
            attempts = 3
            contract_info = None
            for _ in range(attempts):
                contract_info = client.get_open_contract_info(contract_id)
                if contract_info and not contract_info.get('error'):
                    break
            if not contract_info or contract_info.get('error'):
                err = contract_info.get('error') if isinstance(contract_info, dict) else 'unknown'
                raise CommandError(f'No se pudo obtener información del contrato: {err}')
        except Exception as e:
            raise CommandError(f'Fallo consultando contrato en Deriv: {e}')

        # 3) Buscar OrderAudit relacionado y actualizar
        try:
            from monitoring.models import OrderAudit

            since = timezone.now() - timedelta(days=1)
            qs = OrderAudit.objects.filter(
                timestamp__gte=since
            )

            trade = (
                qs.filter(response_payload__order_id=contract_id).first()
                or qs.filter(response_payload__contract_id=contract_id).first()
                or qs.filter(request_payload__order_id=contract_id).first()
            )

            if not trade:
                # Como fallback, intenta con status pendientes
                trade = (
                    OrderAudit.objects.filter(status__in=['pending', 'active', 'open']).order_by('-timestamp').first()
                )

            if not trade:
                raise CommandError('No se encontró un OrderAudit asociado al contract_id.')

            is_sold = bool(contract_info.get('is_sold'))
            profit = float(contract_info.get('profit', 0) or 0)
            sell_price = contract_info.get('sell_price')

            if is_sold:
                trade.status = 'won' if profit > 0 else 'lost'
                trade.pnl = profit
                if sell_price is not None:
                    try:
                        trade.exit_price = float(sell_price)
                    except Exception:
                        pass
                trade.save(update_fields=['status', 'pnl', 'exit_price'])
                status_txt = 'GANADA' if profit > 0 else 'PERDIDA'
                self.stdout.write(self.style.SUCCESS(f'✅ Contrato {contract_id} reconciliado: {status_txt} | P&L=${profit:.2f}'))
            else:
                self.stdout.write(self.style.WARNING(f'⏳ Contrato {contract_id} aún no aparece como vendido (is_sold=False).'))

        except CommandError:
            raise
        except Exception as e:
            raise CommandError(f'Error actualizando OrderAudit: {e}')


