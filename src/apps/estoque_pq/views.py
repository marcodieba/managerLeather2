import base64
from io import BytesIO
import qrcode
from django.http import Http404

from django.shortcuts import render
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Produto, EnderecoEstoque, InventarioSemanal, ContagemInventario




def painel_estoque(request):
    produtos = Produto.objects.all()

    context = {
        "produtos": produtos,
        "total_estoque": sum(p.estoque_total for p in produtos),
        "total_consumo": sum(p.consumo_diario for p in produtos),
        "total_previsao": sum(p.previsao_consumo for p in produtos),
    }

    return render(request, "estoque/painel.html", context)



@api_view(["POST"])
def sync_contagens(request):
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
        },
        ...
      ]
    }

    Responde:
    { "recebidos": ["uuid1", "uuid2", ...] }
    """
    inventario_id = request.data.get("inventario_id")
    dados = request.data.get("contagens", [])

    inv = InventarioSemanal.objects.filter(id=inventario_id, fechado=False).first()
    if not inv:
        return Response({"detail": "Inventário inválido ou fechado"}, status=status.HTTP_400_BAD_REQUEST)

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
            endereco, _ = EnderecoEstoque.objects.get_or_create(codigo=endereco_codigo)

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


def imprimir_etiquetas_qrcode(request):
    """
    Gera uma página HTML com QRCodes para os produtos informados.

    Espera parâmetro GET: ?cds=123,456,789 (cd_produto)
    """
    cds_param = request.GET.get("cds")
    if not cds_param:
        raise Http404("Nenhum produto selecionado")

    try:
        cds = [int(x) for x in cds_param.split(",") if x.strip()]
    except ValueError:
        raise Http404("Parâmetro inválido")

    produtos = Produto.objects.filter(cd_produto__in=cds).order_by("produto")

    etiquetas = []
    for p in produtos:
        # Conteúdo do QR = cd_produto (pode mudar para outro formato se quiser)
        qr_data = str(p.cd_produto)

        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=2,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

        etiquetas.append(
            {
                "produto": p,
                "qr_b64": img_b64,
            }
        )

    context = {
        "etiquetas": etiquetas,
    }
    return render(request, "estoque/etiquetas_qrcode.html", context)