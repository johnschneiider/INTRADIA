"""Configuración de Channels para WebSocket"""
import os

# Configuración de Channels
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',  # Para desarrollo sin Redis
    },
}

