from rest_framework import serializers
from .models import Processo, Requisicao, FluxoRequisicao, Pedido
from datetime import datetime

class PedidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pedido
        fields = ['id', 'cliente', 'artigo', 'quantidade']

class ProcessoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Processo
        fields = ['id', 'nome', 'meta_mes']

class FluxoRequisicaoSerializer(serializers.ModelSerializer):
    processo = serializers.PrimaryKeyRelatedField(queryset=Processo.objects.all())  # Espera apenas o ID

    class Meta:
        model = FluxoRequisicao
        fields = ['id', 'processo', 'encerrado', 'dt_processo']

class RequisicaoSerializer(serializers.ModelSerializer):
    fluxos = FluxoRequisicaoSerializer(many=True)

    class Meta:
        model = Requisicao
        fields = ['id', 'data', 'cd_requisicao', 'artigo', 'pedido', 'quantidade', 'lote', 'qt_entregue', 'dt_requisicao', 'modificado', 'encerrado', 'fluxos']

    

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



