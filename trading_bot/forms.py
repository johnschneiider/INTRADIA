from django import forms
from .models import DerivAPIConfig


class DerivAPIConfigForm(forms.ModelForm):
    """Formulario para configurar la API de Deriv"""
    
    class Meta:
        model = DerivAPIConfig
        fields = [
            'api_token',
            'app_id',
            'is_demo',
            'is_active',
        ]
        widgets = {
            'api_token': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ingresa tu token de API Deriv',
            }),
            'app_id': forms.TextInput(attrs={
                'class': 'form-control',
            }),
            'is_demo': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'api_token': 'Token de API Deriv',
            'app_id': 'App ID',
            'is_demo': '¿Usar cuenta demo?',
            'is_active': '¿Activo?',
        }
        help_texts = {
            'api_token': 'Obtén tu token en app.deriv.com → Settings → API Token',
            'app_id': 'ID de la aplicación Deriv (por defecto: 1089)',
            'is_demo': 'Marca si tu token es para cuenta demo, desmarca para cuenta real',
            'is_active': 'Marca para activar esta configuración',
        }

