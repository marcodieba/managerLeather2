# apps/pedido/admin.py
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.contrib.humanize.templatetags.humanize import intcomma

from .models import (
    Pedido,
    Transportadora,
    TipoVeiculo,
    Veiculo,
    Embarque,
    ItemEmbarque,
)


# ==============================================================================
# INLINES
# ==============================================================================

class ItemEmbarqueInline(admin.TabularInline):
    """
    Permite ver/adicionar embarques parciais diretamente no Pedido.
    """
    model = ItemEmbarque
    extra = 0
    autocomplete_fields = ("embarque",)
    verbose_name = "Embarque Parcial"
    verbose_name_plural = "Histórico de Embarques Parciais"

    fields = (
        "embarque",
        "metragem_embarcada",
        "cd_romaneio_faturamento",
        "nr_pallet",
        "pallet",
        "data_registro",
    )
    readonly_fields = ("data_registro",)


class ItemCargaInline(admin.TabularInline):
    """
    Permite adicionar vários itens/pallets a um Embarque.
    """
    model = ItemEmbarque
    extra = 0
    autocomplete_fields = ("pedido",)

    fields = (
        "pedido",
        "metragem_embarcada",
        "cd_romaneio_faturamento",
        "nr_pallet",
        "pallet",
        "pos_x",
        "pos_y",
        "pos_z",
        "largura",
        "comprimento",
        "altura",
        "rotacionado",
    )


# ==============================================================================
# FILTROS
# ==============================================================================

class TemRequisicaoFilter(SimpleListFilter):
    title = "Possui requisições"
    parameter_name = "tem_requisicao"

    def lookups(self, request, model_admin):
        return (("sim", "Sim"), ("nao", "Não"))

    def queryset(self, request, queryset):
        if self.value() == "sim":
            return queryset.filter(requisicao_links__isnull=False).distinct()
        if self.value() == "nao":
            return queryset.filter(requisicao_links__isnull=True)
        return queryset


class FiltroMesAnoProgramado(SimpleListFilter):
    title = "Mês Programado"
    parameter_name = "mes_programado"

    def lookups(self, request, model_admin):
        datas = (
            model_admin.get_queryset(request)
            .filter(dt_programada__isnull=False)
            .dates("dt_programada", "month", order="DESC")
        )
        out = []
        for d in datas:
            if not d:
                continue
            out.append((d.strftime("%Y-%m"), d.strftime("%B de %Y").capitalize()))
        return out

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        try:
            ano, mes = map(int, self.value().split("-"))
            return queryset.filter(dt_programada__year=ano, dt_programada__month=mes)
        except (ValueError, TypeError):
            return queryset



# ==============================================================================
# AÇÕES
# ==============================================================================

def gerar_relatorio_detalhado(modeladmin, request, queryset):
    if not queryset.exists():
        modeladmin.message_user(request, "Nenhum pedido selecionado.", messages.WARNING)
        return
    ids = ",".join(str(obj.pk) for obj in queryset)

    # NAMES reais do seu apps/pedido/urls.py
    return HttpResponseRedirect(f"{reverse('imprimir_pedido')}?ids={ids}")

gerar_relatorio_detalhado.short_description = "📄 Gerar Relatório Detalhado (por Artigo)"


def gerar_relatorio_por_data(modeladmin, request, queryset):
    if not queryset.exists():
        modeladmin.message_user(request, "Nenhum pedido selecionado.", messages.WARNING)
        return
    ids = ",".join(str(obj.pk) for obj in queryset)

    # NAMES reais do seu apps/pedido/urls.py
    return HttpResponseRedirect(f"{reverse('imprimir_pedido_data')}?ids={ids}")

gerar_relatorio_por_data.short_description = "🗓️ Gerar Relatório por Data"


# ==============================================================================
# ADMINS
# ==============================================================================

@admin.register(Transportadora)
class TransportadoraAdmin(admin.ModelAdmin):
    list_display = ("nome", "cnpj", "contato")
    search_fields = ("nome", "cnpj")


@admin.register(TipoVeiculo)
class TipoVeiculoAdmin(admin.ModelAdmin):
    list_display = ("nome", "capacidade_m2", "profundidade_util", "largura_util")


@admin.register(Veiculo)
class VeiculoAdmin(admin.ModelAdmin):
    list_display = ("placa", "tipo", "transportadora", "motorista")
    list_filter = ("tipo", "transportadora")
    search_fields = ("placa", "motorista")


@admin.register(Embarque)
class EmbarqueAdmin(admin.ModelAdmin):
    list_display = ("id", "veiculo", "data_embarque", "exibir_ocupacao", "finalizado")
    list_filter = ("finalizado", "data_embarque", "veiculo__transportadora")
    search_fields = ("veiculo__placa",)  # sem 'obs'
    date_hierarchy = "data_embarque"
    autocomplete_fields = ("veiculo",)
    inlines = (ItemCargaInline,)

    @admin.display(description="% Ocupação")
    def exibir_ocupacao(self, obj):
        raw = getattr(obj, "percentual_ocupacao", 0)
        try:
            percent_num = float(raw or 0)
        except (TypeError, ValueError):
            percent_num = 0.0

        cor = "green" if percent_num < 90 else "orange" if percent_num <= 100 else "red"
        percent_txt = f"{percent_num:.1f}"
        return format_html("<b style='color:{}'>{}%</b>", cor, percent_txt)



@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = (
        "nr_contract",
        "nr_pedido_interno",
        # "listar_requisicoes",
        "cidade",
        "artigo",
        "cliente",
        "quantidade",
        "quantidade_entregue",
        "exibir_saldo",
        "fechado",
        "dt_programada_formatada",
        "dt_pedido",
    )
    list_filter = ("fechado", "dt_pedido", TemRequisicaoFilter, FiltroMesAnoProgramado)
    search_fields = ("cd_pedido", "cliente", "nr_contract", "nr_pedido_interno", "artigo")
    inlines = (ItemEmbarqueInline,)
    actions = (gerar_relatorio_detalhado, gerar_relatorio_por_data)

    @admin.display(description="Saldo a Entregar")
    def exibir_saldo(self, obj):
        # CORREÇÃO: Subtrai a quantidade_entregue da quantidade total
        qtd_total = float(obj.quantidade or 0)
        qtd_entregue = float(obj.quantidade_entregue or 0)
        saldo_num = qtd_total - qtd_entregue

        if saldo_num <= 0:
            return format_html("<span style='color:green;font-weight:bold'>Entregue</span>")

        # Formata com 3 casas decimais e exibe a unidade
        saldo_txt = f"{saldo_num:.3f}"
        return format_html("<span style='color:#c0392b;font-weight:bold'>{} m²</span>", saldo_txt)




    @admin.display(description="Dt. Programada", ordering="dt_programada")
    def dt_programada_formatada(self, obj: Pedido):
        if obj.dt_programada:
            return obj.dt_programada.strftime("%d/%m/%Y")
        return "—"

    @admin.display(description="Requisições")
    def listar_requisicoes(self, obj: Pedido):
        codigos = [str(link.requisicao.cd_requisicao) for link in obj.requisicao_links.all()]
        return ", ".join(codigos) if codigos else "—"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.prefetch_related("requisicao_links__requisicao", "historico_embarques")
        if "fechado__exact" not in request.GET:
            qs = qs.filter(fechado=False)
        return qs
