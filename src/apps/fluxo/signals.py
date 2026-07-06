# apps/fluxo/signals.py
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.db.models import Sum, signals
from .models import Requisicao  # Assume que Requisicao está em models.py neste app (fluxo)
from src.apps.pedido.models import Pedido # Importe o modelo Pedido
import logging

logger = logging.getLogger(__name__)

# Dicionário global temporário para armazenar PKs de Pedidos afetados durante a exclusão de uma Requisicao
_affected_pedido_pks_on_delete_store = {}


def _atualizar_pedidos_especificos(pedido_pks_set, requisicao_info_for_log="N/A"):
    """
    Atualiza um conjunto específico de Pedidos, recalculando suas quantidades entregues e status.
    """
    if not isinstance(pedido_pks_set, set):
        logger.warning(f"_atualizar_pedidos_especificos chamado com tipo inválido para pedido_pks_set: {type(pedido_pks_set)}")
        return

    for pedido_pk in pedido_pks_set:
        try:
            pedido_a_atualizar = Pedido.objects.get(pk=pedido_pk)

            # Some o campo correto da Requisicao.
            # ESTOU ASSUMINDO 'exp_qt' COMO A QUANTIDADE EXPEDIDA/ENTREGUE DA REQUISICAO.
            # SE FOR OUTRO CAMPO (ex: 'quantidade' ou 'qt'), ALTERE ABAIXO.
            agregacao = Requisicao.objects.filter(
                pedido_links__pedido=pedido_a_atualizar  # Filtra Requisicoes pelo Pedido correto
            ).aggregate(
                soma_total_requisitada=Sum('exp_qt')  # <<< !!! CONFIRME ESTE CAMPO !!!
            )
            
            quantidade_total_calculada = agregacao['soma_total_requisitada'] or 0.0

            pedido_a_atualizar.quantidade_entregue = quantidade_total_calculada
            pedido_a_atualizar.fechado = (
                pedido_a_atualizar.quantidade is not None and
                quantidade_total_calculada >= pedido_a_atualizar.quantidade
            )
            
            # Campos a serem atualizados
            campos_para_salvar = ['quantidade_entregue', 'fechado']
            pedido_a_atualizar.save(update_fields=campos_para_salvar)
            logger.info(
                f"[Pedido Atualizado (Req Acionadora: {requisicao_info_for_log})] "
                f"Pedido PK {pedido_a_atualizar.pk} - qt_entregue={pedido_a_atualizar.quantidade_entregue}, "
                f"fechado={pedido_a_atualizar.fechado}"
            )

        except Pedido.DoesNotExist:
            logger.warning(
                f"Pedido com PK {pedido_pk} não encontrado durante a atualização "
                f"(acionado por Requisição: {requisicao_info_for_log})."
            )
        except Exception as e_inner:
            logger.error(
                f"Erro ao atualizar Pedido PK {pedido_pk} "
                f"(acionado por Requisição: {requisicao_info_for_log}): {e_inner}",
                exc_info=True
            )


@receiver(post_save, sender=Requisicao)
def requisicao_post_save_handler(sender, instance, created, **kwargs):
    """
    Após uma Requisicao ser salva (criada ou atualizada),
    atualiza todos os Pedidos aos quais ela está vinculada.
    """
    pedidos_pks_afetados = set()
    requisicao_id_for_log = instance.id if instance else "ID Desconhecido"
    try:
        # Coleta os PKs de todos os Pedidos vinculados a esta Requisicao
        # Usa o related_name 'pedido_links' de Requisicao -> PedidoRequisicao
        links_de_pedido = instance.pedido_links.select_related('pedido').all()
        for link in links_de_pedido:
            if link.pedido:
                pedidos_pks_afetados.add(link.pedido.pk)
        
        if pedidos_pks_afetados:
            _atualizar_pedidos_especificos(pedidos_pks_afetados, requisicao_info_for_log=requisicao_id_for_log)
    except Exception as e:
        logger.error(
            f"Erro no handler post_save da Requisicao ID {requisicao_id_for_log} ao coletar pedidos afetados: {e}",
            exc_info=True
        )


@receiver(pre_delete, sender=Requisicao)
def requisicao_pre_delete_handler(sender, instance, **kwargs):
    """
    Antes de uma Requisicao ser deletada, armazena os PKs dos Pedidos
    aos quais ela está vinculada. Isso é necessário porque, após a deleção da Requisicao,
    os links em PedidoRequisicao (se on_delete=CASCADE) podem já ter sido removidos.
    """
    global _affected_pedido_pks_on_delete_store
    pedidos_pks_afetados = set()
    requisicao_id_for_log = instance.id if instance else "ID Desconhecido"
    try:
        links_de_pedido = instance.pedido_links.select_related('pedido').all()
        for link in links_de_pedido:
            if link.pedido:
                pedidos_pks_afetados.add(link.pedido.pk)
        
        if pedidos_pks_afetados:
            _affected_pedido_pks_on_delete_store[instance.pk] = pedidos_pks_afetados
        else:
            # Garante que a chave seja removida se não houver links, para evitar stale entries
            _affected_pedido_pks_on_delete_store.pop(instance.pk, None)
    except Exception as e:
        logger.error(
            f"Erro no handler pre_delete da Requisicao ID {requisicao_id_for_log} ao coletar pedidos afetados: {e}",
            exc_info=True
        )
        # Limpa a chave em caso de erro para evitar processamento incorreto no post_delete
        _affected_pedido_pks_on_delete_store.pop(instance.pk, None)


@receiver(post_delete, sender=Requisicao)
def requisicao_post_delete_handler(sender, instance, **kwargs):
    """
    Após uma Requisicao ser deletada, atualiza os Pedidos aos quais ela ESTAVA vinculada,
    usando os PKs armazenados pelo signal pre_delete.
    """
    global _affected_pedido_pks_on_delete_store
    requisicao_pk_deletada = instance.pk 
    
    pedidos_pks_para_atualizar = _affected_pedido_pks_on_delete_store.pop(requisicao_pk_deletada, None)
    
    if pedidos_pks_para_atualizar:
        _atualizar_pedidos_especificos(pedidos_pks_para_atualizar, requisicao_info_for_log=f"{requisicao_pk_deletada} (deletada)")
    elif requisicao_pk_deletada not in _affected_pedido_pks_on_delete_store : # Checa se não foi popado porque estava None
        # Isso pode acontecer se o pre_delete não encontrou links ou teve um erro.
        # O pre_delete já deve ter logado o erro se houve.
        logger.info(f"Nenhum PK de pedido encontrado no store para a Requisicao PK {requisicao_pk_deletada} após deleção.")