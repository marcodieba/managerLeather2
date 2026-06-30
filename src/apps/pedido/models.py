from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date


PES2_TO_M2_DIVISOR = 10.764


# ==========================================================
# NOVOS MODELOS DE APOIO À LOGÍSTICA
# ==========================================================

class Transportadora(models.Model):
    nome = models.CharField('Nome/Razão Social', max_length=255)
    cnpj = models.CharField('CNPJ', max_length=18, blank=True, null=True)
    contato = models.CharField('Contato', max_length=100, blank=True, null=True)

    def __str__(self):
        return self.nome


class TipoVeiculo(models.Model):
    """
    Ex: Carreta, Sider, Bitruck, etc.
    Define as dimensões para cálculo de ocupação.
    """
    nome = models.CharField('Tipo de Veículo', max_length=50)
    capacidade_m2 = models.FloatField('Capacidade Máxima (m²)')
    profundidade_util = models.FloatField('Profundidade Útil (m)', help_text="Para cálculo de acomodação")
    largura_util = models.FloatField('Largura Útil (m)', default=2.40)

    def __str__(self):
        return f"{self.nome} (Cap: {self.capacidade_m2}m²)"


class Veiculo(models.Model):
    placa = models.CharField('Placa', max_length=10)
    transportadora = models.ForeignKey(Transportadora, on_delete=models.CASCADE, related_name='veiculos')
    tipo = models.ForeignKey(TipoVeiculo, on_delete=models.PROTECT)
    motorista = models.CharField('Motorista', max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.placa} - {self.tipo.nome} ({self.transportadora.nome})"


class Embarque(models.Model):
    veiculo = models.ForeignKey('Veiculo', on_delete=models.CASCADE, related_name='embarques')
    data_embarque = models.DateField('Data de Embarque', default=date.today)
    finalizado = models.BooleanField('Embarque Finalizado?', default=False)

    # Armazena o layout completo do caminhão em JSON (opcional)
    mapa_carga_json = models.JSONField('Mapa de Carga (Layout)', null=True, blank=True)

    def __str__(self):
        return f"Carga {self.id} - {self.veiculo.placa} ({self.data_embarque})"

    @property
    def capacidade_m2(self) -> float:
        try:
            return float(self.veiculo.tipo.capacidade_m2 or 0)
        except Exception:
            return 0.0

    @property
    def ocupacao_m2_atual(self) -> float:
        """
        Ocupação logística sempre em m² pelo layout.
        Conta apenas itens no piso (pos_z == 0).
        """
        total = 0.0
        for it in self.itens_embarcados.all():
            if (it.pos_z or 0) == 0:
                total += float((it.largura or 0) * (it.comprimento or 0))
        return total

    @property
    def percentual_ocupacao(self) -> float:
        cap = self.capacidade_m2
        if cap <= 0:
            return 0.0
        return (self.ocupacao_m2_atual / cap) * 100.0


# ==========================================================
# MODELO PEDIDO (ORIGINAL + ATUALIZAÇÕES)
# ==========================================================

