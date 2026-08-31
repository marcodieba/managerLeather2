from rest_framework import serializers
from .models import Processo, Requisicao, FluxoRequisicao, Operador, Justificativa, RequisicaoJustificativa, CustoTintaRegistro, CustoFulaoRegistro, FechamentoDiario, Artigo
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
            # roteiroartigo_set já é prefetched pelo ProcessoViewSet — sem N+1
            total_meta_mes = sum(
                (r.artigo.meta_mes or 0)
                for r in obj.roteiroartigo_set.all()  # usa cache do prefetch
                if r.artigo
            )
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
    processo_nome = serializers.CharField(source='processo.nome', read_only=True)
    operador_nome = serializers.SerializerMethodField()

    def get_operador_nome(self, obj):
        if obj.operador:
            return obj.operador.get_full_name() or obj.operador.username
        return None

    class Meta:
        model = FluxoRequisicao
        fields = ['id', 'processo', 'processo_nome', 'quantidade', 'encerrado', 'dt_processo', 'dt_saida', 'operador_nome']

class ArtigoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artigo
        fields = ['id', 'nome']

class RequisicaoSerializer(serializers.ModelSerializer):
    fluxos = FluxoRequisicaoSerializer(many=True, read_only=True)
    justificativas_registadas = RequisicaoJustificativaSerializer(many=True, read_only=True)
    risco_atraso = serializers.SerializerMethodField()
    artigo_generico = serializers.CharField(source='artigo_padrao.nome', read_only=True)
    fulao = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = Requisicao
        fields = [
            'id', 'data', 'cd_requisicao', 'artigo', 'nr_pedido', 'quantidade', 'lote', 
            'dt_requisicao', 'modificado', 'encerrado', 'fluxos', 'setor', 'qt_mt', 'm2', 'qt',
            'am', 'exp_qt', 'exp_m2', 'exp_am', 'rend', 'kg_blue', 'seco', 'justificativas_registadas',
            'custo_requisicao', 'risco_atraso', 'artigo_generico', 'artigo_padrao',
            'cor', 'espessura', 'classe', 'fulao'
        ]

    def get_risco_atraso(self, obj):
        from datetime import date, timedelta, datetime
        # Usa .all() em vez de .first() para garantir que o cache do
        # prefetch_related (configurado no RequisicaoViewSet) seja usado.
        # .first() pode gerar uma nova query contornando o cache.
        links = obj.pedido_links.all()
        link = links[0] if links else None
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


# ============================================================
# MÓDULO 1: Custo Acabamento Tinta
# ============================================================

class CustoTintaSerializer(serializers.ModelSerializer):
    maquina_display = serializers.CharField(source='get_maquina_display', read_only=True)

    class Meta:
        model  = CustoTintaRegistro
        fields = [
            'id', 'data', 'maquina', 'maquina_display',
            'consumo_kg', 'pecas', 'metros2', 'media_kg_m2', 'criado_em',
        ]
        read_only_fields = ['media_kg_m2', 'criado_em']


# ============================================================
# MÓDULO 2: Custo Fulões Recurtimento
# ============================================================

class CustoFulaoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CustoFulaoRegistro
        fields = [
            'id', 'data', 'artigo',
            'custo_kg_inicial', 'custo_kg_total', 'rendimento',
            'custo_extra_kg', 'custo_m2', 'criado_em',
        ]
        read_only_fields = ['custo_extra_kg', 'custo_m2', 'criado_em']


# ============================================================
# MÓDULO 3: Fechamento Diário
# ============================================================

class FechamentoDiarioSerializer(serializers.ModelSerializer):
    class Meta:
        model  = FechamentoDiario
        fields = ['id', 'data', 'turno_dia', 'turno_noite', 'total', 'obs', 'criado_em']
        read_only_fields = ['total', 'criado_em']


