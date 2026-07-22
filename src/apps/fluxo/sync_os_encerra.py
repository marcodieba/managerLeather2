import pymssql
from django.utils import timezone
from datetime import timedelta
from src.apps.fluxo.models import Requisicao
import logging

logger = logging.getLogger(__name__)

class SyncOrdemServico:
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
            logger.error(f"Erro de conexão com o banco de dados SQL Server: {e}")
            raise

    def sync_e_encerra_requisicoes(self):
        """
        Busca O.S. criadas nos últimos 7 dias e encerra as requisições locais (abertas) correspondentes.
        """
        con = self.conexao()
        cursor = con.cursor(as_dict=True)
        
        # Buscar OS dos últimos 7 dias. Usamos o Nr_Fulao como especificado pelo utilizador.
        query = """
            SELECT TOP 100 PERCENT
                Ordem_Servico.Codigo, 
                Ordem_Servico.Dt_Hr_Digitacao, 
                Ordem_Servico.Nr_Fulao,
                Ordem_Servico.Nr_OS,
                Dt_Inicio_OS,
                Ordem_Servico.Marca_no_Couro as Marca_Couro,
                ISNULL((SELECT SUM(EES.Qt_Expedicao) FROM Estoque_Expedicao_SeA EES WHERE EES.Cd_Pedido_Comercial_Movimento_OS = Ordem_Servico.Codigo), 0) AS Pecas_Exp,
                ISNULL((SELECT SUM(EES.M2_Pes2) FROM Estoque_Expedicao_SeA EES WHERE EES.Cd_Pedido_Comercial_Movimento_OS = Ordem_Servico.Codigo), 0) AS metro2_exp,
                Ordem_Servico.Cd_Sea_Posicao_OS
            FROM Pedido_Comercial_Artigo_Programacao AS Ordem_Servico
            WHERE Ordem_Servico.Dt_Hr_Digitacao >= DATEADD(day, -90, GETDATE())
               OR Dt_Inicio_OS >= DATEADD(day, -90, GETDATE())
            ORDER BY Ordem_Servico.Dt_Hr_Digitacao ASC
        """
        
        try:
            cursor.execute(query)
            ordens = cursor.fetchall()
        except Exception as e:
            logger.error(f"Erro ao buscar ordens no ERP: {e}")
            cursor.close()
            con.close()
            return {"sucesso": False, "erro": str(e)}
            
        cursor.close()
        con.close()
        
        atualizadas = 0
        logs = []

        for os in ordens:
            marca_couro = os.get('Marca_Couro')
            fulao = os.get('Nr_Fulao')
            dt_os = os.get('Dt_Inicio_OS') or os.get('Dt_Hr_Digitacao')
            
            if not marca_couro:
                continue
                
            # Limpar espaços para garantir um bom match
            marca_couro = str(marca_couro).strip()
            
            # Tratar fulão que pode ser None ou vazio
            try:
                fulao_int = int(fulao) if fulao else None
            except (ValueError, TypeError):
                fulao_int = None
                
            # Construir filtro dinamicamente
            filtros = {
                'lote': marca_couro,
                'encerrado': False
            }
            if fulao_int is not None:
                filtros['fulao'] = fulao_int
                
            # Buscar requisições ativas com o mesmo lote (e fulão se existir)
            requisicoes = Requisicao.objects.filter(**filtros).order_by('dt_requisicao')
            
            for req in requisicoes:
                # Verificar as condições de encerramento
                # A Regra diz: Só deve encerrar após a verificação da OS (Cd_Sea_Posicao_OS = 7)
                os_finalizada = (str(os.get('Cd_Sea_Posicao_OS', '')) == '7')
                
                if not os_finalizada:
                    # Não atende às condições para encerrar (OS não finalizada)
                    continue

                # Vamos fechar e atualizar os valores!
                pecas_exp = os.get('Pecas_Exp') or 0
                metro2_exp = os.get('metro2_exp') or 0.0
                nr_os = os.get('Nr_OS') or os.get('Codigo')
                
                req.qt = int(pecas_exp)
                req.m2 = float(metro2_exp)
                req.encerrado = True
                
                obs_msg = f"[{timezone.now().strftime('%d/%m/%Y %H:%M')}] [AUTO-SYNC] Requisição encerrada e quantidades atualizadas (Qt: {req.qt}, M2: {req.m2}) via OS Nº {nr_os} do ERP."
                
                if req.obs:
                    req.obs = f"{req.obs}\n{obs_msg}"
                else:
                    req.obs = obs_msg
                    
                req.save()
                atualizadas += 1
                logs.append(f"Requisicao {req.cd_requisicao} ({marca_couro}) encerrada usando OS {nr_os}.")
                
                # Quebramos o loop pois a O.S. já encontrou a sua requisição ativa mais antiga que bate com os requisitos.
                break

        resultado = {
            "sucesso": True,
            "atualizadas": atualizadas,
            "logs": logs
        }
        return resultado
