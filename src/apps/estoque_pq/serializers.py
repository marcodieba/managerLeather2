# serializers.py
from rest_framework import serializers
from .models import (
    Produto,
    EnderecoEstoque,
    InventarioSemanal,
    ContagemInventario,
)

class ProdutoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produto
        fields = [
            "cd_produto",
            "produto",
            "estoque_anterior",
            "contagem_fisica",
            "em_transito",
        ]


class EnderecoEstoqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnderecoEstoque
        fields = ["codigo", "descricao"]


class InventarioSemanalSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventarioSemanal
        fields = ["id", "referencia", "descricao", "fechado"]


class ContagemInventarioSerializer(serializers.ModelSerializer):
    cd_produto = serializers.IntegerField(source="produto.cd_produto")
    endereco_codigo = serializers.CharField(source="endereco.codigo", allow_null=True)

    class Meta:
        model = ContagemInventario
        fields = [
            "uuid_mobile",
            "cd_produto",
            "endereco_codigo",
            "quantidade",
            "inventario",
            "atualizado_em",
        ]