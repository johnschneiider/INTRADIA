# Generated manually for scope fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trading_bot', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='derivapiconfig',
            name='scope_read',
            field=models.BooleanField(default=True, help_text='Ver actividad, ajustes, límites, historial, balance', verbose_name='Lectura'),
        ),
        migrations.AddField(
            model_name='derivapiconfig',
            name='scope_operate',
            field=models.BooleanField(default=True, help_text='Comprar/vender contratos, renovar caducados, recargar demo', verbose_name='Operar'),
        ),
        migrations.AddField(
            model_name='derivapiconfig',
            name='scope_payments',
            field=models.BooleanField(default=False, help_text='Retirar mediante agentes de pago, transferencias', verbose_name='Pagos'),
        ),
        migrations.AddField(
            model_name='derivapiconfig',
            name='scope_trading_information',
            field=models.BooleanField(default=True, help_text='Ver historial de operaciones', verbose_name='Información de Trading'),
        ),
        migrations.AddField(
            model_name='derivapiconfig',
            name='scope_admin',
            field=models.BooleanField(default=False, help_text='Abrir cuentas, gestionar ajustes y tokens', verbose_name='Administrador'),
        ),
    ]

