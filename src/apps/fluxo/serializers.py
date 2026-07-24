from rest_framework import serializers
from .models import Processo, Requisicao, FluxoRequisicao, Operador, Justificativa, RequisicaoJustificativa
from datetime import datetime
from src.apps.pedido.models import Pedido

# 1º - Definimos o ProcessoSerializer (para que os outros o possam usar)
class ProcessoSerializer(serializers.ModelSerializer):
    meta_diaria_calculada = serializers.SerializerMethodField()

    class Meta:
        model = Processo
        fields = ['id', 'nome', 'meta_diaria_calculada']

    def get_meta_diaria_calculada(self, obj):
        try:
            # Encontra todos os artigos que passam por este processo
            roteiros = obj.roteiroartigo_set.all()
            total_meta_mes = sum(
                (r.artigo.meta_mes or 0) for r in roteiros if r.artigo
            )
            # Assume 22 dias úteis no mês para encontrar a meta diária
            if total_meta_mes > 0:
                return round(total_meta_mes / 22)
            return 0
        except Exception:
            return 0

# 2º - Definimos o PedidoSerializer
class PedidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pedido
        fields = ['id', 'cliente', 'artigo', 'quantidade']

class JustificativaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Justificativa
        fields = ['id', 'nome']

class RequisicaoJustificativaSerializer(serializers.ModelSerializer):
    justificativa_nome = serializers.CharField(source='justificativa.nome', read_only=True)
    
    class Meta:
        model = RequisicaoJustificativa
        fields = ['id', 'justificativa', 'justificativa_nome', 'quantidade', 'm2_proporcional']

# 3º - Agora sim, o OperadorSerializer já pode usar o ProcessoSerializer sem dar erro!
class OperadorSerializer(serializers.ModelSerializer):
    nome_usuario = serializers.CharField(source='usuario.username', read_only=True)
    # Traz a lista completa de processos que o operador tem acesso
    processos = ProcessoSerializer(many=True, read_only=True)

    class Meta:
        model = Operador
        fields = ['id', 'nome_usuario', 'processos']

class FluxoRequisicaoSerializer(serializers.ModelSerializer):
    processo = serializers.PrimaryKeyRelatedField(queryset=Processo.objects.all())  # Espera apenas o ID

    class Meta:
        model = FluxoRequisicao
        fields = ['id', 'processo', 'quantidade', 'encerrado', 'dt_processo', 'dt_saida']

class RequisicaoSerializer(serializers.ModelSerializer):
    fluxos = FluxoRequisicaoSerializer(many=True, read_only=True)
    justificativas_registadas = RequisicaoJustificativaSerializer(many=True, read_only=True)
    risco_atraso = serializers.SerializerMethodField()

    class Meta:
        model = Requisicao
        fields = [
            'id', 'data', 'cd_requisicao', 'artigo', 'nr_pedido', 'quantidade', 'lote', 
            'dt_requisicao', 'modificado', 'encerrado', 'fluxos', 'setor', 'qt_mt', 'm2', 'qt',
            'am', 'exp_qt', 'exp_m2', 'exp_am', 'rend', 'kg_blue', 'seco', 'justificativas_registadas',
            'custo_requisicao', 'risco_atraso'
        ]

    def get_risco_atraso(self, obj):
        from datetime import date, timedelta, datetime
        link = obj.pedido_links.first()
        if link and link.pedido and link.pedido.dt_programada:
            dt_prog = link.pedido.dt_programada
            if isinstance(dt_prog, datetime):
                dt_prog = dt_prog.date()
            if dt_prog <= date.today() + timedelta(days=2):
                return True
        return False

    def update(self, instance, validated_data):
        fluxos_data = validated_data.pop('fluxos', [])
        refilo_kg = validated_data.pop('refilo_kg', None)
        processo_refilo = validated_data.pop('processo_refilo', None)
        
        instance = super().update(instance, validated_data)

        if refilo_kg is not None and refilo_kg > 0:
            Refilo.objects.create(requisicao=instance, processo=processo_refilo, qt_refila=refilo_kg)

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
