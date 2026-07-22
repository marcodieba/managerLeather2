# admin.py
from django.contrib import admin
from django.db.models import Max

from django.urls import path
from django.http import HttpResponse
from django.contrib import messages

# IMPORT CORRIGIDO: Removido a "Etapa"
from .models import Requisicao, FluxoRequisicao, Artigo, CustoRequisicao, Refilo, Processo, RoteiroArtigo, Operador, Justificativa, RequisicaoJustificativa
from django.templatetags.static import static
from .forms import RequisicaoForm

from src.apps.pedido.models import PedidoRequisicao
from .selectrequisicao import SelectRequisicao
from datetime import date
# pyrefly: ignore [missing-import]
from django.utils import timezone
# pyrefly: ignore [missing-import]
from django.forms.models import BaseInlineFormSet
from django.urls import reverse
from django.http import HttpResponseRedirect
import pymssql


@admin.action(description='Atualizar Requisições Selecionadas')
def update_requisicao_action(modeladmin, request, queryset):
    try:
        SelectRequisicao().post_requisicao()
        modeladmin.message_user(request, "Requisições atualizadas com sucesso!", messages.SUCCESS)
    except Exception as e:
        modeladmin.message_user(request, f"Erro ao atualizar: {e}", messages.ERROR)

def imprimir_rendimento(modeladmin, request, queryset):
    ids = ",".join(str(obj.pk) for obj in queryset)
    return HttpResponseRedirect(reverse("imprimir_rendimento") + f"?ids={ids}&tipo=rendimento")
imprimir_rendimento.short_description = "🖨️ Imprimir Rendimento"

def imprimir_fluxograma(modeladmin, request, queryset):
    ids = ",".join(str(obj.pk) for obj in queryset)
    return HttpResponseRedirect(reverse("imprimir_rendimento") + f"?ids={ids}&tipo=fluxograma")
imprimir_fluxograma.short_description = "🖨️ Imprimir Fluxograma"

def imprimir_custo(modeladmin, request, queryset):
    cd_requisicao = ",".join(str(obj.cd_requisicao) for obj in queryset)
    ids = ",".join(str(obj.pk) for obj in queryset)
    return HttpResponseRedirect(reverse("imprimir_rendimento") + f"?ids={ids}&cd_requisicao={cd_requisicao}&tipo=custo")
imprimir_custo.short_description = "🖨️ Imprimir Custo"

def imprimir_fluxo_detalhado(modeladmin, request, queryset):
    ids = ",".join(str(obj.pk) for obj in queryset)
    return HttpResponseRedirect(reverse("imprimir_rendimento") + f"?ids={ids}&tipo=fluxo_detalhado")
imprimir_fluxo_detalhado.short_description = "🖨️ Imprimir Fluxo Detalhado"


