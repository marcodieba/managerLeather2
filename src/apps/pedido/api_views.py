# apps/pedido/api_views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta, datetime

from .serializers import EmbarqueSerializer, VeiculoSerializer, TipoVeiculoSerializer
from src.apps.fluxo.models import Requisicao # Ajuste conforme seu projeto

from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth
from collections import OrderedDict

from .serializers import PedidoSerializer
from .views import (
    get_pedidos_base_queryset, 
    anexa_processos_consolidados, 
    get_grupo_artigo, 
    MESES_DO_ANO
)

from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date

from .models import (
    Pedido, Embarque, ItemEmbarque, Veiculo, TipoVeiculo, Transportadora,
    PrevisaoEmbarque, PrevisaoItemEmbarque, ReservaEmbarque
)
from .views import executar_query_romaneio, _pes2_to_m2


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dashboard(request):
    """Retorna os dados do Dashboard Gerencial em formato JSON"""
    agora = timezone.now()
    trinta_dias_atras = agora - timedelta(days=30)

    # 1. MÉTRICAS COMERCIAL
    pedidos_abertos = Pedido.objects.filter(fechado=False)
    total_carteira_m2 = pedidos_abertos.aggregate(total=Sum('quantidade'))['total'] or 0
    
    pedidos_pendentes = [p for p in pedidos_abertos if p.saldo_a_entregar > 0]
    total_pendente_m2 = sum(p.saldo_a_entregar for p in pedidos_pendentes)
    
    pedidos_atrasados = [
        p for p in pedidos_pendentes 
        if p.dt_programada and p.dt_programada.date() < agora.date()
    ]
    m2_atrasado = sum(p.saldo_a_entregar for p in pedidos_atrasados)

    # 2. MÉTRICAS PRODUÇÃO
    reqs_recentes = Requisicao.objects.filter(dt_requisicao__gte=trinta_dias_atras)
    total_reqs_abertas = reqs_recentes.filter(encerrado=False).count()
    producao_m2 = reqs_recentes.filter(encerrado=False).aggregate(total=Sum('m2'))['total'] or 0
    producao_pecas = reqs_recentes.filter(encerrado=False).aggregate(total=Sum('quantidade'))['total'] or 0

    # 3. MÉTRICAS LOGÍSTICA
    embarques_mes = Embarque.objects.filter(data_embarque__month=agora.month, data_embarque__year=agora.year)
    embarques_abertos = embarques_mes.filter(finalizado=False).count()
    embarques_finalizados = embarques_mes.filter(finalizado=True).count()
    volume_embarcado_mes = ItemEmbarque.objects.filter(
        embarque__data_embarque__month=agora.month,
        embarque__data_embarque__year=agora.year
    ).aggregate(total=Sum('metragem_embarcada'))['total'] or 0

    return Response({
        "comercial": {
            "total_carteira_m2": total_carteira_m2,
            "total_pendente_m2": total_pendente_m2,
            "qtd_pedidos_atrasados": len(pedidos_atrasados),
            "m2_atrasado": m2_atrasado,
        },
        "producao": {
            "total_reqs_abertas": total_reqs_abertas,
            "producao_m2": producao_m2,
            "producao_pecas": producao_pecas,
        },
        "logistica": {
            "embarques_abertos": embarques_abertos,
            "embarques_finalizados": embarques_finalizados,
            "volume_embarcado_mes": volume_embarcado_mes,
        },
        "referencia": {
            "mes_atual": agora.strftime("%m/%Y")
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_embarques_list(request):
    """Equivale a embarques_list_view e embarque_detail_view, mas via API"""
    embarque_id = request.GET.get('id')
    
    # Se passar ID, retorna detalhes de 1 embarque
    if embarque_id:
        try:
            embarque = Embarque.objects.get(pk=embarque_id)
            serializer = EmbarqueSerializer(embarque)
            return Response(serializer.data)
        except Embarque.DoesNotExist:
            return Response({"erro": "Embarque não encontrado"}, status=404)

    # Senão, lista tudo com filtros
    qs = Embarque.objects.all().order_by("-data_embarque", "-id")
    
    dt_ini = request.GET.get("dt_ini")
    dt_fim = request.GET.get("dt_fim")
    finalizado = request.GET.get("finalizado")

    if dt_ini: qs = qs.filter(data_embarque__gte=dt_ini)
    if dt_fim: qs = qs.filter(data_embarque__lte=dt_fim)
    if finalizado in ("0", "1"): qs = qs.filter(finalizado=(finalizado == "1"))

    serializer = EmbarqueSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dados_simulador(request):
    """Retorna os dados base necessários para preencher os selects do simulador no React"""
    veiculos = Veiculo.objects.all().select_related("tipo", "transportadora").order_by("placa")
    tipos = TipoVeiculo.objects.all().order_by("nome")
    
    return Response({
        "veiculos": VeiculoSerializer(veiculos, many=True).data,
        "tipos_veiculo": TipoVeiculoSerializer(tipos, many=True).data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_relatorio_por_artigo(request):
    """
    Retorna a estrutura completa do relatório imprimirpedidoview em JSON,
    preservando agrupamentos e somas originais.
    """
    ids_str = request.GET.get("ids", "")
    ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()] if ids_str else []

    pedidos_selecionados = get_pedidos_base_queryset(ids).order_by("artigo", "cliente")
    anexa_processos_consolidados(pedidos_selecionados)

    totais_qt_por_grupo = {}
    totais_saldo_por_grupo = {}

    for pedido in pedidos_selecionados:
        grupo = get_grupo_artigo(pedido.artigo)
        totais_qt_por_grupo[grupo] = totais_qt_por_grupo.get(grupo, 0) + float(pedido.quantidade or 0)
        totais_saldo_por_grupo[grupo] = totais_saldo_por_grupo.get(grupo, 0) + float(pedido.saldo_a_entregar or 0)

    totais_mensais_query = (
        pedidos_selecionados.filter(dt_programada__isnull=False)
        .annotate(mes_ano=TruncMonth("dt_programada"))
        .values("artigo", "mes_ano")
        .annotate(total_qt_mes=Sum("quantidade"))
        .order_by("artigo", "mes_ano")
    )

    totais_artigo_por_mes = {}
    for item in totais_mensais_query:
        grupo_artigo = get_grupo_artigo(item["artigo"])
        mes_display = f"{MESES_DO_ANO[item['mes_ano'].month]}/{item['mes_ano'].year}"
        totais_artigo_por_mes.setdefault(grupo_artigo, OrderedDict())
        totais_artigo_por_mes[grupo_artigo][mes_display] = totais_artigo_por_mes[grupo_artigo].get(mes_display, 0) + (
            item["total_qt_mes"] or 0
        )

    pedidos_agrupados_final = OrderedDict()
    totais_prod_por_grupo = {}

    def soma_producao(_links):
        return 0

    for pedido in pedidos_selecionados:
        grupo_artigo = get_grupo_artigo(pedido.artigo)
        cliente = pedido.cliente or "CLIENTE NÃO ESPECIFICADO"
        pedidos_agrupados_final.setdefault(grupo_artigo, OrderedDict())
        pedidos_agrupados_final[grupo_artigo].setdefault(cliente, [])
        
        # Serialização do objeto Pedido para trafegar em JSON
        pedido_data = PedidoSerializer(pedido).data
        
        # Garante o transporte dos processos anexados dinamicamente
        if hasattr(pedido, 'processos_consolidados_requisitantes'):
            pedido_data['processos_consolidados_requisitantes'] = [
                {
                    "id": p.id,
                    "processo_nome": p.processo.nome if p.processo else "Desconhecido",
                    "dt_processo": p.dt_processo.isoformat() if p.dt_processo else None
                } for p in pedido.processos_consolidados_requisitantes
            ]
            
        pedidos_agrupados_final[grupo_artigo][cliente].append(pedido_data)

        totais_prod_por_grupo[grupo_artigo] = totais_prod_por_grupo.get(grupo_artigo, 0) + soma_producao(
            pedido.requisicao_links.all()
        )

    totais_por_artigo_final = {}
    for grupo, total_qt in totais_qt_por_grupo.items():
        totais_por_artigo_final[grupo] = {
            "total_qt": total_qt,
            "total_prod": totais_prod_por_grupo.get(grupo, 0),
            "total_saldo": totais_saldo_por_grupo.get(grupo, 0),
        }

    return Response({
        "pedidos_agrupados_por_artigo_e_cliente": pedidos_agrupados_final,
        "totais_por_artigo": totais_por_artigo_final,
        "totais_artigo_por_mes": totais_artigo_por_mes,
        "data_atual": timezone.now()
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_relatorio_por_data(request):
    """
    Retorna a estrutura completa do relatório imprimirpedidodataview em JSON,
    contendo os cálculos dinâmicos de prazos e subtotais mensais.
    """
    pedidos_selecionados = (
        Pedido.objects.filter(dt_programada__isnull=False)
        .filter(Q(fechado=False) | Q(fechado__isnull=True))
        .prefetch_related("historico_embarques")
        .order_by("dt_programada", "cliente", "unidade_medida")
    )

    ids_str = request.GET.get("ids", "")
    if ids_str:
        ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
        if ids:
            pedidos_selecionados = pedidos_selecionados.filter(id__in=ids)

    totais_mensais_query = (
        pedidos_selecionados.annotate(mes=TruncMonth("dt_programada"))
        .values("mes", "unidade_medida")
        .annotate(total_quantidade=Sum("quantidade"))
        .order_by("mes", "unidade_medida")
    )

    totais_mensais_dict = {}
    for total in totais_mensais_query:
        mes_chave = f"{total['mes'].year}-{total['mes'].month:02d}"
        unidade = total["unidade_medida"] or "N/D"
        totais_mensais_dict.setdefault(mes_chave, OrderedDict())[unidade] = total["total_quantidade"]

    pedidos_agrupados = OrderedDict()
    agora = timezone.now()

    for pedido in pedidos_selecionados:
        artigo_nome = (pedido.artigo or "").lower()
        dias_antecedencia = 20 if "nobuck" in artigo_nome else 11

        previsao_inicio = pedido.dt_programada - timedelta(days=dias_antecedencia)
        prazo = pedido.dt_programada
        delta = prazo - agora

        if delta.total_seconds() < 0:
            atraso = abs(delta)
            if atraso.days >= 1:
                status_prazo_texto = f"Atrasado há {atraso.days} dia(s)"
            else:
                horas = int(atraso.total_seconds() // 3600)
                status_prazo_texto = f"Atrasado há {horas} hora(s)"
            status_prazo_classe = "atrasado"
        elif prazo.date() == agora.date():
            status_prazo_texto = "Vence hoje"
            status_prazo_classe = "hoje"
        else:
            dias_restantes = delta.days
            status_prazo_texto = f"Faltam {dias_restantes} dia(s)"
            status_prazo_classe = "adiantado"

        mes_chave = f"{pedido.dt_programada.year}-{pedido.dt_programada.month:02d}"
        if mes_chave not in pedidos_agrupados:
            pedidos_agrupados[mes_chave] = {
                "items": [],
                "subtotais": totais_mensais_dict.get(mes_chave, {}),
                "mes_display": f"{MESES_DO_ANO[pedido.dt_programada.month]} - {pedido.dt_programada.year}",
                "clientes": OrderedDict(),
            }

        # Serialização base e injeção das propriedades calculadas na view
        pedido_data = PedidoSerializer(pedido).data
        pedido_data['previsao_inicio'] = previsao_inicio.isoformat()
        pedido_data['status_prazo_texto'] = status_prazo_texto
        pedido_data['status_prazo_classe'] = status_prazo_classe

        pedidos_agrupados[mes_chave]["items"].append(pedido_data)
        
        nome_cliente = str(pedido.cliente)
        pedidos_agrupados[mes_chave]["clientes"].setdefault(nome_cliente, {})
        unidade = pedido.unidade_medida or "N/D"
        pedidos_agrupados[mes_chave]["clientes"][nome_cliente].setdefault(unidade, 0)
        pedidos_agrupados[mes_chave]["clientes"][nome_cliente][unidade] += float(pedido.quantidade or 0)

    for grupo in pedidos_agrupados.values():
        grupo["clientes"] = OrderedDict(sorted(grupo["clientes"].items(), key=lambda x: x[0].lower()))

    return Response({"pedidos_agrupados": pedidos_agrupados, "data_atual": agora})


# --- FUNÇÃO AUXILIAR DE VEÍCULOS (Mantida a lógica original) ---
def _resolver_veiculo_obrigatorio(veiculo_id, tipo_veiculo_id):
    if veiculo_id:
        return Veiculo.objects.select_related("tipo", "transportadora").get(pk=veiculo_id)

    if not tipo_veiculo_id:
        raise ValidationError("Selecione um veículo cadastrado OU um tipo de veículo (padrão).")

    tipo = TipoVeiculo.objects.get(pk=tipo_veiculo_id)
    transp, _ = Transportadora.objects.get_or_create(
        nome="NÃO INFORMADA", defaults={"cnpj": None, "contato": None}
    )

    placa_generica = f"GEN-{tipo.nome.upper()[:7]}"
    v, _ = Veiculo.objects.get_or_create(
        placa=placa_generica,
        defaults={"transportadora": transp, "tipo": tipo, "motorista": None},
    )

    changed = False
    if v.tipo_id != tipo.id:
        v.tipo = tipo
        changed = True
    if v.transportadora_id != transp.id:
        v.transportadora = transp
        changed = True
    if changed:
        v.save(update_fields=["tipo", "transportadora"])
    return v


# --- APIS DE LOGÍSTICA ---

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_romaneio_pallets(request):
    """Consulta pallets de um romaneio no banco legado MSSQL"""
    cd_romaneio = request.query_params.get("cd_romaneio", "").strip()
    if not cd_romaneio:
        return Response({"erro": "Informe cd_romaneio."}, status=400)

    try:
        linhas = executar_query_romaneio(cd_romaneio)
    except Exception as e:
        return Response({"erro": f"Erro ao consultar romaneio: {str(e)}"}, status=500)

    itens = []
    for row in linhas:
        seq = str(row.get("seq_ped_entrega") or "").strip()
        nr_pallet = str(row.get("nr_pallet") or "").strip()
        pallet = str(row.get("pallet") or "").strip()
        pes2 = row.get("pes2")
        m2 = _pes2_to_m2(pes2)

        pedido = Pedido.objects.filter(nr_pedido_interno=seq).first()
        if not pedido:
            itens.append({
                "ok": False, "erro": f"Pedido não encontrado para Seq={seq}",
                "nr_pallet": nr_pallet, "pallet": pallet, "m2": m2
            })
            continue

        itens.append({
            "ok": True, "pedido_id": pedido.id, "seq_ped_entrega": seq,
            "nr_contract": pedido.nr_contract, "nr_pedido_interno": pedido.nr_pedido_interno,
            "cliente": row.get("cliente") or pedido.cliente,
            "produto": row.get("produto") or pedido.produto,
            "cd_romaneio_faturamento": cd_romaneio,
            "nr_pallet": nr_pallet, "pallet": pallet, "pes2": pes2, "m2": m2,
            "peso_liquido": row.get("peso_pallet_lq"), "pecas": row.get("pecas"),
            "saldo_pedido_m2": pedido.saldo_a_entregar,
        })

    return Response({"cd_romaneio": cd_romaneio, "items": itens})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_salvar_layout_logistica(request):
    """Salva o layout do caminhão (Embarque real)"""
    data = request.data # O DRF já converte o JSON automaticamente!
    
    cd_romaneio = str(data.get("cd_romaneio_faturamento") or "").strip()
    data_embarque = data.get("data_embarque")
    itens = data.get("itens") or []

    if not cd_romaneio or not data_embarque or not itens:
        return Response({"erro": "cd_romaneio, data_embarque e itens são obrigatórios."}, status=400)

    with transaction.atomic():
        try:
            veiculo = _resolver_veiculo_obrigatorio(data.get("veiculo_id"), data.get("tipo_veiculo_id"))
        except (ValidationError, Exception) as e:
            return Response({"erro": str(e)}, status=400)

        embarque = Embarque.objects.create(
            veiculo=veiculo, data_embarque=data_embarque,
            mapa_carga_json=data.get("mapa_carga_json"), finalizado=False
        )

        criados = 0
        for it in itens:
            seq = str(it.get("seq_ped_entrega") or "").strip()
            nr_pallet = str(it.get("nr_pallet") or "").strip()
            pallet = str(it.get("pallet") or "").strip()
            
            pedido = Pedido.objects.filter(nr_pedido_interno=seq).first()
            if not pedido:
                return Response({"erro": f"Pedido {seq} não encontrado."}, status=400)

            m2 = _pes2_to_m2(it.get("pes2"))
            saldo_permitido = float(pedido.saldo_a_entregar or 0) * 1.5 # 50% de tolerância
            
            if m2 > saldo_permitido:
                return Response({"erro": f"Pallet {pallet}: m² ({m2:.2f}) excede saldo +50% ({saldo_permitido:.2f})."}, status=400)

            try:
                ItemEmbarque.objects.create(
                    embarque=embarque, pedido=pedido, metragem_embarcada=m2,
                    cd_romaneio_faturamento=cd_romaneio, nr_pallet=nr_pallet, pallet=pallet,
                    pes2_original=it.get("pes2"), peso_liquido=it.get("peso_liquido"), pecas=it.get("pecas"),
                    pos_x=float(it.get("pos_x") or 0), pos_y=float(it.get("pos_y") or 0),
                    pos_z=int(it.get("pos_z") or 0), largura=float(it.get("largura") or 1.2),
                    comprimento=float(it.get("comprimento") or 1.0), altura=float(it.get("altura") or 1.0),
                    rotacionado=bool(it.get("rotacionado") or False)
                )
                criados += 1
            except IntegrityError:
                return Response({"erro": f"Pallet {pallet} já embarcado noutro momento."}, status=409)

    return Response({"mensagem": "Carga salva!", "embarque_id": embarque.id, "itens_criados": criados}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_iniciar_logistica_previsao(request):
    """Inicia um planeamento de logística (Pré-Embarque)"""
    data = request.data
    data_embarque_str = data.get("data_embarque")
    itens = data.get("itens") or []

    if not data_embarque_str or not itens:
        return Response({"erro": "data_embarque e itens são obrigatórios."}, status=400)

    with transaction.atomic():
        try:
            veiculo = _resolver_veiculo_obrigatorio(data.get("veiculo_id"), data.get("tipo_veiculo_id"))
        except Exception as e:
            return Response({"erro": str(e)}, status=400)

        embarque = Embarque.objects.create(veiculo=veiculo, data_embarque=data_embarque_str, finalizado=False)

        criados = 0
        for it in itens:
            nr_contract = (it.get("nr_contract") or "").strip()
            nr_pedido_interno = (it.get("nr_pedido_interno") or "").strip()
            m2_prev = float(it.get("m2_previsto") or 0)

            pedido = Pedido.objects.filter(nr_contract=nr_contract).first() or Pedido.objects.filter(nr_pedido_interno=nr_pedido_interno).first()
            if not pedido:
                return Response({"erro": f"Pedido {nr_contract} não encontrado."}, status=400)

            ReservaEmbarque.objects.create(embarque=embarque, pedido=pedido, metragem_prevista_m2=m2_prev)
            criados += 1

    return Response({"mensagem": "Logística iniciada (previsão).", "embarque_id": embarque.id, "reservas_criadas": criados}, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_listar_embarques_previstos(request):
    """
    Lista embarques previstos por data e filtro de texto (placa/transportadora).
    """
    data_str = request.query_params.get("data")
    q = request.query_params.get("q", "").strip()

    if not data_str:
        return Response({"erro": "O parâmetro 'data' é obrigatório (YYYY-MM-DD)."}, status=400)

    try:
        data = parse_date(data_str)
    except Exception:
        data = None
        
    if not data:
        return Response({"erro": "Data inválida."}, status=400)

    qs = (
        Embarque.objects
        .select_related("veiculo", "veiculo__tipo", "veiculo__transportadora")
        .filter(data_embarque=data)
        .order_by("veiculo__transportadora__nome", "veiculo__placa")
    )

    if q:
        qs = qs.filter(
            Q(veiculo__placa__icontains=q) |
            Q(veiculo__transportadora__nome__icontains=q)
        )

    embarques_data = []
    for e in qs[:50]:
        embarques_data.append({
            "id": e.id,
            "data": e.data_embarque.isoformat(),
            "placa": e.veiculo.placa,
            "tipo": e.veiculo.tipo.nome,
            "transportadora": e.veiculo.transportadora.nome,
            "finalizado": bool(e.finalizado),
        })

    return Response({"items": embarques_data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_salvar_previsao_logistica(request):
    """
    Salva uma PrevisaoEmbarque e os seus itens (PrevisaoItemEmbarque).
    """
    data_prevista_str = request.data.get("data_prevista")
    observacao = (request.data.get("observacao") or "").strip()
    itens = request.data.get("itens") or []

    if not data_prevista_str or not itens:
        return Response({"erro": "data_prevista e itens são obrigatórios."}, status=400)

    data_prevista = parse_date(data_prevista_str)
    if not data_prevista:
        return Response({"erro": "data_prevista inválida."}, status=400)

    with transaction.atomic():
        previsao = PrevisaoEmbarque.objects.create(
            data_prevista=data_prevista,
            observacao=observacao or None,
        )

        criados = 0
        for it in itens:
            pedido_id = it.get("pedido_id")
            m2 = float(it.get("m2") or 0)
            cd_romaneio = (it.get("cd_romaneio_faturamento") or "").strip()

            if not pedido_id or m2 <= 0:
                raise ValidationError("pedido_id é obrigatório e m2 deve ser maior que zero.")

            pedido = Pedido.objects.get(pk=pedido_id)

            PrevisaoItemEmbarque.objects.create(
                previsao=previsao,
                pedido=pedido,
                metragem_prevista_m2=m2,
                cd_romaneio_faturamento=cd_romaneio or None,
            )
            criados += 1

    return Response({
        "mensagem": "Previsão salva com sucesso.", 
        "previsao_id": previsao.id, 
        "itens_criados": criados
    }, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_converter_previsao_para_embarque(request):
    """
    Converte uma PrevisaoEmbarque num Embarque real, injetando os Itens de Embarque.
    """
    previsao_id = request.data.get("previsao_id")
    veiculo_id = request.data.get("veiculo_id")
    tipo_veiculo_id = request.data.get("tipo_veiculo_id")
    data_embarque_str = request.data.get("data_embarque")

    if not previsao_id or not data_embarque_str:
        return Response({"erro": "previsao_id e data_embarque são obrigatórios."}, status=400)

    data_embarque = parse_date(data_embarque_str)
    if not data_embarque:
        return Response({"erro": "data_embarque inválida."}, status=400)

    try:
        previsao = PrevisaoEmbarque.objects.prefetch_related("itens__pedido").get(pk=previsao_id)
    except PrevisaoEmbarque.DoesNotExist:
        return Response({"erro": "Previsão não encontrada."}, status=404)

    if previsao.convertido:
        return Response({"erro": "Esta previsão já foi convertida num embarque."}, status=400)

    with transaction.atomic():
        try:
            veiculo = _resolver_veiculo_obrigatorio(veiculo_id, tipo_veiculo_id)
        except Exception as e:
            return Response({"erro": str(e)}, status=400)

        embarque = Embarque.objects.create(
            veiculo=veiculo,
            data_embarque=data_embarque,
            finalizado=False,
        )

        criados = 0
        for prev_item in previsao.itens.all():
            pedido = prev_item.pedido
            m2 = float(prev_item.metragem_prevista_m2 or 0)

            saldo_permitido = float(pedido.saldo_a_entregar or 0) * 1.5
            if m2 > saldo_permitido + 1e-9:
                raise ValidationError(f"Previsão do pedido {pedido.nr_contract}: m² excede saldo +50%.")

            ItemEmbarque.objects.create(
                embarque=embarque,
                pedido=pedido,
                metragem_embarcada=m2,
                cd_romaneio_faturamento=(prev_item.cd_romaneio_faturamento or f"PREV-{previsao.id}"),
                nr_pallet=f"PREV-{previsao.id}-{prev_item.id}",
                pallet=f"PREV-{previsao.id}-{prev_item.id}",
                pos_x=0, pos_y=0, pos_z=0, largura=1.2, comprimento=1.0, altura=1.0, rotacionado=False
            )
            criados += 1

        previsao.convertido = True
        previsao.save(update_fields=["convertido"])

    return Response({
        "mensagem": "Previsão convertida num embarque real.", 
        "embarque_id": embarque.id, 
        "itens_criados": criados
    }, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_pedidos_internos(request):
    """Devolve a lista de Pedidos Internos formatada para o React com a lógica de Prazos"""
    agora = timezone.now()
    
    # Filtra os pedidos exatamente como a sua view antiga fazia
    pedidos = Pedido.objects.filter(
        dt_programada__isnull=False
    ).filter(
        Q(fechado=False) | Q(fechado__isnull=True)
    ).order_by('dt_programada', 'cliente', 'unidade_medida')
    
    dados = []
    meses_pt = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 
                7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
    
    for p in pedidos:
        # 1. RECRIAR A LÓGICA DE PRAZOS ORIGINAL
        artigo_nome = (p.artigo or "").lower()
        dias_antecedencia = 20 if "nobuck" in artigo_nome else 11
        
        previsao_inicio = p.dt_programada - timedelta(days=dias_antecedencia)
        prazo = p.dt_programada
        delta = prazo - agora
        
        if delta.total_seconds() < 0:
            atraso = abs(delta)
            if atraso.days >= 1:
                status_texto = f"Atrasado há {atraso.days} dia(s)"
            else:
                horas = int(atraso.total_seconds() // 3600)
                status_texto = f"Atrasado há {horas} hora(s)"
            status_classe = "atrasado"
        elif prazo.date() == agora.date():
            status_texto = "Vence hoje"
            status_classe = "hoje"
        else:
            dias_restantes = delta.days
            status_texto = f"Faltam {dias_restantes} dia(s)"
            status_classe = "adiantado"

        # 2. FORMATAR MÊS
        mes_display = f"{meses_pt.get(p.dt_programada.month, '')} - {p.dt_programada.year}"

        # 3. EMPACOTAR OS DADOS
        dados.append({
            "id": p.pk,
            "nr_contract": p.nr_contract or "",
            "nr_pedido_cliente": p.nr_pedido_cliente or "",
            "cliente": p.cliente or "",
            "artigo": p.artigo or "",
            "selecao": p.selecao or "",
            "quantidade": float(p.quantidade or 0),
            "quantidade_entregue": float(p.quantidade_entregue or 0),
            "unidade_medida": p.unidade_medida or "N/D",
            "dt_embarque": p.dt_embarque.isoformat() if p.dt_embarque else None,
            "dt_programada": p.dt_programada.isoformat() if p.dt_programada else None,
            "obs": p.obs or "",
            "status_prazo_texto": status_texto,
            "status_prazo_classe": status_classe,
            "mes_display": mes_display,
            "previsao_inicio": previsao_inicio.isoformat() if previsao_inicio else None
        })
        
    return Response(dados)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_pedidos_dashboard_producao(request):
    """
    Retorna os pedidos em aberto que já possuem requisições vinculadas,
    separando o WIP em Processando e Fila, e identificando o gargalo atual do pedido.
    """
    pedidos = Pedido.objects.filter(
        Q(fechado=False) | Q(fechado__isnull=True),
        requisicao_links__isnull=False
    ).distinct().prefetch_related('requisicao_links__requisicao', 'requisicao_links__requisicao__fluxos__processo')

    dados = []
    
    for p in pedidos:
        m2_processando = 0.0
        m2_em_fila = 0.0
        m2_concluido = 0.0
        
        volume_por_setor = {}
        
        for link in p.requisicao_links.all():
            req = link.requisicao
            vol = float(req.qt_mt or req.m2 or 0)
            
            if req.encerrado:
                m2_concluido += float(req.m2 or req.qt_mt or 0)
            else:
                fluxos = list(req.fluxos.all())
                fluxo_ativo = next((f for f in fluxos if not f.encerrado), None)
                
                if fluxo_ativo:
                    m2_processando += vol
                    proc_nome = fluxo_ativo.processo.nome if fluxo_ativo.processo else "Desconhecido"
                else:
                    m2_em_fila += vol
                    # Assume que a fila está no último setor processado aguardando o próximo
                    ultimo_fluxo = max((f for f in fluxos if f.dt_saida), key=lambda x: x.dt_saida, default=None)
                    proc_nome = ultimo_fluxo.processo.nome if (ultimo_fluxo and ultimo_fluxo.processo) else "Aguardando Início"
                
                volume_por_setor[proc_nome] = volume_por_setor.get(proc_nome, 0) + vol

        # Identificar o setor com maior acúmulo como sendo o "Gargalo atual" deste pedido
        gargalo_nome = "N/D"
        if volume_por_setor:
            gargalo_nome = max(volume_por_setor, key=volume_por_setor.get)
            
        m2_em_producao = m2_processando + m2_em_fila
        
        if m2_em_producao > 0 or m2_concluido > 0:
            dados.append({
                "id": p.pk,
                "cd_pedido": p.cd_pedido,
                "nr_contract": p.nr_contract or "",
                "cliente": p.cliente or "",
                "artigo": p.artigo or "",
                "dt_programada": p.dt_programada.isoformat() if p.dt_programada else None,
                "quantidade_pedida": float(p.quantidade or 0),
                "m2_em_producao": m2_em_producao, # Total WIP (processando + fila)
                "m2_processando": m2_processando,
                "m2_em_fila": m2_em_fila,
                "m2_concluido": m2_concluido,
                "setor_gargalo": gargalo_nome,
                # Pode futuramente ser puxado de uma config. Usando um fallback padrao de 80.
                "capacidade_gargalo_m2h": 80 
            })
            
    dados.sort(key=lambda x: x["m2_em_producao"], reverse=True)
    return Response(dados)