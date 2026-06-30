from django.urls import path
from .views import painel_estoque, imprimir_etiquetas_qrcode
from .api_views import (
    listar_produtos,
    inventario_aberto,
    listar_enderecos,
    sync_contagens,
)

urlpatterns = [
    path("estoque/", painel_estoque, name="painel_estoque"),
    path(
        "estoque/etiquetas/",
        imprimir_etiquetas_qrcode,
        name="estoque_imprimir_etiquetas",
    ),

    path("api/produtos/", listar_produtos, name="api_listar_produtos"),
    path("api/inventario_aberto/", inventario_aberto, name="api_inventario_aberto"),
    path("api/enderecos/", listar_enderecos, name="api_listar_enderecos"),
    path("api/contagens/sync/", sync_contagens, name="api_sync_contagens"),
]