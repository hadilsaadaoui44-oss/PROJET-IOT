import os
from django.apps import AppConfig


class AnalyzerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analyzer'

    def ready(self):
        # Éviter le double lancement avec l'autoreloader de Django
        if os.environ.get('RUN_MAIN') == 'true':
            from .services.n8n_manager import start_n8n
            start_n8n()
