# api_views.py
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import (
    Produto,
    EnderecoEstoque,
    InventarioSemanal,
    ContagemInventario,
)
from .serializers import (
    ProdutoSerializer,
    EnderecoEstoqueSerializer,
    InventarioSemanalSerializer,
)

@api_view(["GET"])
def listar_produtos(request):
    qs = Produto.objects.all()
    return Response(ProdutoSerializer(qs, many=True).data)


@api_view(["GET"])
def inventario_aberto(request):
    inv = (
        InventarioSemanal.objects
        .filter(fechado=False)
        .order_by("-referencia")
        .first()
    )
    if not inv:
        return Response(
            {"detail": "Nenhum inventário aberto"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(InventarioSemanalSerializer(inv).data)


@api_view(["GET"])
def listar_enderecos(request):
    qs = EnderecoEstoque.objects.all()
    return Response(EnderecoEstoqueSerializer(qs, many=True).data)


@api_view(["POST"])
def sync_contagens(request):
    print(">>> SYNC_CONTAGENS payload:", request.data)  # LOG SIMPLES
    """
    Espera:
    {
      "inventario_id": 1,
      "contagens": [
        {
          "uuid_mobile": "550e8400-e29b-41d4-a716-446655440000",
          "cd_produto": 123,
          "endereco_codigo": "A01-01",
          "quantidade": 10.5,
          "atualizado_em": "2026-04-13T14:00:00Z"
        }
      ]
    }
    Responde:
    { "recebidos": ["uuid1", "uuid2", ...] }
    """
    inventario_id = request.data.get("inventario_id")
    dados = request.data.get("contagens", [])

    inv = InventarioSemanal.objects.filter(id=inventario_id, fechado=False).first()
    if not inv:
        return Response(
            {"detail": "Inventário inválido ou fechado"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    recebidos = []

    for item in dados:
        uuid_mobile = item.get("uuid_mobile")
        cd_produto = item.get("cd_produto")
        endereco_codigo = item.get("endereco_codigo")
        quantidade = float(item.get("quantidade", 0))
        atualizado_em = item.get("atualizado_em")

        if not (uuid_mobile and cd_produto):
            continue

        produto = Produto.objects.filter(cd_produto=cd_produto).first()
        if not produto:
            continue

        endereco = None
        if endereco_codigo:
            endereco, _ = EnderecoEstoque.objects.get_or_create(
                codigo=endereco_codigo
            )

        obj, created = ContagemInventario.objects.get_or_create(
            uuid_mobile=uuid_mobile,
            defaults={
                "inventario": inv,
                "produto": produto,
                "endereco": endereco,
                "quantidade": quantidade,
                "atualizado_em": atualizado_em or timezone.now(),
            },
        )

        if not created:
            obj.quantidade = quantidade
            obj.endereco = endereco
            obj.atualizado_em = atualizado_em or timezone.now()
            obj.save()

        recebidos.append(uuid_mobile)

    return Response({"recebidos": recebidos})