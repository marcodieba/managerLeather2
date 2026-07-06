import os
from celery import Celery

# Define o módulo de definições padrão do Django para o Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'leatherManager.settings')

app = Celery('leatherManager')

# Lê as configurações usando o prefixo 'CELERY_' no settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')

# Carrega as tarefas (tasks.py) de todas as aplicações registadas
app.autodiscover_tasks()
