from rest_framework import serializers
from .models import Processo, Requisicao, FluxoRequisicao, Operador
from datetime import datetime
from src.apps.pedido.models import Pedido


class OperadorSerializer(serializers.ModelSerializer):
    # Puxa os nomes reais em vez de apenas os IDs
    nome_processo = serializers.CharField(source='processo.nome', read_only=True)
    nome_usuario = serializers.CharField(source='usuario.username', read_only=True) # Pode trocar por 'usuario.first_name' se preferir

    class Meta:
        model = Operador
        fields = ['id', 'nome_usuario', 'nome_processo']

class PedidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pedido
        fields = ['id', 'cliente', 'artigo', 'quantidade']

class ProcessoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Processo
        fields = ['id', 'nome']

class FluxoRequisicaoSerializer(serializers.ModelSerializer):
    processo = serializers.PrimaryKeyRelatedField(queryset=Processo.objects.all())  # Espera apenas o ID

    class Meta:
        model = FluxoRequisicao
        # Adicionei a "quantidade" aqui também para garantir que a API possa ler e gravar esse campo!
        fields = ['id', 'processo', 'quantidade', 'encerrado', 'dt_processo']

class RequisicaoSerializer(serializers.ModelSerializer):
    # Adicionamos read_only=True ou required=False para evitar problemas no POST
    fluxos = FluxoRequisicaoSerializer(many=True, required=False)

    class Meta:
        model = Requisicao
        # 🌟 CORRIGIDO: Trocamos 'pedido' por 'nr_pedido' e 'qt_entregue' por 'exp_qt'
        fields = ['id', 'data', 'cd_requisicao', 'artigo', 'nr_pedido', 'quantidade', 'lote', 'exp_qt', 'dt_requisicao', 'modificado', 'encerrado', 'fluxos']

    def update(self, instance, validated_data):
        fluxos_data = validated_data.pop('fluxos', [])
        instance = super().update(instance, validated_data)

        instance.fluxos.all().delete()

        for fluxo_data in fluxos_data:
            processo = fluxo_data.pop('processo')

            # Converte datetime para date, se necessário
            dt_processo = fluxo_data.get('dt_processo')
            if isinstance(dt_processo, datetime):
                fluxo_data['dt_processo'] = dt_processo.date()

            FluxoRequisicao.objects.create(
                requisicao=instance,
                processo=processo,
                **fluxo_data
            )

        return instance