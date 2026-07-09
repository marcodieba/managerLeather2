from django.contrib import admin
from django.conf import settings
from django.urls import path, include
from django.conf.urls.static import static
from src.apps.fluxo.views import busca_requisicao_ajax, ordem_servico_page
from src.apps.pedido.views import dashboard_view
from src.apps.fluxo.views import ProcessoViewSet, RequisicaoViewSet, PedidoViewSet, FluxoRequisicaoViewSet, OperadorViewSet

pedidos_list = PedidoViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
pedidos_detail = PedidoViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})
processos_list = ProcessoViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
processos_detail = ProcessoViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})
requisicoes_list = RequisicaoViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
requisicoes_detail = RequisicaoViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})
fluxorequisicoes_list = FluxoRequisicaoViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
fluxorequisicoes_detail = FluxoRequisicaoViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})
operadores_list = OperadorViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
operadores_detail = OperadorViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})

urlpatterns = [
    path('pedidos/', pedidos_list, name='pedido-list'),
    path('pedidos/<int:pk>/', pedidos_detail, name='pedido-detail'),
    path('processos/', processos_list, name='processo-list'),
    path('processos/<int:pk>/', processos_detail, name='processo-detail'),
    path('requisicoes/', requisicoes_list, name='requisicao-list'),
    path('requisicoes/<int:pk>/', requisicoes_detail, name='requisicao-detail'),
    path('fluxorequisicoes/', fluxorequisicoes_list, name='fluxorequisicao-list'),
    path('fluxorequisicoes/<int:pk>/', fluxorequisicoes_detail, name='fluxorequisicao-detail'),
    path('operadores/', operadores_list, name='operador-list'),
    path('operadores/<int:pk>/', operadores_detail, name='operador-detail'),
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