# src/apps/fluxo/api_views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, logout
from django.utils.timezone import is_aware, make_naive
from django.db.models import Q
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from .models import Requisicao, Operador
from .serializers import RequisicaoSerializer, OperadorSerializer
from .views import OrdemServicoSQL, extrair_marca_couro
from .select_custo_formula import custo_requisicao
from src.apps.fluxo.sync_os_encerra import SyncOrdemServico


# --- FUNÇÕES AUXILIARES DE TEMPO ---
def calcular_segundos(dt_inicio, dt_fim):
    if not dt_inicio:
        return 0
    inicio = dt_inicio if isinstance(dt_inicio, datetime) else datetime.combine(dt_inicio, datetime.min.time())
    fim = dt_fim if dt_fim and isinstance(dt_fim, datetime) else (datetime.combine(dt_fim, datetime.min.time()) if dt_fim else datetime.now())
    
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


# --- APIS DO FLUXO ---

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_busca_requisicao(request):
    """Substitui o busca_requisicao_ajax, retornando JSON para dropdowns no React"""
    termo_busca = request.query_params.get('term', '').strip()
    
    if len(termo_busca) < 2:
        return Response([])

    requisicoes = Requisicao.objects.filter(
        Q(cd_requisicao__icontains=termo_busca) | Q(lote__icontains=termo_busca)
    )[:10]

    resultados = [
        {
            'id': req.pk,
            'numero': req.cd_requisicao,
            'cliente': req.lote,
            'data': req.data.strftime('%d/%m/%Y') if req.data else 'N/A'
        }
        for req in requisicoes
    ]
    return Response(resultados)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_resumo_lotes_ativos(request):
    """Substitui a resumo_lotes_ativos_view"""
    requisicoes_ativas = Requisicao.objects.filter(
        encerrado=False,
        fluxos__processo__nome__icontains='Recurtimento'
    ).distinct().prefetch_related('fluxos__processo')

    dados_relatorio = []

    for req in requisicoes_ativas:
        primeiro_fluxo = req.fluxos.order_by('dt_processo', 'id').first()
        if not primeiro_fluxo:
            continue
        
        data_inicio_total = primeiro_fluxo.dt_processo
        tempo_total_segundos = calcular_segundos(data_inicio_total, datetime.now())
        
        fluxos_ativos = req.fluxos.filter(encerrado=False)
        locais_atuais = []
        
        for f in fluxos_ativos:
            if f.processo:
                locais_atuais.append({
                    'nome': f.processo.nome,
                    'quantidade': f.quantidade,
                    'tempo_no_setor': formatar_tempo(calcular_segundos(f.dt_processo, datetime.now()))
                })

        if locais_atuais:
            dados_relatorio.append({
                'id': req.id,
                'cd_requisicao': req.cd_requisicao,
                'lote': req.lote or "N/A",
                'artigo': req.artigo or "N/A",
                'data_inicio': data_inicio_total.isoformat() if data_inicio_total else None,
                'tempo_total': formatar_tempo(tempo_total_segundos),
                'locais_atuais': locais_atuais
            })

    # Ordena os mais antigos primeiro
    dados_relatorio.sort(key=lambda x: x['data_inicio'] if x['data_inicio'] else "")

    return Response({"data_atual": date.today().isoformat(), "lotes": dados_relatorio})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_imprimir_rendimento(request):
    """Substitui imprimir_rendimento_view (Rendimento, Fluxograma e Custo)"""
    ids_str = request.query_params.get("ids", "")
    tipo = request.query_params.get("tipo", "padrao")
    
    if not ids_str:
        return Response({"erro": "Parâmetro 'ids' é obrigatório."}, status=400)
        
    ids = [int(i) for i in ids_str.split(",") if i.isdigit()]
    objetos = Requisicao.objects.filter(id__in=ids)

    # Regra de negócio legada mantida:
    if tipo == "custo":
        cd_requisicao = request.query_params.get("cd_requisicao")
        if cd_requisicao:
            custo_requisicao([cd_requisicao])

    resposta_dados = []

    for req in objetos:
        fluxos = list(req.get_fluxos_ordenados())
        fluxos_processados = []
        processos_ativos_dict = {}
        total_segundos_req = 0 

        for fluxo in fluxos:
            data_fim = fluxo.dt_saida if fluxo.encerrado and fluxo.dt_saida else (fluxo.dt_processo if fluxo.encerrado else datetime.now())
            segundos_setor = calcular_segundos(fluxo.dt_processo, data_fim)
            
            total_segundos_req += segundos_setor
            
            # Serializar manualmente os campos necessários do fluxo
            fluxos_processados.append({
                'id': fluxo.id,
                'processo_nome': fluxo.processo.nome if fluxo.processo else "N/A",
                'quantidade': fluxo.quantidade,
                'encerrado': fluxo.encerrado,
                'dt_processo': fluxo.dt_processo.isoformat() if fluxo.dt_processo else None,
                'dt_saida': fluxo.dt_saida.isoformat() if fluxo.dt_saida else None,
                'tempo_processo': formatar_tempo(segundos_setor)
            })

            if not fluxo.encerrado and fluxo.processo:
                pid = fluxo.processo.id
                if pid not in processos_ativos_dict:
                    processos_ativos_dict[pid] = {
                        'nome': fluxo.processo.nome,
                        'dt_processo': fluxo.dt_processo.isoformat() if fluxo.dt_processo else None,
                        'tempo_no_processo': formatar_tempo(calcular_segundos(fluxo.dt_processo, datetime.now())),
                        'quantidade': 0
                    }
                processos_ativos_dict[pid]['quantidade'] += (fluxo.quantidade or 0)
        
        # Estruturar o objeto final para o JSON
        req_data = RequisicaoSerializer(req).data
        req_data['fluxos_com_tempo'] = fluxos_processados
        req_data['processos_ativos_agrupados'] = list(processos_ativos_dict.values())
        req_data['tempo_total_formatado'] = formatar_tempo(total_segundos_req)
        
        resposta_dados.append(req_data)

    return Response({
        "tipo_relatorio": tipo,
        "data_atual": date.today().isoformat(),
        "requisicoes": resposta_dados
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_calcular_ordem_servico(request):
    """
    Substitui ordem_servico_page.
    Espera receber no corpo (JSON): 
    { "itens": [{"requisicao_id": 1, "quantidade": "100.5"}, ...] }
    """
    itens = request.data.get('itens', [])
    resultado_final = []
    erros = []

    total_pecas = Decimal(0)
    total_metro = Decimal(0)
    total_resultado = Decimal(0)

    if not itens:
        return Response({"erro": "Nenhum item foi enviado para processamento."}, status=400)

    for item in itens:
        req_id = item.get('requisicao_id')
        qtd_str = str(item.get('quantidade', '0')).replace(',', '.')
        
        try:
            requisicao = Requisicao.objects.get(pk=req_id)
            marca_couro = extrair_marca_couro(requisicao.lote)
            if not marca_couro:
                erros.append(f"A requisição ID {req_id} não possui marca de couro válida no lote.")
                continue
            
            quantidade = Decimal(qtd_str)
            if quantidade <= 0:
                continue

            sql = OrdemServicoSQL()
            ordens = sql.buscar_ordens(marca_couro)
            
            for ordem in ordens:
                pecas = Decimal(ordem.get('Pecas_WB') or 0)
                metro = Decimal(ordem.get('Metro2_WB') or 0)
                
                media_m2_peca = (metro / pecas) if pecas > 0 else Decimal(0)
                resultado_calc = media_m2_peca * quantidade
                
                ordem['Media_Metro_Peca'] = float(round(media_m2_peca, 2))
                ordem['Resultado'] = float(round(resultado_calc, 2))
                
                # Tratamento para serialização JSON
                ordem['Pecas_WB'] = float(pecas)
                ordem['Metro2_WB'] = float(metro)
                
                total_pecas += pecas
                total_metro += metro
                total_resultado += resultado_calc

                resultado_final.append(ordem)

        except Requisicao.DoesNotExist:
            erros.append(f"Requisição com ID {req_id} não encontrada.")
        except InvalidOperation:
            erros.append(f"Quantidade '{qtd_str}' para requisição ID {req_id} é inválida.")
        except Exception as e:
            erros.append(f"Erro ao processar item {req_id}: {str(e)}.")

    return Response({
        "resultado": resultado_final,
        "erros": erros,
        "totais": {
            "pecas": float(total_pecas),
            "metro": float(round(total_metro, 2)),
            "resultado": float(round(total_resultado, 2)),
        }
    })

# ============================================================
# AUTENTICAÇÃO REST VIA TOKEN
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response({'erro': 'Usuário e senha são obrigatórios.'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)

    if not user:
        return Response({'erro': 'Credenciais inválidas.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        operador = Operador.objects.get(usuario=user)
    except Operador.DoesNotExist:
        # Se for um superuser (gestor) que não tem perfil de Operador, permitimos o login
        # mas retornamos apenas os dados básicos para não quebrar o React
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'operador': {
                'id': user.id,
                'nome_usuario': user.username,
                'processos': []
            }
        }, status=status.HTTP_200_OK)

    token, _ = Token.objects.get_or_create(user=user)
    operador_data = OperadorSerializer(operador).data

    return Response({
        'token': token.key,
        'operador': operador_data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_me(request):
    try:
        operador = Operador.objects.get(usuario=request.user)
        serializer = OperadorSerializer(operador)
        return Response(serializer.data)
    except Operador.DoesNotExist:
        # Fallback para gestores sem perfil de operador
        return Response({
            'id': request.user.id,
            'nome_usuario': request.user.username,
            'processos': []
        })

@api_view(['POST'])
@permission_classes([AllowAny]) # Pode restringir para IsAuthenticated se preferir
def api_sync_ordens_servico(request):
    """
    Inicia o processo manual (via clique no botão) para sincronizar e encerrar
    as requisições locais com base nas Ordens de Serviço do Marca_Evolution.
    """
    sync_tool = SyncOrdemServico()
    resultado = sync_tool.sync_e_encerra_requisicoes()
    
    if resultado.get("sucesso"):
        return Response({
            'sucesso': True,
            'mensagem': f'Sincronização concluída! {resultado.get("atualizadas")} requisições encerradas.',
            'logs': resultado.get("logs")
        })
    else:
        return Response({
            'sucesso': False,
            'mensagem': f'Erro na sincronização: {resultado.get("erro")}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def api_logout(request):
    logout(request)
    return Response({"detail": "Logout successful."})