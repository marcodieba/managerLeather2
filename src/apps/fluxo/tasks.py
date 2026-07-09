# src/apps/fluxo/tasks.py
from celery import shared_task
from .selectrequisicao import SelectRequisicao
from .select_custo_formula import custo_requisicao
from .selectfilter_lote import SelectFilterLote

@shared_task
def sync_requisicoes_task():
    sincronizador = SelectRequisicao()
    sincronizador.post_requisicao() # <--- Corrigido para o nome exato da função

@shared_task
def sync_custos_task():
    # Se custo_requisicao recebe uma lista de IDs, pode adaptá-la para buscar os pendentes
    custo_requisicao(buscar_todas=True)