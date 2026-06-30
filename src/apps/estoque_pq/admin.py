from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect   # <- AQUI
from django.urls import reverse  


from .models import (
    Produto,
    Couro,
    EnderecoEstoque,
    InventarioSemanal,
    ContagemInventario,
)
from .services import consolidar_inventario


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    search_fields = ["produto", "cd_produto"]
    list_display = ["cd_produto", "produto", "contagem_fisica", "em_transito"]
    actions = ["imprimir_etiquetas_qrcode"]

    def imprimir_etiquetas_qrcode(self, request, queryset):
        cds = ",".join(str(p.cd_produto) for p in queryset)
        url = reverse("estoque_imprimir_etiquetas") + f"?cds={cds}"
        return HttpResponseRedirect(url)

    imprimir_etiquetas_qrcode.short_description = (
        "Imprimir etiquetas QRCode dos produtos selecionados"
    )


@admin.register(Couro)
class CouroAdmin(admin.ModelAdmin):
    search_fields = ["cd_pallet"]


@admin.register(EnderecoEstoque)
class EnderecoEstoqueAdmin(admin.ModelAdmin):
    list_display = ["codigo", "descricao"]
    search_fields = ["codigo", "descricao"]


@admin.register(InventarioSemanal)
class InventarioSemanalAdmin(admin.ModelAdmin):
    list_display = ["referencia", "descricao", "fechado"]
    list_filter = ["fechado"]
    actions = ["action_consolidar_inventarios"]

    def action_consolidar_inventarios(self, request, queryset):
        count = 0
        for inv in queryset:
            if inv.fechado:
                continue
            consolidar_inventario(inv.id)
            count += 1

        if count > 0:
            self.message_user(
                request,
                f"{count} inventário(s) consolidado(s) com sucesso.",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "Nenhum inventário foi consolidado (todos já estavam fechados).",
                level=messages.WARNING,
            )

    action_consolidar_inventarios.short_description = (
        "Consolidar inventário(s) selecionado(s)"
    )


@admin.register(ContagemInventario)
class ContagemInventarioAdmin(admin.ModelAdmin):
    list_display = [
        "inventario",
        "produto",
        "endereco",
        "quantidade",
        "uuid_mobile",
        "atualizado_em",
    ]
    list_filter = ["inventario", "endereco"]
    search_fields = ["produto__produto", "uuid_mobile"]


