from rest_framework import serializers
from .models import Produto, EnderecoEstoque, InventarioSemanal, ContagemInventario

class ProdutoSerializer(serializers.ModelSerializer):
    # Declaramos os campos calculados (@property) do modelo como leitura
    estoque_total = serializers.ReadOnlyField()
    consumo_diario = serializers.ReadOnlyField()
    previsao_consumo = serializers.ReadOnlyField()
    previsao_estoque = serializers.ReadOnlyField()
    autonomia_dias = serializers.ReadOnlyField()
    risco = serializers.ReadOnlyField()

    class Meta:
        model = Produto
        fields = [
            "cd_produto",
            "produto",
            "estoque_anterior",
            "contagem_fisica",
            "em_transito",
            "percentual",
            "ultimo_valor",
            "dolar",
            "chegada",
            "lancado",
            "obs",
            # Adicionando os campos virtuais
            "estoque_total",
            "consumo_diario",
            "previsao_consumo",
            "previsao_estoque",
            "autonomia_dias",
            "risco"
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