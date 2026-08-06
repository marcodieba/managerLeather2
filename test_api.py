import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.core.leatherManager.settings')
django.setup()

from django.test import RequestFactory
from src.apps.pedido.api_views import api_pedidos_dashboard_producao

factory = RequestFactory()
request = factory.get('/pedido/imprimir/status-producao/')
# NOT authenticated

try:
    response = api_pedidos_dashboard_producao(request)
    print("Response status:", response.status_code)
    print("Response data:", response.data)
except Exception as e:
    print("Exception caught:", e)
