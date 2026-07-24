from rest_framework import viewsets
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import is_aware, make_naive
from django.db.models import Prefetch
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.utils import timezone
from .models import Processo, Requisicao, FluxoRequisicao, Operador, RoteiroArtigo, Justificativa, RequisicaoJustificativa
from .serializers import PedidoSerializer, ProcessoSerializer, RequisicaoSerializer, FluxoRequisicaoSerializer, OperadorSerializer, JustificativaSerializer
from src.apps.pedido.models import Pedido
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required

from .select_custo_formula import custo_requisicao
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import pymssql


# pyrefly: ignore [missing-import]
from django.db.models import Q

# A view legado de impressão (agora liberada para abrir em nova aba pelo React)
def imprimir_rendimento_view(request):
    from datetime import datetime, date

    ids_str = request.GET.get("ids", "")
    tipo = request.GET.get("tipo", "padrao")
    ids = [int(i) for i in ids_str.split(",") if i.isdigit()]
    objetos = Requisicao.objects.filter(id__in=ids)

    # 🚀 Processa os custos e o rendimento automaticamente antes de gerar o relatório
    if tipo in ["rendimento", "custo"]:
        cd_requisicoes = [str(req.cd_requisicao) for req in objetos]
        if cd_requisicoes:
            custo_requisicao(cd_requisicoes)
            # Recarrega os objetos do banco pois o script atualizou os custos e os M2 finais!
            objetos = Requisicao.objects.filter(id__in=ids)

    # 🌟 FUNÇÃO NOVA: Agora calcula em segundos para podermos somar no final
    def calcular_segundos(dt_inicio, dt_fim):
        if not dt_inicio:
            return 0
        inicio = dt_inicio if isinstance(dt_inicio, datetime) else datetime.combine(dt_inicio, datetime.min.time())
        fim = dt_fim if dt_fim and isinstance(dt_fim, datetime) else (datetime.combine(dt_fim, datetime.min.time()) if dt_fim else datetime.now())
        
        delta = fim - inicio
        return delta.total_seconds() if delta.total_seconds() > 0 else 0

    def formatar_tempo(segundos):
        if segundos == 0:
            return "0.0 horas"
        horas = segundos / 3600
        if horas >= 24:
            dias = int(horas // 24)
            horas_restantes = horas % 24
            return f"{dias}d e {horas_restantes:.1f}h"
        return f"{horas:.1f} horas"

    for req in objetos:
        fluxos = list(req.get_fluxos_ordenados())
        fluxos_processados = []
        processos_ativos_dict = {}
        total_segundos_req = 0 

        for fluxo in fluxos:
            
            # 🌟 NOVA LÓGICA DE TEMPO: Direta, sem tentar adivinhar linhas!
            if fluxo.encerrado:
                # Se já saiu do setor, o tempo final é exatamente o carimbo da saída
                # (Usamos o fluxo.dt_processo como fallback apenas para leituras velhas que não tenham dt_saida)
                data_fim = fluxo.dt_saida if fluxo.dt_saida else fluxo.dt_processo
            else:
                # Se ainda está na máquina, o tempo conta até agora
                data_fim = datetime.now()

            # Calcula e formata
            segundos_setor = calcular_segundos(fluxo.dt_processo, data_fim)
            fluxo.tempo_processo = formatar_tempo(segundos_setor)
            
            total_segundos_req += segundos_setor
            fluxos_processados.append(fluxo)

            # (O Agrupamento para as Caixas Superiores Azuis continua intocável e a funcionar)
            if not fluxo.encerrado and fluxo.processo:
                pid = fluxo.processo.id
                if pid not in processos_ativos_dict:
                    processos_ativos_dict[pid] = {
                        'nome': fluxo.processo.nome,
                        'dt_processo': fluxo.dt_processo,
                        'tempo_no_processo': formatar_tempo(calcular_segundos(fluxo.dt_processo, datetime.now())),
                        'quantidade': 0
                    }
                processos_ativos_dict[pid]['quantidade'] += (fluxo.quantidade or 0)
        
        # 🌟 CÁLCULOS DINÂMICOS PARA O TEMPLATE
        # 1. Somatórias de Refilo / Percas
        soma_kg = sum(refilo.qt_refila or 0 for refilo in req.refilos.all())
        kg_blue_val = req.kg_blue if req.kg_blue else 1
        soma_m2 = float(soma_kg) / float(kg_blue_val) if float(kg_blue_val) > 0 else 0
        req_m2_val = req.m2 if req.m2 else 1
        soma_perc = (soma_m2 / req_m2_val) * 100 if req_m2_val > 0 else 0
        
        # Cálculo da Quebra Global (% Dif) = 100 - (Saída / Entrada * 100)
        entrada_m2 = float(req.qt_mt or 0)
        saida_m2 = float(req.m2 or 0)
        
        if entrada_m2 > 0 and saida_m2 > 0:
            # Se a saída for menor que a entrada (perda), a quebra será negativa
            req.quebra_global_perc = round(((saida_m2 / entrada_m2) - 1) * 100, 2)
        else:
            req.quebra_global_perc = 0
        
        req.tota_perca_kg = soma_kg
        req.tota_perca_m2 = round(soma_m2, 2)
        req.tota_perca_perc = round(soma_perc, 2)

        # 2. Custo Financeiro (Usando 42.00 fixo ou custo_requisicao se tiver)
        valor_m2 = req.custo_requisicao_inicial if req.custo_requisicao_inicial else 42.00
        req.financeiro_vl_m2 = valor_m2
        req.financeiro_total = round(soma_m2 * float(valor_m2), 2)

        # 3. Quebra de Processos (Aprovados / Reprovados)
        processos_nomes = ["BLUE", "SECAGEM", "LIXADEIRA", "QUALIDADE", "MOLISSA"]
        quebra = []
        
        for p_nome in processos_nomes:
            # Tenta encontrar se houve refilo (perca) neste processo específico
            refilo_processo = next((r for r in req.refilos.all() if r.processo and p_nome.upper() in r.processo.nome.upper()), None)
            
            p_kg = refilo_processo.qt_refila if refilo_processo and refilo_processo.qt_refila else 0
            p_reprovado_m2 = float(p_kg) / float(kg_blue_val) if float(kg_blue_val) > 0 else 0
            p_aprovado_m2 = req_m2_val - p_reprovado_m2
            
            p_reprovado_perc = (p_reprovado_m2 / req_m2_val) * 100 if req_m2_val > 0 else 0
            p_aprovado_perc = (p_aprovado_m2 / req_m2_val) * 100 if req_m2_val > 0 else 0

            quebra.append({
                "nome": p_nome,
                "total_lote": req_m2_val,
                "aprovado_m2": round(p_aprovado_m2, 2),
                "aprovado_perc": round(p_aprovado_perc, 2),
                "reprovado_m2": round(p_reprovado_m2, 2),
                "reprovado_perc": round(p_reprovado_perc, 2),
            })
        req.quebra_processos = quebra

    if tipo == "rendimento":
        template_name = "rendimento/impressao.html"
    elif tipo == "fluxograma":
        template_name = "fluxograma/impressao.html"
    elif tipo == "custo":
        cd_requisicao = request.GET.get("cd_requisicao")
        if cd_requisicao:
            custo_requisicao([cd_requisicao])  # mantém compatível com sua função
        template_name = "custo/impressao.html"
        template_name = "custo/impressao.html"
    elif tipo == "fluxo_detalhado":
        template_name = "fluxograma/fluxo_detalhado.html"

    return render(request, template_name, {"objetos": objetos, "today": date.today()})


# SUA CLASSE DE CONEXÃO SQL
class OrdemServicoSQL:
    def conexao(self):
        try:
            con = pymssql.connect(
                host='192.168.20.250',
                port='1433',
                user='sa',
                password='CR@R2018c', 
                database='Marca_Evolution'
            )
            return con
        except pymssql.Error as e:
            print(f"Erro de conexão com o banco de dados: {e}")
            raise

    def buscar_ordens(self, marca_couro):
        con = self.conexao()
        cursor = con.cursor(as_dict=True)
        query = """
            SELECT
                Ordem_Servico.Nr_OS,
                Ordem_Servico.Marca_no_Couro AS Marca_Couro,
                Ordem_Servico.Quantidade_WB AS Pecas_WB,
                Ordem_Servico.Pes2_M2_WB AS Metro2_WB,
                Ordem_Servico.Observacao_Producao AS Cd_Observacao
            FROM Pedido_Comercial_Artigo_Programacao AS Ordem_Servico
            WHERE Ordem_Servico.Marca_no_Couro = %s
            ORDER BY Ordem_Servico.Codigo DESC
        """
        cursor.execute(query, (marca_couro,))
        results = cursor.fetchall()
        cursor.close()
        con.close()
        return results


# -------------------------------------------------------------------
# VIEW PARA IMPRESSÃO DE RELATÓRIO DE MÁQUINA
# -------------------------------------------------------------------
def imprimir_maquina_view(request):
    from datetime import datetime, date, timedelta
    from src.apps.fluxo.models import Processo, Requisicao, FluxoRequisicao
    from django.db.models import Sum
    import json

    processo_id = request.GET.get("processo_id")
    data_inicio_str = request.GET.get("data_inicio")
    data_fim_str = request.GET.get("data_fim")

    if not processo_id:
        return render(request, "maquinas/impressao.html", {"erro": "Processo não informado"})

    try:
        processo = Processo.objects.get(id=processo_id)
    except Processo.DoesNotExist:
        return render(request, "maquinas/impressao.html", {"erro": "Máquina não encontrada"})

    # Hoje e início do turno (ex: 06:00) - Fallback para comportamento atual se não houver filtro
    hoje = date.today()
    agora = datetime.now()
    inicio_dia = datetime.combine(hoje, datetime.min.time())
    inicio_turno = inicio_dia + timedelta(hours=6) if agora.hour >= 6 else inicio_dia - timedelta(hours=18)

    # Processamento de Datas do Filtro (Para os Gráficos)
    tem_filtro = False
    if data_inicio_str and data_fim_str:
        try:
            dt_ini = datetime.strptime(data_inicio_str, "%Y-%m-%d")
            dt_fim = datetime.strptime(data_fim_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            tem_filtro = True
        except ValueError:
            pass
            
    if not tem_filtro:
        dt_ini = inicio_dia
        dt_fim = datetime.combine(hoje, datetime.max.time())

    # 1. Obter TODOS os fluxos para manter o relatório original INTACTO
    fluxos_maquina = FluxoRequisicao.objects.filter(processo=processo).select_related('requisicao')

    # Métricas Originais
    wip_lotes = []
    produzido_hoje_m2 = 0
    produzido_hoje_pcs = 0
    produzido_turno_m2 = 0
    produzido_turno_pcs = 0
    tempo_total_segundos = 0
    lotes_finalizados_count = 0
    
    # Dados EXCLUSIVOS para o Relatório Detalhado (Tabelas)
    historico_lotes = []
    resumo_artigos_dict = {}

    for f in fluxos_maquina:
        req = f.requisicao
        is_encerrado = f.encerrado
        
        req_m2 = float(req.m2 or req.qt_mt or 0) if req.encerrado else float(req.qt_mt or req.m2 or 0)
        req_pcs = int(req.qt or req.quantidade or 0) if req.encerrado else int(req.quantidade or req.qt or 0)
        
        pcs_fluxo = int(f.quantidade or 0) if f.quantidade else req_pcs
        metros_fluxo = (req_m2 / req_pcs * pcs_fluxo) if req_pcs > 0 else req_m2

        # 1.1 WIP (Em Processo) - MANTIDO 100% COMO ORIGINAL
        if not is_encerrado:
            delta_espera = agora - (f.dt_processo.replace(tzinfo=None) if f.dt_processo else agora)
            horas_espera = delta_espera.total_seconds() / 3600
            
            wip_lotes.append({
                "cd_requisicao": req.cd_requisicao,
                "lote": req.lote,
                "artigo": req.artigo,
                "quantidade": pcs_fluxo,
                "m2": round(metros_fluxo, 2),
                "tempo_espera": f"{horas_espera:.1f}h"
            })
            continue

        # 1.2 Finalizados - MANTIDO 100% COMO ORIGINAL
        dt_saida = f.dt_saida.replace(tzinfo=None) if f.dt_saida else (f.dt_processo.replace(tzinfo=None) if f.dt_processo else None)
        if dt_saida and is_encerrado:
            lotes_finalizados_count += 1
            dt_entrada = f.dt_processo.replace(tzinfo=None) if f.dt_processo else dt_saida
            
            # Duração exata do lote
            duracao_lote_segundos = max(0, (dt_saida - dt_entrada).total_seconds())
            tempo_total_segundos += duracao_lote_segundos
            
            if dt_saida.date() == hoje:
                produzido_hoje_m2 += metros_fluxo
                produzido_hoje_pcs += pcs_fluxo
                
            if dt_saida >= inicio_turno:
                produzido_turno_m2 += metros_fluxo
                produzido_turno_pcs += pcs_fluxo
                
            # HISTÓRICO DETALHADO (APENAS SE ESTIVER NO PERÍODO)
            if dt_ini <= dt_saida <= dt_fim:
                art = req.artigo or "S/ Artigo"
                
                # Tabela de Histórico
                historico_lotes.append({
                    "cd_requisicao": req.cd_requisicao,
                    "lote": req.lote,
                    "artigo": art,
                    "quantidade": pcs_fluxo,
                    "m2": round(metros_fluxo, 2),
                    "entrada": dt_entrada.strftime("%d/%m %H:%M"),
                    "saida": dt_saida.strftime("%d/%m %H:%M"),
                    "duracao_min": round(duracao_lote_segundos / 60, 1)
                })
                
                # Agregação por Artigo
                if art not in resumo_artigos_dict:
                    resumo_artigos_dict[art] = {"lotes": 0, "pcs": 0, "m2": 0.0}
                resumo_artigos_dict[art]["lotes"] += 1
                resumo_artigos_dict[art]["pcs"] += pcs_fluxo
                resumo_artigos_dict[art]["m2"] += metros_fluxo

    import statistics

    # Prepara Resumo por Artigos (Calcula % e Ordena por m2)
    total_m2_historico = sum(a["m2"] for a in resumo_artigos_dict.values())
    total_pcs_historico = sum(a["pcs"] for a in resumo_artigos_dict.values())
    total_minutos_historico = sum(a["duracao_min"] for a in historico_lotes)
    total_lotes_historico = len(historico_lotes)
    
    resumo_artigos = []
    for art, dados in resumo_artigos_dict.items():
        pct = (dados["m2"] / total_m2_historico * 100) if total_m2_historico > 0 else 0
        resumo_artigos.append({
            "artigo": art,
            "lotes": dados["lotes"],
            "pcs": dados["pcs"],
            "m2": round(dados["m2"], 2),
            "pct_m2": round(pct, 1)
        })
    resumo_artigos.sort(key=lambda x: x["m2"], reverse=True)
    
    # Cálculos Avançados (Ranking e Estatísticas)
    maior_lote_m2 = None
    menor_lote_m2 = None
    top_5_maiores_tempos = []
    estatisticas = None
    
    if historico_lotes:
        # Ranking de M2
        sorted_by_m2 = sorted(historico_lotes, key=lambda x: x["m2"])
        menor_lote_m2 = sorted_by_m2[0]
        maior_lote_m2 = sorted_by_m2[-1]
        
        # Top 5 maiores tempos
        sorted_by_time = sorted(historico_lotes, key=lambda x: x["duracao_min"], reverse=True)
        top_5_maiores_tempos = sorted_by_time[:5]
        
        # Estatísticas (Mediana, Desvio, Maior, Menor)
        duracoes = [l["duracao_min"] for l in historico_lotes if l["duracao_min"] > 0]
        if duracoes:
            estatisticas = {
                "maior": max(duracoes),
                "menor": min(duracoes),
                "mediana": round(statistics.median(duracoes), 1),
                "desvio": round(statistics.stdev(duracoes), 1) if len(duracoes) > 1 else 0.0
            }

    # Ordenar o histórico cronologicamente (mais recente no topo)
    historico_lotes.sort(key=lambda x: x["saida"], reverse=True)

    # 2. Cálculos Finais (KPIs)
    velocidade_media = 0
    tempo_medio_lote_min = 0
    horas_totais = tempo_total_segundos / 3600

    if lotes_finalizados_count > 0:
        tempo_medio_lote_min = (tempo_total_segundos / lotes_finalizados_count) / 60
        if horas_totais > 0:
            velocidade_media = produzido_hoje_m2 / horas_totais 

    context = {
        "processo": processo,
        "hoje": hoje,
        "hora_impressao": agora.strftime("%H:%M:%S"),
        "tem_filtro": tem_filtro,
        "data_inicio": dt_ini.date() if tem_filtro else None,
        "data_fim": dt_fim.date() if tem_filtro else None,
        "kpis": {
            "producao_hoje_m2": round(produzido_hoje_m2, 2),
            "producao_hoje_pcs": produzido_hoje_pcs,
            "producao_turno_m2": round(produzido_turno_m2, 2),
            "producao_turno_pcs": produzido_turno_pcs,
            "wip_qtd": sum(l["quantidade"] for l in wip_lotes),
            "wip_m2": round(sum(l["m2"] for l in wip_lotes), 2),
            "tempo_medio_min": round(tempo_medio_lote_min, 1),
        },
        "wip_lotes": wip_lotes,
        "historico_lotes": historico_lotes,
        "resumo_artigos": resumo_artigos,
        "total_m2_historico": round(total_m2_historico, 2),
        "total_pcs_historico": total_pcs_historico,
        "total_lotes_historico": total_lotes_historico,
        "total_minutos_historico": round(total_minutos_historico, 1),
        "maior_lote_m2": maior_lote_m2,
        "menor_lote_m2": menor_lote_m2,
        "top_5_maiores_tempos": top_5_maiores_tempos,
        "estatisticas": estatisticas,
    }

    return render(request, "maquinas/impressao.html", context)


def extrair_marca_couro(valor):
    partes = (valor or "").split(",", 1)
    marca_couro = partes[1] if len(partes) > 1 else partes[0]
    return marca_couro.strip()

# -------------------------------------------------------------------
# VIEW PARA A BUSCA AJAX (AUTOCOMPLETE)
# -------------------------------------------------------------------
def busca_requisicao_ajax(request):
    termo_busca = request.GET.get('term', '').strip()
    
    if len(termo_busca) < 2:
        return JsonResponse([], safe=False)

    requisicoes = Requisicao.objects.filter(
        Q(cd_requisicao__icontains=termo_busca) | Q(lote__icontains=termo_busca)
    )[:10]

    resultados_json = []
    for req in requisicoes:
        resultados_json.append({
            'id': req.pk,
            'numero': req.cd_requisicao,
            'cliente': req.lote,
            'data': req.data_criacao.strftime('%d/%m/%Y') if hasattr(req, 'data_criacao') and req.data_criacao else 'N/A'
        })
        
    return JsonResponse(resultados_json, safe=False)

# -------------------------------------------------------------------
# VIEW PRINCIPAL - ORDEM DE SERVIÇO
# -------------------------------------------------------------------
def ordem_servico_page(request):
    resultado_final = []
    erro = ''

    total_pecas = Decimal(0)
    total_metro = Decimal(0)
    total_resultado = Decimal(0)

    if request.method == 'POST':
        requisicao_ids = request.POST.getlist('requisicao_id')
        quantidades_str = request.POST.getlist('quantidade')

        if not requisicao_ids:
            erro = 'Nenhum item foi adicionado para processamento.'
        
        for req_id, qtd_str in zip(requisicao_ids, quantidades_str):
            try:
                requisicao = Requisicao.objects.get(pk=req_id)
                marca_couro = extrair_marca_couro(requisicao.lote)
                if not marca_couro:
                    continue
                
                quantidade = Decimal(qtd_str.replace(',', '.'))
                if quantidade <= 0:
                    continue

                sql = OrdemServicoSQL()
                ordens = sql.buscar_ordens(marca_couro)
                
                for ordem in ordens:
                    pecas = Decimal(ordem.get('Pecas_WB') or 0)
                    metro = Decimal(ordem.get('Metro2_WB') or 0)
                    
                    media_m2_peca = (metro / pecas) if pecas > 0 else Decimal(0)
                    resultado_calc = media_m2_peca * quantidade
                    
                    ordem['Media_Metro_Peca'] = round(media_m2_peca, 2)
                    ordem['Resultado'] = round(resultado_calc, 2)
                    
                    total_pecas += pecas
                    total_metro += metro
                    total_resultado += resultado_calc

                    resultado_final.append(ordem)

            except Requisicao.DoesNotExist:
                erro += f"Requisição com ID {req_id} não encontrada. "
            except InvalidOperation:
                erro += f"Quantidade '{qtd_str}' para requisição ID {req_id} é inválida. "
            except Exception as e:
                erro += f"Erro ao processar item {req_id}: {e}. "
    
    contexto = {
        'resultado': resultado_final,
        'erro': erro.strip(),
        'totais': {
            'pecas': total_pecas,
            'metro': round(total_metro, 2),
            'resultado': round(total_resultado, 2),
        }
    }
    return render(request, 'ordens_servico.html', contexto)


class OperadorViewSet(viewsets.ModelViewSet):
    queryset = Operador.objects.all()
    serializer_class = OperadorSerializer
    permission_classes = [AllowAny]

class PedidoViewSet(viewsets.ModelViewSet):
    queryset = Pedido.objects.all()
    serializer_class = PedidoSerializer

class ProcessoViewSet(viewsets.ModelViewSet):
    queryset = Processo.objects.all()
    serializer_class = ProcessoSerializer

class RequisicaoViewSet(viewsets.ModelViewSet):
    queryset = Requisicao.objects.all()
    serializer_class = RequisicaoSerializer

class FluxoRequisicaoViewSet(viewsets.ModelViewSet):
    queryset = FluxoRequisicao.objects.all().order_by('-id')
    serializer_class = FluxoRequisicaoSerializer

class JustificativaViewSet(viewsets.ModelViewSet):
    queryset = Justificativa.objects.all().order_by('nome')
    serializer_class = JustificativaSerializer
    permission_classes = [AllowAny]


@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def ler_qrcode_movimentacao(request):
    cd_requisicao = request.data.get('cd_requisicao')
    operador_id = request.data.get('operador_id') 
    
    # ⚠️ NOVIDADE: Como o operador tem várias máquinas, o frontend precisa dizer qual ele está a usar
    processo_id = request.data.get('processo_id') 
    
    qtd_recebida = int(request.data.get('quantidade', 0))
    motivo_diferenca = request.data.get('motivo_diferenca', 'AINDA_EM_PROCESSO')
    justificativa_id = request.data.get('justificativa_id')

    if not cd_requisicao or not operador_id or not processo_id or qtd_recebida <= 0:
        return Response({'sucesso': False, 'erro': 'Dados incompletos ou quantidade inválida.'}, status=400)

    try:
        requisicao = Requisicao.objects.get(cd_requisicao=cd_requisicao)
        operador = Operador.objects.get(id=operador_id)
        processo_atual = Processo.objects.get(id=processo_id)
    except Requisicao.DoesNotExist:
        return Response({'sucesso': False, 'erro': 'Requisição não encontrada.'}, status=404)
    except Operador.DoesNotExist:
        return Response({'sucesso': False, 'erro': 'Operador não encontrado.'}, status=404)
    except Processo.DoesNotExist:
        return Response({'sucesso': False, 'erro': 'Processo não encontrado.'}, status=404)

    # Valida se o operador tem o processo no seu perfil
    if not operador.processos.filter(id=processo_atual.id).exists():
        return Response({'sucesso': False, 'erro': f'O operador não tem permissão para atuar no setor: {processo_atual.nome}.'}, status=403)

    agora = timezone.now()

    forcar_ajuste = request.data.get('forcar_ajuste', False)

    # --------------------------------------------------------------------------------
    # 1. RASTREABILIDADE LIVRE E AJUSTE DE CONTAGEM
    # --------------------------------------------------------------------------------
    # Evita que o processo consuma as próprias peças (consumo recursivo)
    fluxos_para_consumir = list(requisicao.fluxos.filter(encerrado=False).exclude(processo_id=processo_id).order_by('dt_processo', 'id'))
    tem_outro_processo = requisicao.fluxos.exclude(processo_id=processo_id).exists()

    if not tem_outro_processo:
        # É o primeiro processo! A quantidade base é a da requisição, menos o que já entrou aqui.
        total_requisicao = float(requisicao.quantidade or requisicao.qt or 0)
        qtd_ja_entrou = sum((f.quantidade or 0) for f in requisicao.fluxos.filter(processo_id=processo_id))
        saldo_disponivel = total_requisicao - qtd_ja_entrou
        
        if qtd_recebida > saldo_disponivel + 12 and not forcar_ajuste:
            diferenca = qtd_recebida - saldo_disponivel
            return Response({
                'sucesso': False, 
                'precisa_confirmacao': True, 
                'diferenca': diferenca,
                'qtd_anterior': saldo_disponivel,
                'total_requisicao': total_requisicao,
                'erro': f'A quantidade recebida excede o saldo da requisição em {int(diferenca)} peças.'
            }, status=400)
            
        # Não há fluxos anteriores para consumir, pois é o início da cadeia
        fluxos_para_consumir = []
        total_disponivel = saldo_disponivel
    else:
        total_disponivel = sum(f.quantidade for f in fluxos_para_consumir if f.quantidade)
        
        if total_disponivel == 0:
            # Se não há peças abertas nos processos anteriores, significa que já foi tudo puxado
            ultimo_fluxo = requisicao.fluxos.exclude(processo_id=processo_id).order_by('-dt_saida', '-id').first()
            processo_anterior = ultimo_fluxo.processo.nome if ultimo_fluxo and ultimo_fluxo.processo else "Desconhecido"
            
            if qtd_recebida > 12 and not forcar_ajuste:
                qtd_ant = sum((f.quantidade or 0) for f in requisicao.fluxos.filter(processo_id=ultimo_fluxo.processo_id)) if ultimo_fluxo else 0
                return Response({
                    'sucesso': False, 
                    'precisa_confirmacao': True, 
                    'diferenca': qtd_recebida,
                    'qtd_anterior': qtd_ant,
                    'total_requisicao': float(requisicao.quantidade or requisicao.qt or 0),
                    'erro': f'A quantidade recebida excede o limite permitido (todas as peças já foram consumidas de {processo_anterior}).'
                }, status=400)
            
            nova_obs = f"[{agora.strftime('%d/%m/%Y %H:%M')}] Ajuste automático de contagem (+{qtd_recebida} peças) no processo {processo_anterior}."
            requisicao.obs = f"{requisicao.obs}\n{nova_obs}" if requisicao.obs else nova_obs
            requisicao.save()

            if ultimo_fluxo:
                novo_fluxo = FluxoRequisicao.objects.create(
                    requisicao=requisicao,
                    processo=ultimo_fluxo.processo,
                    quantidade=qtd_recebida,
                    dt_processo=agora,
                    encerrado=False
                )
                fluxos_para_consumir = [novo_fluxo]
                total_disponivel = qtd_recebida
            else:
                return Response({'sucesso': False, 'erro': 'Não há processo anterior para compensar a diferença.'}, status=400)

        # Se o operador tentar puxar mais peças do que o lote total disponível
        elif qtd_recebida > total_disponivel:
            diferenca = qtd_recebida - total_disponivel
            if diferenca > 12 and not forcar_ajuste:
                # Soma a quantidade já registrada no processo anterior dos fluxos em aberto
                ultimo_proc_id = fluxos_para_consumir[-1].processo_id if fluxos_para_consumir else None
                qtd_ant = sum((f.quantidade or 0) for f in requisicao.fluxos.filter(processo_id=ultimo_proc_id)) if ultimo_proc_id else total_disponivel
                return Response({
                    'sucesso': False, 
                    'precisa_confirmacao': True, 
                    'diferenca': diferenca,
                    'qtd_anterior': qtd_ant,
                    'total_requisicao': float(requisicao.quantidade or requisicao.qt or 0),
                    'erro': f'A quantidade recebida excede o limite permitido (diferença de +{diferenca} peças em relação ao disponível).'
                }, status=400)
                
            ultimo_fluxo_aberto = fluxos_para_consumir[-1]
            ultimo_fluxo_aberto.quantidade += diferenca
            ultimo_fluxo_aberto.save()
            total_disponivel += diferenca

            resumo_atrasados = {}
            for f in fluxos_para_consumir:
                nome_proc = f.processo.nome if f.processo else "Desconhecido"
                resumo_atrasados[nome_proc] = resumo_atrasados.get(nome_proc, 0) + (f.quantidade or 0)
            
            texto_atrasados = " e ".join([proc for proc, qtd in resumo_atrasados.items() if qtd > 0])
            
            nova_obs = f"[{agora.strftime('%d/%m/%Y %H:%M')}] Ajuste automático de contagem (+{diferenca} peças) no processo {texto_atrasados}."
            requisicao.obs = f"{requisicao.obs}\n{nova_obs}" if requisicao.obs else nova_obs
            requisicao.save()

    qtd_a_consumir = qtd_recebida

    # --------------------------------------------------------------------------------
    # 2. CONSUMO INTELIGENTE E DIVISÃO DE LOTE (MANTIDO E FUNCIONA EM QUALQUER ROTA)
    # --------------------------------------------------------------------------------
    for fluxo in fluxos_para_consumir:
        if qtd_a_consumir <= 0:
            break
            
        if qtd_a_consumir >= fluxo.quantidade:
            # Consome a linha inteira de forma limpa
            qtd_a_consumir -= fluxo.quantidade
            fluxo.encerrado = True
            fluxo.dt_saida = agora
            fluxo.save()
        else:
            # A linha tem mais peças do que precisamos, então divide o lote
            qtd_que_ficou = fluxo.quantidade - qtd_a_consumir
            
            fluxo.quantidade = qtd_a_consumir
            fluxo.encerrado = True
            fluxo.dt_saida = agora
            fluxo.save()
            
            if motivo_diferenca == 'PERDA':
                proc_perda, _ = Processo.objects.get_or_create(nome="⚠️ PERDA / REFUGO")
                FluxoRequisicao.objects.create(requisicao=requisicao, processo=proc_perda, quantidade=qtd_que_ficou, dt_processo=agora, dt_saida=agora, encerrado=True)
            elif motivo_diferenca == 'ERRO_CONTAGEM':
                # Removemos as peças a mais para a conta fechar, não criando fluxo residual
                nova_obs = f"[{agora.strftime('%d/%m/%Y %H:%M')}] Erro de contagem (-{qtd_que_ficou} peças) regularizado. Excesso removido."
                requisicao.obs = f"{requisicao.obs}\n{nova_obs}" if requisicao.obs else nova_obs
                requisicao.save()
            elif motivo_diferenca == 'REPROCESSO':
                proc_rep, _ = Processo.objects.get_or_create(nome="♻️ AGUARDANDO REPROCESSO")
                FluxoRequisicao.objects.create(requisicao=requisicao, processo=proc_rep, quantidade=qtd_que_ficou, dt_processo=agora, encerrado=False)
            elif motivo_diferenca == 'NOVO_LOTE':
                proc_nl, _ = Processo.objects.get_or_create(nome="🔄 SEPARADO P/ NOVO LOTE")
                FluxoRequisicao.objects.create(requisicao=requisicao, processo=proc_nl, quantidade=qtd_que_ficou, dt_processo=agora, encerrado=False)
            else:
                # Mantém os couros atrasados seguros na máquina anterior onde já estavam
                FluxoRequisicao.objects.create(
                    requisicao=requisicao,
                    processo=fluxo.processo,
                    quantidade=qtd_que_ficou,
                    dt_processo=fluxo.dt_processo, 
                    encerrado=False
                )
            
            qtd_a_consumir = 0
            break

    # --------------------------------------------------------------------------------
    # 3. CRIA A NOVA ENTRADA NO SETOR ATUAL
    # --------------------------------------------------------------------------------
    FluxoRequisicao.objects.create(
        requisicao=requisicao,
        processo=processo_atual,
        quantidade=qtd_recebida,
        dt_processo=agora,
        encerrado=False
    )
    
    # --------------------------------------------------------------------------------
    # 4. REGISTRO DINÂMICO DE JUSTIFICATIVA DA MEDIDORA
    # --------------------------------------------------------------------------------
    if justificativa_id:
        try:
            justif = Justificativa.objects.get(id=justificativa_id)
            req_justif, created = RequisicaoJustificativa.objects.get_or_create(
                requisicao=requisicao,
                justificativa=justif,
                defaults={'quantidade': 0}
            )
            req_justif.quantidade += qtd_recebida
            req_justif.save()
        except Justificativa.DoesNotExist:
            pass

    return Response({
        'sucesso': True,
        'mensagem': f'✅ Entrada de {qtd_recebida} peças registada com sucesso no setor de {processo_atual.nome}!'
    })


@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def ajustar_processo_anterior(request):
    """
    Endpoint para supervisor ajustar a quantidade no processo anterior,
    quando um operador tenta inserir uma quantidade maior que o permitido.
    """
    cd_requisicao = request.data.get('cd_requisicao')
    processo_id = request.data.get('processo_id')
    nova_qtd_anterior = int(request.data.get('nova_qtd_anterior', 0))
    
    # Credenciais do supervisor
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not cd_requisicao or not processo_id or not username or not password or nova_qtd_anterior <= 0:
        return Response({'sucesso': False, 'erro': 'Dados incompletos.'}, status=400)
        
    # 1. Autenticação do Supervisor
    from django.contrib.auth import authenticate
    user = authenticate(username=username, password=password)
    if user is None:
        return Response({'sucesso': False, 'erro': 'Credenciais inválidas.'}, status=401)
        
    if not (user.is_staff or user.is_superuser):
        return Response({'sucesso': False, 'erro': 'Utilizador não tem permissão de supervisor.'}, status=403)
        
    try:
        requisicao = Requisicao.objects.get(cd_requisicao=cd_requisicao)
        processo_atual = Processo.objects.get(id=processo_id)
    except Exception:
        return Response({'sucesso': False, 'erro': 'Requisição ou Processo não encontrados.'}, status=404)
        
    # 2. Localiza o fluxo anterior
    is_primeiro_processo = not requisicao.fluxos.exists()
    if is_primeiro_processo:
        # Se é o primeiro processo, o ajuste na verdade é no total do lote (Requisicao)
        requisicao.quantidade = nova_qtd_anterior
        
        agora = timezone.now()
        nova_obs = f"[{agora.strftime('%d/%m/%Y %H:%M')}] Lote total ajustado de {requisicao.quantidade} para {nova_qtd_anterior} pelo supervisor {user.username}."
        requisicao.obs = f"{requisicao.obs}\n{nova_obs}" if requisicao.obs else nova_obs
        requisicao.save()
        
        return Response({'sucesso': True, 'mensagem': 'Ajuste concluído com sucesso.'})
    
    # Se não é o primeiro processo, ajusta a quantidade dos fluxos abertos no processo anterior
    fluxos_abertos = list(requisicao.fluxos.filter(encerrado=False).order_by('dt_processo', 'id'))
    
    if not fluxos_abertos:
        # Se não há fluxos abertos, pega o último processo que encerrou e reabre/cria saldo
        ultimo_fluxo = requisicao.fluxos.order_by('-dt_saida', '-id').first()
        if not ultimo_fluxo:
            return Response({'sucesso': False, 'erro': 'Histórico vazio, não é possível ajustar.'}, status=400)
            
        processo_anterior_id = ultimo_fluxo.processo_id
    else:
        processo_anterior_id = fluxos_abertos[-1].processo_id
        
    # Soma atual desse processo
    fluxos_do_processo = requisicao.fluxos.filter(processo_id=processo_anterior_id)
    soma_atual = sum(f.quantidade for f in fluxos_do_processo if f.quantidade)
    
    diferenca = nova_qtd_anterior - soma_atual
    
    agora = timezone.now()
    if diferenca != 0:
        if fluxos_abertos:
            ultimo = fluxos_abertos[-1]
            ultimo.quantidade += diferenca
            ultimo.save()
        else:
            # Não tem fluxo aberto, cria um novo no processo anterior com o saldo adicional
            FluxoRequisicao.objects.create(
                requisicao=requisicao,
                processo_id=processo_anterior_id,
                quantidade=diferenca,
                dt_processo=agora,
                encerrado=False
            )
            
        proc_ant = Processo.objects.filter(id=processo_anterior_id).first()
        nome_proc = proc_ant.nome if proc_ant else "Desconhecido"
        
        sinal = "+" if diferenca > 0 else ""
        nova_obs = f"[{agora.strftime('%d/%m/%Y %H:%M')}] Ajuste manual ({sinal}{diferenca} peças) no processo {nome_proc} pelo supervisor {user.username}."
        requisicao.obs = f"{requisicao.obs}\n{nova_obs}" if requisicao.obs else nova_obs
        requisicao.save()
        
    return Response({'sucesso': True, 'mensagem': 'Ajuste concluído com sucesso.'})

@staff_member_required
def resumo_lotes_ativos_view(request):
    from datetime import datetime, date

    # 1. Filtrar requisições que NÃO estão encerradas e que já têm o 'Recurtimento' iniciado
    requisicoes_ativas = Requisicao.objects.filter(
        encerrado=False,
        fluxos__processo__nome__icontains='Recurtimento'
    ).distinct().prefetch_related('fluxos__processo')

    # Funções de cálculo de tempo (adaptadas da sua view existente)
    def calcular_segundos(dt_inicio, dt_fim):
        if not dt_inicio:
            return 0
        inicio = dt_inicio if isinstance(dt_inicio, datetime) else datetime.combine(dt_inicio, datetime.min.time())
        fim = dt_fim if dt_fim and isinstance(dt_fim, datetime) else (datetime.combine(dt_fim, datetime.min.time()) if dt_fim else datetime.now())
        
        # Garantir compatibilidade de fuso horário
        if is_aware(inicio): inicio = make_naive(inicio)
        if is_aware(fim): fim = make_naive(fim)
            
        delta = fim - inicio
        return delta.total_seconds() if delta.total_seconds() > 0 else 0

    def formatar_tempo(segundos):
        if segundos == 0:
            return "0.0 horas"
        horas = segundos / 3600
        if horas >= 24:
            dias = int(horas // 24)
            horas_restantes = horas % 24
            return f"{dias}d e {horas_restantes:.1f}h"
        return f"{horas:.1f} horas"

    dados_relatorio = []

    for req in requisicoes_ativas:
        # O primeiro fluxo indica o início do processo produtivo
        primeiro_fluxo = req.fluxos.order_by('dt_processo', 'id').first()
        if not primeiro_fluxo:
            continue
        
        data_inicio_total = primeiro_fluxo.dt_processo
        tempo_total_segundos = calcular_segundos(data_inicio_total, datetime.now())
        
        # Obter os fluxos onde o lote está retido atualmente (encerrado=False)
        fluxos_ativos = req.fluxos.filter(encerrado=False)
        
        locais_atuais = []
        for f in fluxos_ativos:
            if f.processo:
                locais_atuais.append({
                    'nome': f.processo.nome,
                    'quantidade': f.quantidade,
                    'tempo_no_setor': formatar_tempo(calcular_segundos(f.dt_processo, datetime.now()))
                })

        if locais_atuais: # Só adiciona ao relatório se ainda estiver ativamente nalguma máquina
            dados_relatorio.append({
                'cd_requisicao': req.cd_requisicao,
                'lote': req.lote or "N/A",
                'artigo': req.artigo or "N/A",
                'data_inicio': data_inicio_total,
                'tempo_total': formatar_tempo(tempo_total_segundos),
                'data_inicio_bruta': data_inicio_total, # Usado para ordenação
                'locais_atuais': locais_atuais
            })

    # Ordenar do mais antigo para o mais recente (os lotes que estão a demorar mais tempo ficam no topo)
    dados_relatorio.sort(key=lambda x: x['data_inicio_bruta'] if x['data_inicio_bruta'] else datetime.now())

    return render(request, "fluxograma/resumo_lotes.html", {
        "dados": dados_relatorio,
        "today": date.today()
    })

def imprimir_relatorio_geral_view(request):
    from datetime import datetime, timedelta, time
    from decimal import Decimal
    
    data_str = request.GET.get('data', '')
    data_str = request.GET.get('data', '')
    processos_str = request.GET.get('processos', '')
    
    if not data_str or not processos_str:
        return JsonResponse({'error': 'Parâmetros data e processos são obrigatórios'}, status=400)
        
    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Formato de data inválido. Use YYYY-MM-DD.'}, status=400)
        
    processos_ids = [int(x) for x in processos_str.split(',') if x.isdigit()]
    
    # 1º Turno: 07:30 - 17:50
    # 2º Turno: 17:50 - 03:00 (dia seguinte)
    t1_start = datetime.combine(data_obj, time(7, 30))
    t1_end = datetime.combine(data_obj, time(17, 50))
    t2_start = t1_end
    t2_end = datetime.combine(data_obj + timedelta(days=1), time(3, 0))
    
    fluxos = FluxoRequisicao.objects.select_related('requisicao', 'processo').filter(
        processo_id__in=processos_ids,
        dt_saida__gte=t1_start,
        dt_saida__lte=t2_end
    )
    
    # Agrupar por Processo
    processos_selecionados = Processo.objects.filter(id__in=processos_ids)
    processos_dict = {p.id: p.nome for p in processos_selecionados}
    
    acabamento_list = ['MULTIPONTO', 'PISTOLA', 'TOP', 'GRAVAR PRENSA', 'TOP FINAL', 'PRENSA HIDRAULICA', 'ESPONJAR', 'PISTOLA F. CARNAL', 'ESPONJAR FLOR', 'PISTOLA CORREÇÃO', 'PISTOLA RESINA', 'PISTOLA FLOR', 'PISTOLA CARNAL', 'CHAPA LISA', 'PISTOLA CERA', 'VACUO SECO', 'VÁCUO SECO', 'MATIZAÇÃO', 'TINGIMENTO', 'IMPREGNAÇÃO', 'ROLO LISO', 'PISTOLA R. ADESÃO', 'COBERTURA PISTOLA', 'PISTOLA F. ADESÃO', 'CORTINA', 'TUNEL DE PINTURA', 'VÁCUO', 'VACUO']
    
    def is_acabamento(nome):
        nome_upper = nome.upper()
        if "VÁCUO MOLHADO" in nome_upper or "VACUO MOLHADO" in nome_upper:
            return False
        return any(k in nome_upper for k in acabamento_list)
        
    relatorio = {
        'recurtimento': {},
        'acabamento': {}
    }
    
    for p in processos_selecionados:
        grupo = 'acabamento' if is_acabamento(p.nome) else 'recurtimento'
        relatorio[grupo][p.id] = {
            'nome': p.nome,
            'turno1': {'pecas': 0, 'mts': 0},
            'turno2': {'pecas': 0, 'mts': 0},
            'total': {'pecas': 0, 'mts': 0}
        }
        
    for f in fluxos:
        if f.processo_id not in processos_dict:
            continue
            
        grupo = 'acabamento' if is_acabamento(processos_dict[f.processo_id]) else 'recurtimento'
        stats = relatorio[grupo][f.processo_id]
        
        req = f.requisicao
        
        pecas = f.quantidade if f.quantidade else (req.quantidade if req.quantidade else 1)
        
        # Calcular mts (proporcional caso seja quantidade parcial)
        mts = 0
        if req.qt_mt and req.quantidade and req.quantidade > 0:
            mts = float(req.qt_mt) * (pecas / req.quantidade)
        elif req.qt_mt:
            mts = float(req.qt_mt)
            
        if t1_start <= f.dt_saida < t1_end:
            turno = 'turno1'
        else:
            turno = 'turno2'
            
        stats[turno]['pecas'] += pecas
        stats[turno]['mts'] += mts
        stats['total']['pecas'] += pecas
        stats['total']['mts'] += mts

    return render(request, "maquinas/relatorio_geral.html", {
        "data_relatorio": data_obj.strftime("%d/%m/%Y"),
        "dia_semana": data_obj.strftime("%A").capitalize(),
        "relatorio": relatorio
    })

def imprimir_maquina_view(request):
    from datetime import datetime, date
    from django.db.models import Sum, Count, F, Avg
    import statistics
    
    processo_id = request.GET.get('processo_id')
    if not processo_id:
        return JsonResponse({'error': 'Parâmetro processo_id obrigatório'}, status=400)
        
    processo = get_object_or_404(Processo, id=processo_id)
    
    data_inicio_str = request.GET.get('data_inicio', '')
    data_fim_str = request.GET.get('data_fim', '')
    tem_filtro = bool(data_inicio_str or data_fim_str)
    
    fluxos = FluxoRequisicao.objects.filter(processo=processo).select_related('requisicao')
    
    # wip lotes: fluxos não encerrados nesta maquina
    wip_fluxos = fluxos.filter(encerrado=False).order_by('dt_processo')
    
    # historico: fluxos encerrados (já processados)
    historico = fluxos.filter(encerrado=True)
    
    # 1º Turno (07:30 - 17:50) e 2º Turno (17:50 - 03:00)
    hoje = date.today()
    agora = datetime.now()
    
    # KPIs basicos (Produção Hoje)
    # Consideramos os encerrados hoje
    encerrados_hoje = historico.filter(dt_saida__date=hoje)
    
    if tem_filtro:
        if data_inicio_str:
            historico = historico.filter(dt_saida__gte=f"{data_inicio_str} 00:00:00")
        if data_fim_str:
            historico = historico.filter(dt_saida__lte=f"{data_fim_str} 23:59:59")
    
    def calc_m2(req, pcs):
        if not req.qt_mt: return 0.0
        if req.quantidade and req.quantidade > 0:
            return float(req.qt_mt) * (pcs / req.quantidade)
        return float(req.qt_mt)

    # Historico Lotes
    historico_lotes = []
    total_minutos_historico = 0
    total_m2_historico = 0
    total_pcs_historico = 0
    
    artigos_dict = {}
    tempos_list = []
    
    for f in historico:
        req = f.requisicao
        pcs = f.quantidade if f.quantidade else req.quantidade
        if not pcs: pcs = 1
        m2 = calc_m2(req, pcs)
        
        duracao_min = 0
        if f.dt_processo and f.dt_saida:
            duracao_min = (f.dt_saida - f.dt_processo).total_seconds() / 60.0
            
        historico_lotes.append({
            'cd_requisicao': req.cd_requisicao,
            'lote': req.lote,
            'artigo': req.artigo,
            'quantidade': pcs,
            'm2': m2,
            'entrada': f.dt_processo.strftime('%d/%m %H:%M') if f.dt_processo else '',
            'saida': f.dt_saida.strftime('%d/%m %H:%M') if f.dt_saida else '',
            'duracao_min': duracao_min
        })
        
        total_pcs_historico += pcs
        total_m2_historico += m2
        total_minutos_historico += duracao_min
        
        if duracao_min > 0:
            tempos_list.append(duracao_min)
            
        art = req.artigo or "N/A"
        if art not in artigos_dict:
            artigos_dict[art] = {'lotes': 0, 'pcs': 0, 'm2': 0}
        artigos_dict[art]['lotes'] += 1
        artigos_dict[art]['pcs'] += pcs
        artigos_dict[art]['m2'] += m2

    resumo_artigos = []
    for art, val in artigos_dict.items():
        pct = (val['m2'] / total_m2_historico * 100) if total_m2_historico > 0 else 0
        resumo_artigos.append({
            'artigo': art,
            'lotes': val['lotes'],
            'pcs': val['pcs'],
            'm2': val['m2'],
            'pct_m2': pct
        })
        
    # KPIs globais (WIP, turno, hoje)
    wip_lotes = []
    wip_qtd = 0
    wip_m2 = 0
    for f in wip_fluxos:
        req = f.requisicao
        pcs = f.quantidade if f.quantidade else (req.quantidade or 1)
        m2 = calc_m2(req, pcs)
        wip_qtd += pcs
        wip_m2 += m2
        
        espera = (agora - f.dt_processo).total_seconds() / 3600.0 if f.dt_processo else 0
        wip_lotes.append({
            'cd_requisicao': req.cd_requisicao,
            'lote': req.lote,
            'artigo': req.artigo,
            'quantidade': pcs,
            'm2': m2,
            'tempo_espera': f"{espera:.1f}h"
        })

    producao_hoje_m2 = 0
    producao_hoje_pcs = 0
    producao_turno_m2 = 0
    producao_turno_pcs = 0
    
    # Para o turno: simplificamos usando se foi na ultimas 8h ou no turno 1/2 dependendo da hora atual
    # Para nao falhar, simplificamos: turno = hoje
    for f in encerrados_hoje:
        req = f.requisicao
        pcs = f.quantidade if f.quantidade else (req.quantidade or 1)
        m2 = calc_m2(req, pcs)
        producao_hoje_pcs += pcs
        producao_hoje_m2 += m2
        # simplificação para turno
        producao_turno_pcs += pcs
        producao_turno_m2 += m2

    kpis = {
        'producao_hoje_m2': producao_hoje_m2,
        'producao_hoje_pcs': producao_hoje_pcs,
        'producao_turno_m2': producao_turno_m2,
        'producao_turno_pcs': producao_turno_pcs,
        'tempo_medio_min': (total_minutos_historico / len(historico_lotes)) if historico_lotes else 0,
        'wip_qtd': wip_qtd,
        'wip_m2': wip_m2
    }
    
    # Estatisticas
    maior_lote_m2 = max(historico_lotes, key=lambda x: x['m2']) if historico_lotes else {}
    menor_lote_m2 = min(historico_lotes, key=lambda x: x['m2']) if historico_lotes else {}
    
    estat = {}
    if tempos_list:
        estat['maior'] = max(tempos_list)
        estat['menor'] = min(tempos_list)
        estat['mediana'] = statistics.median(tempos_list)
        estat['desvio'] = statistics.stdev(tempos_list) if len(tempos_list) > 1 else 0
        
    top_5_maiores_tempos = sorted(historico_lotes, key=lambda x: x['duracao_min'], reverse=True)[:5]
    
    context = {
        "processo": processo,
        "tem_filtro": tem_filtro,
        "data_inicio": data_inicio_str,
        "data_fim": data_fim_str,
        "hoje": hoje,
        "hora_impressao": agora.strftime('%H:%M'),
        "kpis": kpis,
        "resumo_artigos": resumo_artigos,
        "historico_lotes": historico_lotes,
        "total_lotes_historico": len(historico_lotes),
        "total_pcs_historico": total_pcs_historico,
        "total_m2_historico": total_m2_historico,
        "total_minutos_historico": total_minutos_historico,
        "maior_lote_m2": maior_lote_m2,
        "menor_lote_m2": menor_lote_m2,
        "estatisticas": estat,
        "top_5_maiores_tempos": top_5_maiores_tempos,
        "wip_lotes": wip_lotes
    }
    return render(request, "maquinas/impressao.html", context)