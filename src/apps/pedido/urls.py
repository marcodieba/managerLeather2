# apps/pedido/urls.py
from django.urls import path
from . import views
from . import api_views # O arquivo que acabamos de criar

urlpatterns = [
    # ---------------------------------------------------------
    # ROTAS LEGADAS (Manter ativas até o React estar 100%)
    # ---------------------------------------------------------
    path("dashboard/", views.dashboard_view, name="dashboard_gerencial"),
    path("imprimir/", views.imprimir_pedido_view, name="imprimir_pedido"),
    path("imprimir_data/", views.imprimir_pedido_data_view, name="imprimir_pedido_data"),
    path("simulador/", views.simulador_logistica_view, name="simulador_logistica"),
    path("embarques/", views.embarques_list_view, name="embarques_list"),
    path("embarques/<int:pk>/", views.embarque_detail_view, name="embarque_detail"),
    path("embarques/<int:pk>/imprimir/", views.embarque_print_view, name="embarque_print"),

    # ---------------------------------------------------------
    # SUAS APIS JSON EXISTENTES (AJAX do template atual)
    # ---------------------------------------------------------
    path("api/romaneio/pallets/", views.api_romaneio_pallets, name="api_romaneio_pallets"),
    path("api/logistica/salvar-layout/", views.salvar_layout_logistica, name="salvar_layout_logistica"),
    path("api/logistica/previsao/iniciar/", views.iniciar_logistica_previsao_view, name="iniciar_logistica_previsao"),
    path("api/logistica/converter-previsao/", views.converter_previsao_para_embarque_view, name="converter_previsao_para_embarque"),
    path("api/logistica/embarques-previstos/", views.listar_embarques_previstos_view, name="listar_embarques_previstos"),

    # ---------------------------------------------------------
    # NOVAS APIS PARA O REACT
    # ---------------------------------------------------------
    path("api/v1/dashboard/", api_views.api_dashboard, name="api_v1_dashboard"),
    path("api/v1/embarques/", api_views.api_embarques_list, name="api_v1_embarques"),
    path("api/v1/simulador-dados/", api_views.api_dados_simulador, name="api_v1_simulador_dados"),

    # NOVAS APIS DE RELATÓRIOS COMPLEXOS PARA O REACT
    path("api/v1/relatorios/por-artigo/", api_views.api_relatorio_por_artigo, name="api_v1_relatorio_por_artigo"),
    path("api/v1/relatorios/por-data/", api_views.api_relatorio_por_data, name="api_v1_relatorio_por_data"),

    # NOVAS APIS DE LOGÍSTICA PARA O REACT (DRF Padrão)
    path("api/v1/logistica/romaneio-pallets/", api_views.api_romaneio_pallets, name="api_v1_romaneio_pallets"),
    path("api/v1/logistica/salvar-layout/", api_views.api_salvar_layout_logistica, name="api_v1_salvar_layout_logistica"),
    path("api/v1/logistica/previsao/iniciar/", api_views.api_iniciar_logistica_previsao, name="api_v1_iniciar_logistica_previsao"),
    path("api/v1/logistica/embarques-previstos/", api_views.api_listar_embarques_previstos, name="api_v1_listar_embarques_previstos"),
    path("api/v1/logistica/previsao/salvar/", api_views.api_salvar_previsao_logistica, name="api_v1_salvar_previsao_logistica"),
    path("api/v1/logistica/converter-previsao/", api_views.api_converter_previsao_para_embarque, name="api_v1_converter_previsao"),
]