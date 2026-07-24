# src/apps/fluxo/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import api_views

router = DefaultRouter()
router.register(r'pedidos', views.PedidoViewSet)
router.register(r'processos', views.ProcessoViewSet)
router.register(r'requisicoes', views.RequisicaoViewSet)
router.register(r'fluxorequisicoes', views.FluxoRequisicaoViewSet)
router.register(r'operadores', views.OperadorViewSet)
router.register(r'justificativas', views.JustificativaViewSet)

urlpatterns = [
    # ---------------------------------------------------------
    # CRUD PADRÃO DO REST FRAMEWORK (Já funciona perfeitamente)
    # ---------------------------------------------------------
    path('', include(router.urls)),
    
    # ---------------------------------------------------------
    # ROTAS LEGADAS (Manter ativas até o React substituir o HTML)
    # ---------------------------------------------------------
    path("imprimir/", views.imprimir_rendimento_view, name="imprimir_rendimento"),
    path("imprimir/maquina/", views.imprimir_maquina_view, name="imprimir_maquina"),
    path("imprimir/relatorio-geral/", views.imprimir_relatorio_geral_view, name="imprimir_relatorio_geral"),
    path('ordem-servico/', views.ordem_servico_page, name='ordem_servico_page'),
    path('busca/requisicao/', views.busca_requisicao_ajax, name='busca_requisicao_ajax'),
    path('resumo-lotes/', views.resumo_lotes_ativos_view, name='resumo_lotes'),
    
    # API EXCELENTE JÁ EXISTENTE
    path('movimentacao/qrcode/', views.ler_qrcode_movimentacao, name='ler_qrcode'),
    path('movimentacao/ajustar_anterior/', views.ajustar_processo_anterior, name='ajustar_anterior'),
    
    # ---------------------------------------------------------
    # NOVAS APIS PARA O REACT
    # ---------------------------------------------------------
    path('v1/busca-requisicao/', api_views.api_busca_requisicao, name='api_v1_busca_requisicao'),
    path('v1/resumo-lotes/', api_views.api_resumo_lotes_ativos, name='api_v1_resumo_lotes'),
    path('v1/relatorio-rendimento/', api_views.api_imprimir_rendimento, name='api_v1_imprimir_rendimento'),
    path('v1/calcular-ordem-servico/', api_views.api_calcular_ordem_servico, name='api_v1_calcular_ordem_servico'),
    path('v1/leitor/requisicao-info/<str:cd_requisicao>/', api_views.api_leitor_requisicao_info, name='api_v1_leitor_requisicao_info'),
    
    path('v1/dashboard/pareto-refugos/', api_views.api_pareto_refugos, name='api_v1_pareto_refugos'),
    path('v1/dashboard/heatmap-produtividade/', api_views.api_heatmap_produtividade, name='api_v1_heatmap_produtividade'),
    
    # ADICIONE ESTA LINHA EM FALTA ABAIXO: 👇
    path('v1/auth/login/', api_views.api_login, name='api_v1_auth_login'),
    
    path('v1/auth/logout/', api_views.api_logout, name='api_v1_auth_logout'),
    path('v1/auth/me/', api_views.api_me, name='api_v1_auth_me'),
    
    path('v1/sync-ordens-servico/', api_views.api_sync_ordens_servico, name='api_v1_sync_ordens_servico'),
    path('v1/sync-selectrequisicao/', api_views.api_sync_selectrequisicao, name='api_v1_sync_selectrequisicao'),
]