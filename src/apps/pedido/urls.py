from django.urls import path
from .views import (
    dashboard_view,
    imprimir_pedido_view,
    imprimir_pedido_data_view,
    simulador_logistica_view,

    api_romaneio_pallets,
    salvar_layout_logistica,
    embarques_list_view,
    embarque_detail_view,
    embarque_print_view,

    converter_previsao_para_embarque_view,
    iniciar_logistica_previsao_view,  # novo
    listar_embarques_previstos_view,
)

urlpatterns = [
    path("dashboard/", dashboard_view, name="dashboard_gerencial"),
    path("imprimir/", imprimir_pedido_view, name="imprimir_pedido"),
    path("imprimir_data/", imprimir_pedido_data_view, name="imprimir_pedido_data"),
    path("simulador/", simulador_logistica_view, name="simulador_logistica"),

    path("api/romaneio/pallets/", api_romaneio_pallets, name="api_romaneio_pallets"),
    path("api/logistica/salvar-layout/", salvar_layout_logistica, name="salvar_layout_logistica"),

    path("api/logistica/previsao/iniciar/", iniciar_logistica_previsao_view, name="iniciar_logistica_previsao",),
    # path("api/logistica/previsao/salvar/", salvar_previsao_logistica_view, name="salvar_previsao_logistica"),
    path("api/logistica/converter-previsao/", converter_previsao_para_embarque_view, name="converter_previsao_para_embarque"),
    path("api/logistica/embarques-previstos/", listar_embarques_previstos_view, name="listar_embarques_previstos"),
    
    path("embarques/", embarques_list_view, name="embarques_list"),
    path("embarques/<int:pk>/", embarque_detail_view, name="embarque_detail"),
    path("embarques/<int:pk>/imprimir/", embarque_print_view, name="embarque_print"),
]