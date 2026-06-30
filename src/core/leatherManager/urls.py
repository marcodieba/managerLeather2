from django.contrib import admin
from django.conf import settings
from django.urls import path, include
from django.conf.urls.static import static
from src.apps.fluxo.views import imprimir_rendimento_view
from src.apps.pedido.views import imprimir_pedido_view, dashboard_view

from src.apps.fluxo.views import busca_requisicao_ajax, ordem_servico_page

urlpatterns = [
    path('', dashboard_view, name='home'),
    path('admin/', admin.site.urls),
    
    # 🌟 A SUA ESCOLHA: A rota oficial da API para o React / Telemóvel
    path('api/', include('src.apps.fluxo.urls')),
    
    # Rotas de navegação normais do Django
    path("pedido/", include("src.apps.pedido.urls")),
    path("estoque_pq/", include("src.apps.estoque_pq.urls")),
    path('ordem-servico/', ordem_servico_page, name='ordem_servico_page'),
    path('busca/requisicao/', busca_requisicao_ajax, name='busca_requisicao_ajax'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)