@admin.action(description='Gerar Rendimento')
def requisicao_sea(modeladmin, request, queryset):
    con = pymssql.connect(host='192.168.20.250',
                            port='1433',
                            user='sa',
                            password='CR@R2018c',
                            database='Marca_Evolution'
                            )
    cursor = con.cursor()
    lista_lote = []
    for obj in queryset:
        cursor.execute(f"""WITH Base AS (
            SELECT 
                Pedido_Comercial_Artigo_Programacao.Marca_no_Couro, 
                ISNULL(Quantidade_WB, Quantidade_SA) AS Quantidade_WB, 
                ISNULL(Pes2_M2_WB, Pes2_M2_SA) AS Pes2_M2_WB, 
                CASE 
                    WHEN ISNULL(Quantidade_WB, Quantidade_SA) > 0 
                    THEN CONVERT(Numeric(18,2), ISNULL(Pes2_M2_WB, Pes2_M2_SA) / ISNULL(Quantidade_WB, Quantidade_SA)) 
                    ELSE NULL 
                END AS Media_WB,
                ISNULL(Qt_Expedicao, 0) AS Quantidade_Exp, 

                ISNULL((
                    SELECT SUM(EES.Qt_Expedicao) 
                    FROM Estoque_Expedicao_SeA EES 
                    WHERE EES.Cd_Pedido_Comercial_Movimento_OS = Pedido_Comercial_Artigo_Programacao.Codigo 
                    AND (
                        (EES.Dt_Expedicao >= CONVERT(datetime, '01/04/2025') AND EES.Dt_Expedicao <= CONVERT(datetime, '09/04/2025')) 
                        OR EES.Dt_Expedicao IS NULL
                    )
                ), 0) AS Qt_Exp_Tot,

                Estoque_Expedicao_SeA.M2_Pes2 AS Pes2_M2_Exp,

                CASE 
                    WHEN Qt_Expedicao > 0 
                    THEN CONVERT(Numeric(18,2), Pedido_Comercial_Artigo_Programacao.Pes2_M2_Exp / Qt_Expedicao) 
                    ELSE NULL 
                END AS Media_Exp,

                Nr_Item_Pedido,
                Sea_Artigo.Nome + RTRIM(' ' + ISNULL(Sea_Artigo_Cor.Nome, '')) + RTRIM(' ' + ISNULL(WB_Sea_Espessura.Nome, '')) + ' ' + Classificacao AS Artigo,

                CASE 
                    WHEN Produto_Unidade.Nome_Resumido = 'M2' 
                    THEN Pedido_Comercial_Artigo.Quantidade * 10.764 
                    ELSE Pedido_Comercial_Artigo.Quantidade 
                END AS Quantidade_Pedido_Pes2,

                Pedido_Tipo.Nome AS Pedido_Tipo,
                Dt_Pedido,
                Dt_Expedicao,

                CASE 
                    WHEN ISNULL(Quantidade_WB, Quantidade_SA) IS NULL THEN '1-WB' 
                    WHEN Dt_Expedicao IS NULL THEN '2-PROD.' 
                    WHEN Quantidade_SA IS NULL THEN '3-EXP.' 
                    ELSE '4-SA_EXP' 
                END AS Wb_Prod_Expedido,

                ISNULL((
                    SELECT SUM(Qt_Expedicao) 
                    FROM Estoque_Expedicao_SeA EES 
                    WHERE EES.Cd_Pedido_Comercial_Movimento_OS = Pedido_Comercial_Artigo_Programacao.Codigo
                ), 0) AS Qt_Tot_Exp,

                ISNULL((
                    SELECT COUNT(*) 
                    FROM Estoque_Expedicao_SeA EES 
                    WHERE EES.Cd_Pedido_Comercial_Movimento_OS = Pedido_Comercial_Artigo_Programacao.Codigo
                ), 0) AS Qt_Tot_Exp_It,

                CASE 
                    WHEN A.Unid_em_Couro = 1 THEN 'INTEIRO' 
                    ELSE 'MEIO' 
                END AS Int_Meio

            FROM Pedido_Comercial_Artigo_Programacao 
            INNER JOIN Pedido_Comercial_Artigo ON Pedido_Comercial_Artigo_Programacao.Cd_Pedido_Comercial_Artigo = Pedido_Comercial_Artigo.Codigo
            INNER JOIN Pedido_Comercial ON Pedido_Comercial.Codigo = Pedido_Comercial_Artigo.Cd_Pedido_Comercial
            INNER JOIN Fornecedor_Cliente_CNPJ ON Fornecedor_Cliente_CNPJ.Codigo = Pedido_Comercial.Cd_Cliente_CNPJ
            INNER JOIN Pedido_Tipo ON Pedido_Tipo.Codigo = Pedido_Comercial.Cd_Pedido_Tipo
            INNER JOIN Cidade ON Cidade.Codigo = Fornecedor_Cliente_CNPJ.Cd_Cidade
            INNER JOIN Pais ON Pais.Codigo = Fornecedor_Cliente_CNPJ.Cd_Pais
            LEFT OUTER JOIN Sea_Artigo ON Sea_Artigo.Codigo = Pedido_Comercial_Artigo.Cd_Sea_Artigo
            LEFT OUTER JOIN Sea_Artigo_Cor ON Sea_Artigo_Cor.Codigo = Pedido_Comercial_Artigo.Cd_Sea_Artigo_Cor
            LEFT OUTER JOIN WB_Sea_Espessura ON WB_Sea_Espessura.Codigo = Pedido_Comercial_Artigo.Cd_Sea_Espessura_Final
            LEFT OUTER JOIN Produto_Unidade ON Produto_Unidade.Codigo = Pedido_Comercial_Artigo.Cd_Produto_Unidade
            LEFT OUTER JOIN Estoque_Expedicao_SeA ON Cd_Pedido_Comercial_Movimento_OS = Pedido_Comercial_Artigo_Programacao.Codigo
            LEFT OUTER JOIN Fornecedor_Cliente Representante ON Representante.Codigo = ISNULL(Pedido_Comercial.Cd_Representante, Fornecedor_Cliente_CNPJ.Cd_Representante)
            LEFT OUTER JOIN Estoque_Expedicao EE ON EE.Cd_Pedido_Comercial_artigo_Programacao = Pedido_Comercial_Artigo_Programacao.Codigo
            LEFT OUTER JOIN WB_Artigo A ON A.Codigo = EE.Cd_WB_Artigo

            WHERE 
                ((Dt_Expedicao >= CONVERT(datetime, '01/04/2024') AND Dt_Expedicao <= CONVERT(datetime, '08/04/2025')) OR Dt_Expedicao IS NULL)
                AND Pedido_Comercial_Artigo_Programacao.Cd_Unidade_de_Producao = 1
                AND Pedido_Comercial_Artigo_Programacao.Marca_no_Couro = '{obj.lote}'
        )

        SELECT TOP 1
            Marca_no_Couro,
            Quantidade_WB,
            Pes2_M2_WB,
            Media_WB,
            Qt_Exp_Tot,
            SUM(Pes2_M2_Exp) OVER () AS Pes2_M2_Exp,
            Media_Exp,
            Nr_Item_Pedido,
            Artigo,
            Quantidade_Pedido_Pes2,
            Pedido_Tipo,
            Dt_Pedido,
            Dt_Expedicao,
            Wb_Prod_Expedido,
            Qt_Tot_Exp,
            Qt_Tot_Exp_It,
            Int_Meio
        FROM Base;
        """)
        row = cursor.fetchone()
        try:
            if row is not None:
                Requisicao.objects.filter(pk=obj.id).update(qt=row[1], m2=row[2], am=row[3], exp_qt=row[4], exp_m2=round(row[5]), exp_am=row[5]/row[4], rend=round((0-((row[2]-row[5])/row[2]*100)),2))
                lista_lote.append([row])
        except:
            continue
    modeladmin.message_user(request, f'{queryset.count()} produtos foram marcados como ativos.', messages.SUCCESS)

