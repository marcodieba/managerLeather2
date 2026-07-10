from rest_framework import viewsets
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import is_aware, make_naive
from django.db.models import Prefetch
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.utils import timezone
from .models import Processo, Requisicao, FluxoRequisicao, Operador, RoteiroArtigo
from .serializers import PedidoSerializer, ProcessoSerializer, RequisicaoSerializer, FluxoRequisicaoSerializer, OperadorSerializer
from src.apps.pedido.models import Pedido
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required

from .select_custo_formula import custo_requisicao
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import pymssql


from django.db.models import Q

@staff_member_required
def imprimir_rendimento_view(request):
    from datetime import datetime, date

    ids_str = request.GET.get("ids", "")
    tipo = request.GET.get("tipo", "padrao")
    ids = [int(i) for i in ids_str.split(",") if i.isdigit()]
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
        
        req.fluxos_com_tempo = fluxos_processados
        req.processos_ativos_agrupados = list(processos_ativos_dict.values())
        req.tempo_total_formatado = formatar_tempo(total_segundos_req)

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
    queryset = FluxoRequisicao.objects.all()
    serializer_class = FluxoRequisicaoSerializer


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

    # --------------------------------------------------------------------------------
    # 1. RASTREABILIDADE LIVRE (Sem Bloqueio de Roteiro Fixo)
    # O sistema procura onde estão os lotes "em aberto" para os conseguir consumir
    # --------------------------------------------------------------------------------
    fluxos_para_consumir = list(requisicao.fluxos.filter(encerrado=False).order_by('dt_processo', 'id'))
    total_disponivel = sum(f.quantidade for f in fluxos_para_consumir if f.quantidade)
    
    if total_disponivel == 0:
        return Response({'sucesso': False, 'erro': 'Atenção: Não há peças disponíveis em aberto nesta requisição.'}, status=400)

    # Se o operador tentar puxar mais peças do que o lote total disponível
    if qtd_recebida > total_disponivel:
        resumo_atrasados = {}
        for f in fluxos_para_consumir:
            nome_proc = f.processo.nome if f.processo else "Desconhecido"
            resumo_atrasados[nome_proc] = resumo_atrasados.get(nome_proc, 0) + (f.quantidade or 0)
        
        texto_atrasados = " | ".join([f"{qtd} peças em {proc}" for proc, qtd in resumo_atrasados.items() if qtd > 0])
        msg_erro = f'❌ Você tentou puxar {qtd_recebida} peças, mas só existem {total_disponivel} peças livres na fábrica para este lote.\n\n📍 Onde elas estão: [{texto_atrasados}]'
        
        return Response({'sucesso': False, 'erro': msg_erro}, status=400)

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

    return Response({
        'sucesso': True,
        'mensagem': f'✅ Entrada de {qtd_recebida} peças registada com sucesso no setor de {processo_atual.nome}!'
    })


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