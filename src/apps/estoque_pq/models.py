from django.db import models


from django.db import models
from django.utils import timezone


class Produto(models.Model):
    data = models.DateTimeField(auto_now_add=True)
    cd_produto = models.BigIntegerField(primary_key=True, unique=True)
    produto = models.CharField(('Produto'), max_length=100, default=None, null=True, blank=True)
    quantidade = models.BigIntegerField(('Quantidade'), null=True, blank=True)

    # =========================
    # CAMPOS DA PLANILHA
    # =========================
    estoque_anterior = models.FloatField(default=0)
    contagem_fisica = models.FloatField(default=0)
    em_transito = models.FloatField(default=0)

    percentual = models.FloatField(default=0)

    ultimo_valor = models.FloatField(default=0)
    dolar = models.FloatField(null=True, blank=True)

    chegada = models.DateField(null=True, blank=True)
    lancado = models.BooleanField(default=False)

    obs = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.produto}"

    # =========================
    # CÁLCULOS BASEADOS NO CONSUMO REAL
    # =========================

    @property
    def estoque_total(self):
        return (self.contagem_fisica or 0) + (self.em_transito or 0)

    @property
    def consumo_diario(self):
        from django.db.models import Sum
        from datetime import timedelta

        data_limite = timezone.now() - timedelta(days=7)

        total = (
            self.consumos
            .filter(data__gte=data_limite)
            .aggregate(total=Sum('quantidade_consumida'))['total'] or 0
        )

        return total / 7 if total else 0

    @property
    def previsao_consumo(self):
        dias = 6
        return self.consumo_diario * dias

    @property
    def previsao_estoque(self):
        return self.estoque_total - self.previsao_consumo

    @property
    def autonomia_dias(self):
        if self.consumo_diario > 0:
            return self.estoque_total / self.consumo_diario
        return 0

    @property
    def risco(self):
        if self.autonomia_dias <= 5:
            return "CRÍTICO"
        elif self.autonomia_dias <= 10:
            return "PERIGOSO"
        return ""


class ConsumoProduto(models.Model):
    produto = models.ForeignKey(
        Produto,
        on_delete=models.CASCADE,
        related_name="consumos"
    )

    cd_requisicao = models.BigIntegerField()

    peso = models.FloatField()
    percentual = models.FloatField()
    acrescimo = models.FloatField()

    quantidade_consumida = models.FloatField()
    custo_unitario = models.FloatField()
    custo_total = models.FloatField()

    data = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.produto} - {self.quantidade_consumida}"


class Couro(models.Model):
    # hj = date.today()
    data = models.DateTimeField(auto_now_add=True)
    cd_pallet = models.CharField(primary_key=True, unique=True, max_length=100, null=False, blank=False)
    artigo = models.CharField(('Artigo'), max_length=100,  default=None, null=True, blank=True)
    quantidade = models.BigIntegerField(('Quantidade'), null=False, blank=False)
    m2 = models.DecimalField(('M²'), default=0.0, max_digits=10, decimal_places=2, null=False, blank=False)
    

    def __str__(self):
        return f"{self.cd_pallet}"



class EnderecoEstoque(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    descricao = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return self.codigo

class InventarioSemanal(models.Model):
    referencia = models.DateField()  # ex: segunda da semana
    descricao = models.CharField(max_length=200, blank=True, null=True)
    fechado = models.BooleanField(default=False)

    def __str__(self):
        return f"Inventário {self.referencia}"

class ContagemInventario(models.Model):
    inventario = models.ForeignKey(
        InventarioSemanal,
        on_delete=models.CASCADE,
        related_name="contagens",
    )
    produto = models.ForeignKey("Produto", on_delete=models.CASCADE)
    endereco = models.ForeignKey(
        EnderecoEstoque,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    quantidade = models.FloatField(default=0)

    uuid_mobile = models.CharField(max_length=100, unique=True)
    atualizado_em = models.DateTimeField(default=timezone.now)
    origem = models.CharField(max_length=50, default="mobile")

    class Meta:
        unique_together = ("inventario", "produto", "endereco")

    def __str__(self):
        return f"{self.inventario} - {self.produto} - {self.endereco}"