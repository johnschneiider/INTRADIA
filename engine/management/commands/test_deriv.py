from django.core.management.base import BaseCommand
from connectors.deriv_client import DerivClient


class Command(BaseCommand):
    help = 'Probar conexión real con Deriv API'

    def handle(self, *args, **options):
        self.stdout.write("🔄 Probando conexión real con Deriv API...")
        
        client = DerivClient()
        
        # Probar autenticación
        self.stdout.write("🔐 Probando autenticación...")
        is_authenticated = client.authenticate()
        
        if is_authenticated:
            self.stdout.write(self.style.SUCCESS("✅ Autenticación exitosa"))
            
            # Probar balance
            self.stdout.write("💰 Obteniendo balance real...")
            balance = client.get_balance()
            self.stdout.write(f"Balance: {balance}")
            
            # Probar datos históricos
            self.stdout.write("📊 Obteniendo datos históricos reales...")
            candles = client.get_candles('EURUSD', '5m', 10)
            self.stdout.write(f"Velas obtenidas: {len(candles)}")
            if candles:
                self.stdout.write(f"Primera vela: {candles[0]}")
                self.stdout.write(f"Última vela: {candles[-1]}")
            
        else:
            self.stdout.write(self.style.ERROR("❌ Fallo en autenticación"))
            self.stdout.write("Verifica que el token DERIV_API_TOKEN esté configurado correctamente")
        
        self.stdout.write("\n🎯 Prueba completada")