# pyrefly: ignore [missing-import]
from django.contrib.admin import SimpleListFilter

class TemPedidoFilter(SimpleListFilter):
    title = 'Possui Pedido'
    parameter_name = 'tem_pedido'

    def lookups(self, request, model_admin):
        return (
            ('sim', 'Sim'),
            ('nao', 'Não'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'sim':
            return queryset.filter(pedido_links__isnull=False).distinct()
        if self.value() == 'nao':
            return queryset.filter(pedido_links__isnull=True)
        return queryset

# --- NOVAS CONFIGURAÇÕES DE ROTEIRO ---
class RoteiroArtigoInline(admin.TabularInline):
    model = RoteiroArtigo
    extra = 1
    ordering = ('ordem',)



@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    search_fields = ['nome']

from django.db import transaction

@admin.register(Artigo)
class ArtigosAdmin(admin.ModelAdmin):
    list_display = ('nome', 'meta_mes')
    search_fields = ('nome',)
    inlines = [RoteiroArtigoInline]

    def save_related(self, request, form, formsets, change):
        # 🔥 deixa o Django salvar TUDO primeiro
        super().save_related(request, form, formsets, change)

        # 🔥 agora o banco está consistente
        with transaction.atomic():
            itens = RoteiroArtigo.objects.filter(
                artigo=form.instance
            ).order_by('id')

            for i, item in enumerate(itens, start=1):
                if item.ordem != i:
                    item.ordem = i
                    item.save(update_fields=['ordem'])

# --- INLINES DA REQUISIÇÃO ---
class FluxoRequisicaoInlineFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.forms:
            if form.instance.pk is None:
                form.initial['encerrado'] = False
                form.initial['quantidade'] = 0
                form.initial['dt_processo'] = timezone.now()

class FluxoRequisicaoInline(admin.TabularInline):
    model = FluxoRequisicao
    extra = 1
    formset = FluxoRequisicaoInlineFormSet
    autocomplete_fields = ['processo'] # Facilita achar o processo

class CustoRequisicaoInline(admin.TabularInline):
    model = CustoRequisicao
    extra = 1
    autocomplete_fields = ['produto']

class RefiloInlineFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i, form in enumerate(self.forms):
            if form.instance.pk is None:
                form.initial['qt_refilo'] = 0

class RefiloInline(admin.TabularInline):
    model = Refilo
    extra = 4
    formset = RefiloInlineFormSet

class PedidoRequisicaoInline(admin.TabularInline):
    model = PedidoRequisicao
    extra = 1
    autocomplete_fields = ['pedido']


# --- O ADMIN PRINCIPAL DA REQUISIÇÃO ---
@admin.register(Requisicao)
class RequisicaoAdmin(admin.ModelAdmin):
    form = RequisicaoForm
    inlines = [RefiloInline, FluxoRequisicaoInline, CustoRequisicaoInline, PedidoRequisicaoInline]

    # Ativa a lupa de pesquisa no campo do Artigo Genérico
    autocomplete_fields = ['artigo_padrao'] 

    # AQUI ESTAVA O PROBLEMA! O artigo_padrao precisa estar no fieldsets para aparecer na tela
    fieldsets = [
                ('Requisição Essencial', {
                    'classes': ('wide',),
                    'fields': [
                        ('setor','cd_requisicao',),
                        ('artigo','artigo_padrao',), # <--- AGORA ELE VAI APARECER NA TELA DE EDIÇÃO
                        ('classe', 'espessura'),
                        ('cor', 'fulao'),
                        ('lote', 'ficha'),
                        ('pallet', 'quantidade'),
                        ('qt_mt', 'encerrado'),
                        ('obs'),
                    ]
                }),
                ('Custos e Rendimento', {
                    'classes': ('wide',),
                    'fields': [
                        ('custo_requisicao_inicial', 'custo_requisicao'),
                        ('rendimento_custo', 'kg_blue'),
                        ('seco',),
                    ]
                }),
            ]
    
    list_display = ('cd_requisicao','data_criacao_formatada', 'listar_pedido', 'fulao', 'lote', 'pallet','quantidade','qt_mt','artigo', 'get_artigos')
    list_select_related = True
    search_fields = ('cd_requisicao', 'lote', 'artigo', 'fulao')
    list_filter = [TemPedidoFilter]
    ordering = ('-dt_requisicao',)
    actions = [update_requisicao_action, requisicao_sea, imprimir_rendimento, imprimir_fluxograma, imprimir_custo, imprimir_fluxo_detalhado]

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',)
        }
        js = (static('fluxo/admin_autocomplete.js'),)
    
    def has_add_permission(self, request):
        return False  
    
    def data_criacao_formatada(self, obj):
        return obj.dt_requisicao.strftime('%d/%m/%Y')
    data_criacao_formatada.short_description = 'Data de Criação'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        SelectRequisicao()
        return qs.filter(encerrado=False)

    # AQUI CORRIGIMOS A COLUNA NA LISTA PARA MOSTRAR O ARTIGO VINCULADO
    def get_artigos(self, obj):
        if obj.artigo_padrao:
            return obj.artigo_padrao.nome
        return '⚠️ Sem Vínculo'
    get_artigos.short_description = 'Artigo Genérico'

    def listar_pedido(self, obj):
        return ", ".join(
            str(link.pedido.nr_contract)
            for link in obj.pedido_links.select_related('pedido')
        )
    listar_pedido.short_description = "Pedidos"
    
    change_list_template = "admin/pedido_changelist.html"

    def changelist_view(self, request, extra_context=None):
        if request.method == "POST" and 'executar-funcao' in request.POST:
            SelectRequisicao
            self.message_user(request, "Função executada com sucesso!", messages.SUCCESS)
            return HttpResponseRedirect(request.path)
        return super().changelist_view(request, extra_context=extra_context)
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('executar-selectrequisicao/', self.admin_site.admin_view(self.executar_select_requisicao), name='executar_selectrequisicao'),
        ]
        return custom_urls + urls

    def executar_select_requisicao(self, request):
        try:
            SelectRequisicao().post_requisicao()
            self.message_user(request, "Requisições atualizadas com sucesso!", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Erro ao atualizar: {e}", messages.ERROR)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../'))


@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    list_display = ("usuario", "listar_processos")
    search_fields = (
        "usuario__username",
        "usuario__first_name",
        "processos__nome",
    )
    filter_horizontal = ("processos",)

    def listar_processos(self, obj):
        return ", ".join(
            obj.processos.values_list("nome", flat=True)
        )

    listar_processos.short_description = "Processos"

@admin.register(Justificativa)
class JustificativaAdmin(admin.ModelAdmin):
    list_display = ('nome',)
    search_fields = ('nome',)

@admin.register(RequisicaoJustificativa)
class RequisicaoJustificativaAdmin(admin.ModelAdmin):
    list_display = ('requisicao', 'justificativa', 'quantidade', 'm2_proporcional')
    search_fields = ('requisicao__cd_requisicao', 'justificativa__nome')