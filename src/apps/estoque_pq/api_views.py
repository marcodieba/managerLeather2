import base64
import qrcode
from io import BytesIO
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Produto, EnderecoEstoque, InventarioSemanal, ContagemInventario
from .serializers import ProdutoSerializer, EnderecoEstoqueSerializer, InventarioSemanalSerializer

# --- APIS DO APP MÓVEL / LISTAGENS BÁSICAS ---

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def listar_produtos(request):
    qs = Produto.objects.all()
    return Response(ProdutoSerializer(qs, many=True).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def inventario_aberto(request):
    inv = InventarioSemanal.objects.filter(fechado=False).order_by("-referencia").first()
    if not inv:
        return Response({"detail": "Nenhum inventário aberto"}, status=status.HTTP_404_NOT_FOUND)
    return Response(InventarioSemanalSerializer(inv).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def listar_enderecos(request):
    qs = EnderecoEstoque.objects.all()
    return Response(EnderecoEstoqueSerializer(qs, many=True).data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_contagens(request):
    # O seu código do sync_contagens continua intocável aqui
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

        if not (uuid_mobile and cd_produto): continue

        produto = Produto.objects.filter(cd_produto=cd_produto).first()
        if not produto: continue

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


# --- NOVAS APIS PARA O REACT (DASHBOARD E ETIQUETAS) ---

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_painel_estoque(request):
    """Substitui o painel_estoque, enviando os produtos e os cabeçalhos resumidos"""
    produtos = Produto.objects.all()
    
    total_estoque = sum(p.estoque_total for p in produtos)
    total_consumo = sum(p.consumo_diario for p in produtos)
    total_previsao = sum(p.previsao_consumo for p in produtos)

    return Response({
        "resumo": {
            "total_estoque": total_estoque,
            "total_consumo": total_consumo,
            "total_previsao": total_previsao,
        },
        "produtos": ProdutoSerializer(produtos, many=True).data
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_imprimir_etiquetas(request):
    """Gera os QR Codes e envia a String Base64 direto no JSON"""
    cds_param = request.query_params.get("cds")
    
    if not cds_param:
        return Response({"erro": "Nenhum produto selecionado. Envie os 'cds' via parâmetro GET."}, status=400)

    try:
        cds = [int(x) for x in cds_param.split(",") if x.strip()]
    except ValueError:
        return Response({"erro": "Parâmetro 'cds' inválido."}, status=400)

    produtos = Produto.objects.filter(cd_produto__in=cds).order_by("produto")
    etiquetas = []
    
    for p in produtos:
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(str(p.cd_produto))
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

        etiquetas.append({
            "cd_produto": p.cd_produto,
            "nome_produto": p.produto,
            # Já formata para o formato correto de imagem Web
            "qr_image": f"data:image/png;base64,{img_b64}" 
        })

    return Response({"etiquetas": etiquetas})