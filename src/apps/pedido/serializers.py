# apps/pedido/serializers.py
from rest_framework import serializers
from .models import (
    Transportadora, TipoVeiculo, Veiculo, Embarque, 
    ItemEmbarque, Pedido, PrevisaoEmbarque, PrevisaoItemEmbarque
)

class TransportadoraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transportadora
        fields = '__all__'

class TipoVeiculoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoVeiculo
        fields = '__all__'

class VeiculoSerializer(serializers.ModelSerializer):
    tipo = TipoVeiculoSerializer(read_only=True)
    transportadora = TransportadoraSerializer(read_only=True)
    
    class Meta:
        model = Veiculo
        fields = '__all__'

class PedidoSerializer(serializers.ModelSerializer):
    # Incluindo as propriedades (@property) essenciais do modelo
    saldo_a_entregar = serializers.ReadOnlyField()
    status_entrega = serializers.ReadOnlyField()

    class Meta:
        model = Pedido
        fields = '__all__'

class ItemEmbarqueSerializer(serializers.ModelSerializer):
    pedido = PedidoSerializer(read_only=True)

    class Meta:
        model = ItemEmbarque
        fields = '__all__'

class EmbarqueSerializer(serializers.ModelSerializer):
    veiculo = VeiculoSerializer(read_only=True)
    itens_embarcados = ItemEmbarqueSerializer(many=True, read_only=True)
    capacidade_m2 = serializers.ReadOnlyField()
    ocupacao_m2_atual = serializers.ReadOnlyField()
    percentual_ocupacao = serializers.ReadOnlyField()

    class Meta:
        model = Embarque
        fields = '__all__'