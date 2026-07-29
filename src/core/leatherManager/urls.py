from django.contrib import admin
from django.conf import settings
from django.urls import path, include, re_path
from django.conf.urls.static import static
from src.apps.pedido.views import dashboard_view

urlpatterns = [
    path('', dashboard_view, name='home'),
    path('admin/', admin.site.urls),
    
    # 🌟 A SUA ESCOLHA: A rota oficial da API para o React / Telemóvel
    path('api/', include('src.apps.fluxo.urls')),
    
    # Rotas de navegação normais do Django
    path("pedido/", include("src.apps.pedido.urls")),
    path("estoque_pq/", include("src.apps.estoque_pq.urls")),

    # 👇 Roteamento para as páginas do React Frontend
    re_path(r'^(?:pedidos-internos|login|leitor|fluxo|requisicao)/?$', dashboard_view, name='react_frontend'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)