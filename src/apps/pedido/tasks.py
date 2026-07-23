# src/apps/pedido/tasks.py
from celery import shared_task
from .selectpedidos import SelectPedidos # Ajuste para o nome da sua classe/função
from .selectformula import SelectFormula

@shared_task
def sync_pedidos_task():
    """Roda a sincronização de pedidos em background"""
    sincronizador = SelectPedidos()
    sincronizador.pedidos_marca()

@shared_task
def sync_formulas_task():
    sincronizador = SelectFormula()
    sincronizador.executar()