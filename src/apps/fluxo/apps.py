# apps/fluxo/apps.py
from django.apps import AppConfig

class FluxoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.apps.fluxo' #

    def ready(self):
        import src.apps.fluxo.signals # Importa os signals