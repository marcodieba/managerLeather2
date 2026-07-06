from django.db.models import Sum
from .models import InventarioSemanal, ContagemInventario, Produto

def consolidar_inventario(inventario_id: int):
    inv = InventarioSemanal.objects.get(id=inventario_id)

    agregados = (
        ContagemInventario.objects
        .filter(inventario=inv)
        .values("produto_id")          # produto_id = valor de cd_produto
        .annotate(total=Sum("quantidade"))
    )

    for row in agregados:
        cd_produto = row["produto_id"]         # já é o código que você usa no SQL Server
        total = row["total"] or 0

        produto = Produto.objects.get(cd_produto=cd_produto)
        produto.contagem_fisica = total
        produto.save()

    inv.fechado = True
    inv.save()