class Pedido(models.Model):
    hj = date.today()

    cd_pedido = models.IntegerField()
    cliente = models.CharField(('Cliente'), max_length=255, blank=True, null=False)
    cidade = models.CharField(('Cidade'), max_length=100, default=None, null=True, blank=True)
    uf = models.CharField(('UF'), max_length=2, default=None, null=True, blank=True)
    nr_pedido_interno = models.CharField(('Cod.Contr'), max_length=20, default=None, null=True, blank=True)
    nr_pedido_cliente = models.CharField(('Cod. Pedido Cliente'), max_length=30, default=None, null=True, blank=True)
    nr_contract = models.CharField(('Ped.Contract'), max_length=20, default=None, null=True, blank=True)
    selecao = models.CharField(('Classe'), blank=True, max_length=100, null=True)
    artigo = models.CharField(('Artigo'), max_length=100, default=None, null=True, blank=True)
    produto = models.CharField(('Produto'), blank=True, max_length=100, null=True)
    unidade_medida = models.CharField(('Unidade de Medida'), blank=True, max_length=100, null=True)  # SEM default
    quantidade = models.FloatField(('Qt. Pedido'), null=False, blank=True)  # verbose_name original
    quantidade_entregue = models.FloatField(('Qt. Entregue'), default=0.0, null=True, blank=True)
    classificando = models.BooleanField(('CLASSIFICANDO?'), default=False, null=True)
    obs = models.CharField(('Observação'), max_length=100, default=None, null=True, blank=True)
    fechado = models.BooleanField(('Fechado?'), default=False, null=False)
    dt_pedido = models.DateTimeField(('Data do Pedido'), null=False)
    dt_programada = models.DateTimeField(('Data do Programada'), null=True, blank=True)
    dt_embarque = models.DateTimeField(('Data do Embarque'), null=True, blank=True)
    espessura = models.CharField(('espessura'), blank=True, max_length=100, null=True)

    @property
    def saldo_a_entregar(self):
        embarcado = self.historico_embarques.aggregate(
            total=models.Sum('metragem_embarcada')
        )['total'] or 0
        return max(0, float(self.quantidade or 0) - float(embarcado or 0))

    @property
    def status_entrega(self):
        saldo = self.saldo_a_entregar
        if saldo <= 0:
            return "Totalmente Entregue"
        elif saldo < float(self.quantidade or 0):
            return f"Entrega Parcial (Faltam {saldo:.3f}m²)"
        return "Aguardando Embarque"

    def __str__(self):
        cliente = self.cliente or ""
        return u"%s - %s - %s - Saldo: %s" % (
            self.nr_contract,
            cliente[:10],
            self.artigo,
            self.saldo_a_entregar
        )

    def to_dict(self):
        return {
            'value': self.pk,
            'cd_pedido': self.cd_pedido,
            'cliente': self.cliente,
            'nr_pedido_interno': self.nr_pedido_interno,
            'nr_contract': self.nr_contract,
            'selecao': self.selecao,
            'artigo': self.artigo,
            'produto': self.produto,
            'quantidade': self.quantidade,
            'quantidade_entregue': self.quantidade_entregue,
            'fechado': self.fechado,
            'dt_pedido': self.dt_pedido,
            'dt_programada': self.dt_programada,
            'saldo_a_entregar': self.saldo_a_entregar,
            'status_entrega': self.status_entrega,
        }



# ==========================================================
# ITEM EMBARQUE (ÚNICO) + RASTREIO ROMANEIO/PALLET
# ==========================================================

class ItemEmbarque(models.Model):
    """
    Item embarcado (baixa do pedido sempre em m²) + layout + rastreio do romaneio/pallet.
    """
    embarque = models.ForeignKey(Embarque, on_delete=models.CASCADE, related_name='itens_embarcados')
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='historico_embarques')

    # Baixa do pedido (sempre m²)
    metragem_embarcada = models.FloatField('Metragem Embarcada (m²) nesta Viagem')

    # Rastreio do romaneio/pallet (bloqueio de duplicidade)
    cd_romaneio_faturamento = models.CharField('Cd. Romaneio Faturamento', max_length=30, db_index=True)
    nr_pallet = models.CharField('Nr. Pallet', max_length=30)
    pallet = models.CharField('Pallet (Nr_Pallet_Nr_Embalagem)', max_length=60)

    # Auditoria opcional (dados originais do SELECT)
    pes2_original = models.FloatField('Pes² (original)', null=True, blank=True)
    peso_liquido = models.FloatField('Peso Líquido', null=True, blank=True)
    pecas = models.IntegerField('Peças', null=True, blank=True)

    # Layout (Lego logístico)
    pos_x = models.FloatField('Posição X (m)', default=0)
    pos_y = models.FloatField('Posição Y (m)', default=0)
    pos_z = models.IntegerField('Nível de Remonte (Z)', default=0)  # 0 chão

    largura = models.FloatField('Largura (m)', default=1.2)
    comprimento = models.FloatField('Comprimento (m)', default=1.0)
    altura = models.FloatField('Altura (m)', default=1.0)
    rotacionado = models.BooleanField('Está Rotacionado?', default=False)

    data_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cd_romaneio_faturamento', 'nr_pallet', 'pallet'],
                name='uniq_romaneio_nr_pallet_pallet'
            )
        ]
        indexes = [
            models.Index(fields=['cd_romaneio_faturamento']),
            models.Index(fields=['nr_pallet']),
        ]

    def __str__(self):
        return f"{self.metragem_embarcada}m² do Pedido {self.pedido.nr_contract} ({self.nr_pallet}/{self.pallet})"

    def clean(self):
        # bloqueia alteração em embarque finalizado
        if self.embarque_id and hasattr(self, 'embarque') and self.embarque.finalizado:
            raise ValidationError("Este embarque está finalizado; não é permitido alterar/incluir itens.")

        if self.metragem_embarcada is None or float(self.metragem_embarcada) <= 0:
            raise ValidationError("A metragem embarcada deve ser maior que zero.")

        # valida saldo (considerando edição) + TOLERÂNCIA 50%
        if self.pedido_id:
            qs = ItemEmbarque.objects.filter(pedido_id=self.pedido_id)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            total_outros = qs.aggregate(total=models.Sum('metragem_embarcada'))['total'] or 0
            
            # Saldo "real" antes deste item
            saldo_real = max(0.0, float(self.pedido.quantidade or 0) - float(total_outros or 0))

            # Tolerância de 50% sobre o saldo restante (para cobrir variações de romaneio)
            tolerancia = 0.50
            saldo_permitido = saldo_real * (1 + tolerancia)

            if float(self.metragem_embarcada) > saldo_permitido + 1e-9:
                raise ValidationError(
                    f"Metragem embarcada ({self.metragem_embarcada}m²) excede "
                    f"saldo ({saldo_real:.2f}m²) +50% tolerância ({saldo_permitido:.2f}m²)."
                )


    @property
    def area_ocupada_m2(self) -> float:
        return float((self.largura or 0) * (self.comprimento or 0))


