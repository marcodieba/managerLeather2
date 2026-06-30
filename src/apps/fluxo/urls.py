from django.urls import path, include
# from src.apps.fluxo import views
from rest_framework.routers import DefaultRouter
from .views import busca_requisicao_ajax, ordem_servico_page
from .views import (PedidoViewSet, 
                    ProcessoViewSet, 
                    RequisicaoViewSet, 
                    FluxoRequisicaoViewSet, 
                    imprimir_rendimento_view, 
                    ler_qrcode_movimentacao,
                    OperadorViewSet,
                    resumo_lotes_ativos_view)

router = DefaultRouter()
router.register(r'pedidos', PedidoViewSet)
router.register(r'processos', ProcessoViewSet)
router.register(r'requisicoes', RequisicaoViewSet)
router.register(r'fluxorequisicoes', FluxoRequisicaoViewSet)
router.register(r'operadores', OperadorViewSet)


urlpatterns = [
    path('', include(router.urls)),
    path("imprimir/", imprimir_rendimento_view, name="imprimir_rendimento"),
    # path('ordens/', buscar_ordens_servico, name='buscar_ordens_servico'),
    path('ordem-servico/', ordem_servico_page, name='ordem_servico_page'),
    
    # URL que o JavaScript AJAX vai chamar para o autocomplete
    # Lembre-se que o HTML está chamando /busca/requisicao/
    path('busca/requisicao/', busca_requisicao_ajax, name='busca_requisicao_ajax'),
    path('movimentacao/qrcode/', ler_qrcode_movimentacao, name='ler_qrcode'),
    path('resumo-lotes/', resumo_lotes_ativos_view, name='resumo_lotes'),
    # path('fluxo/', views.RequisicaoViewSet),
    # path('fluxo/<int:pk>/', views.requisicao_detail),
    # path('<pk>/', RequisicaoDetailView.as_view()),
    # path('requisicoes/', include(router.urls)),

    # path(
    #     "swagger-ui/",
    #     RequisicaoViewSet.as_view(
    #         template_name="swagger-ui.html",
    #         extra_context={"schema_url": "openapi-schema"},
    #     ),
    #     name="swagger-ui",
    # ),
]