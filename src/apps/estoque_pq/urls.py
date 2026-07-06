from django.urls import path
from . import views  # Mantido temporariamente caso alguma rota legada precise
from . import api_views

urlpatterns = [
    # ---------------------------------------------------------
    # ROTAS LEGADAS (A renderizar HTML)
    # ---------------------------------------------------------
    path("estoque/", views.painel_estoque, name="painel_estoque"),
    path("estoque/etiquetas/", views.imprimir_etiquetas_qrcode, name="estoque_imprimir_etiquetas"),

    # ---------------------------------------------------------
    # ROTAS DA API PARA MOBILE/REACT
    # ---------------------------------------------------------
    path("api/v1/estoque/painel/", api_views.api_painel_estoque, name="api_v1_painel_estoque"),
    path("api/v1/estoque/etiquetas/", api_views.api_imprimir_etiquetas, name="api_v1_etiquetas"),
    
    path("api/v1/estoque/produtos/", api_views.listar_produtos, name="api_v1_listar_produtos"),
    path("api/v1/estoque/inventario-aberto/", api_views.inventario_aberto, name="api_v1_inventario_aberto"),
    path("api/v1/estoque/enderecos/", api_views.listar_enderecos, name="api_v1_listar_enderecos"),
    path("api/v1/estoque/contagens/sync/", api_views.sync_contagens, name="api_v1_sync_contagens"),
]