class PedidoRequisicao(models.Model):
    requisicao = models.ForeignKey('fluxo.Requisicao', on_delete=models.CASCADE, related_name='pedido_links')
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='requisicao_links')

    class Meta:
        unique_together = ('requisicao', 'pedido')

    def __str__(self):
        return f"Pedido {self.pedido.cd_pedido} vinculado à Requisição {self.requisicao.cd_requisicao}"


class ReservaEmbarque(models.Model):
    """
    Reserva de metragem por Pedido dentro de um Embarque (previsão).
    NÃO baixa saldo do pedido; serve apenas para planejar.
    """
    embarque = models.ForeignKey(
        Embarque,
        on_delete=models.CASCADE,
        related_name="reservas"
    )
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="reservas_embarque"
    )
    metragem_prevista_m2 = models.FloatField("Metragem Prevista (m²)")

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("embarque", "pedido")

    def clean(self):
        if self.metragem_prevista_m2 is None or self.metragem_prevista_m2 <= 0:
            raise ValidationError("A metragem prevista deve ser maior que zero.")

    def __str__(self):
        return f"{self.metragem_prevista_m2}m² reservados do Pedido {self.pedido.nr_contract} no Embarque {self.embarque_id}"


class PrevisaoEmbarque(models.Model):
    data_prevista = models.DateField('Data Prevista', default=date.today)
    cliente = models.CharField('Cliente (livre)', max_length=255, blank=True, null=True)
    observacao = models.CharField('Observação', max_length=255, blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    convertido = models.BooleanField('Convertido em Embarque?', default=False)

    def __str__(self):
        return f"Prev #{self.id} - {self.data_prevista} - {self.cliente or 'Vários clientes'}"


class PrevisaoItemEmbarque(models.Model):
    previsao = models.ForeignKey(
        PrevisaoEmbarque,
        on_delete=models.CASCADE,
        related_name='itens'
    )
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='previsoes_embarque'
    )

    # aqui é apenas intenção, não baixa saldo de fato
    metragem_prevista_m2 = models.FloatField('Metragem Prevista (m²)')

    # opcional: para quando já souber de qual romaneio virá
    cd_romaneio_faturamento = models.CharField(
        'Romaneio Previsto', max_length=30, blank=True, null=True
    )

    criado_em = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.metragem_prevista_m2 is None or self.metragem_prevista_m2 <= 0:
            raise ValidationError("A metragem prevista deve ser maior que zero.")

        # se quiser, pode limitar à quantidade do pedido (ou +tolerância)
        saldo = float(self.pedido.saldo_a_entregar or 0)
        if self.metragem_prevista_m2 > saldo * 1.5:  # mesma regra de tolerância
            raise ValidationError(
                f"Metragem prevista ({self.metragem_prevista_m2}m²) excede "
                f"saldo ({saldo:.2f}m²) +50%."
            )

    def __str__(self):
        return f"Prev {self.metragem_prevista_m2}m² do Pedido {self.pedido.nr_contract}"