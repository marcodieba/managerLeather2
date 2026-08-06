import pymssql
# pyrefly: ignore [missing-import]
from django.utils import timezone
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
        Busca O.S. dos últimos 90 dias e:
          - SEMPRE atualiza m2, qt e rendimento (mesmo OS parcial/não finalizada)
          - Só encerra a requisição quando Cd_Sea_Posicao_OS = 7 (OS finalizada)
        """
        con = self.conexao()
        cursor = con.cursor(as_dict=True)

        query = """
            SELECT TOP 100 PERCENT
                Ordem_Servico.Codigo,
                Ordem_Servico.Dt_Hr_Digitacao,
                Ordem_Servico.Nr_Fulao,
                Ordem_Servico.Nr_OS,
                Dt_Inicio_OS,
                Ordem_Servico.Marca_no_Couro AS Marca_Couro,
                ISNULL((SELECT SUM(EES.Qt_Expedicao)
                        FROM Estoque_Expedicao_SeA EES
                        WHERE EES.Cd_Pedido_Comercial_Movimento_OS = Ordem_Servico.Codigo), 0) AS Pecas_Exp,
                ISNULL((SELECT SUM(EES.M2_Pes2)
                        FROM Estoque_Expedicao_SeA EES
                        WHERE EES.Cd_Pedido_Comercial_Movimento_OS = Ordem_Servico.Codigo), 0) AS metro2_exp,
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
        encerradas  = 0
        logs        = []

        for os in ordens:
            marca_couro = os.get('Marca_Couro')
            fulao       = os.get('Nr_Fulao')

            if not marca_couro:
                continue

            marca_couro = str(marca_couro).strip()

            try:
                fulao_int = int(fulao) if fulao else None
            except (ValueError, TypeError):
                fulao_int = None

            filtros = {'lote': marca_couro, 'encerrado': False}
            if fulao_int is not None:
                filtros['fulao'] = fulao_int

            requisicoes = Requisicao.objects.filter(**filtros).order_by('dt_requisicao')

            pecas_exp    = os.get('Pecas_Exp') or 0
            metro2_exp   = os.get('metro2_exp') or 0.0
            nr_os        = os.get('Nr_OS') or os.get('Codigo')
            os_finalizada = str(os.get('Cd_Sea_Posicao_OS', '')) == '7'

            for req in requisicoes:
                houve_mudanca     = False
                campos_atualizados = []

                nova_m2 = float(metro2_exp) if metro2_exp else 0.0
                nova_qt = int(pecas_exp) if pecas_exp else 0

                # ── Atualiza m2 produzido (parcial ou final) ───────────────────
                m2_atual = float(req.m2) if req.m2 is not None else 0.0
                if abs(m2_atual - nova_m2) > 0.001:
                    req.m2 = nova_m2
                    houve_mudanca = True
                    campos_atualizados.append(f"m2={nova_m2:.2f}")

                # ── Atualiza peças expedidas ───────────────────────────────────
                qt_atual = int(req.qt) if req.qt is not None else 0
                if qt_atual != nova_qt:
                    req.qt = nova_qt
                    houve_mudanca = True
                    campos_atualizados.append(f"qt={nova_qt}")

                # ── Calcula rendimento: m2_saida / qt_mt_entrada * 100 ─────────
                if nova_m2 > 0 and req.qt_mt and float(req.qt_mt) > 0:
                    rend_calc = round((nova_m2 / float(req.qt_mt)) * 100, 2)
                    rend_atual = float(req.rend) if req.rend is not None else 0.0
                    if abs(rend_atual - rend_calc) > 0.01:
                        req.rend = rend_calc
                        houve_mudanca = True
                        campos_atualizados.append(f"rend={rend_calc}%")


                # ── Encerra SOMENTE quando OS finalizada (posição 7) ──────────
                if os_finalizada:
                    req.encerrado = True
                    houve_mudanca = True
                    campos_atualizados.append("encerrado=True")

                if houve_mudanca:
                    # Sanitiza fulao: SQLite aceita texto em campos inteiros,
                    # mas o Django valida no save() e lança ValueError se não for número.
                    if req.fulao is not None:
                        try:
                            req.fulao = int(req.fulao)
                        except (ValueError, TypeError):
                            req.fulao = None

                    obs_tipo = "ENCERRADO" if os_finalizada else "PARCIAL"
                    obs_msg = (
                        f"[{timezone.now().strftime('%d/%m/%Y %H:%M')}] "
                        f"[SYNC-{obs_tipo}] OS Nº {nr_os}: "
                        f"{', '.join(campos_atualizados)}."
                    )
                    req.obs = f"{req.obs}\n{obs_msg}" if req.obs else obs_msg
                    req.save()
                    atualizadas += 1
                    if os_finalizada:
                        encerradas += 1
                        logs.append(
                            f"[ENCERRADO] Req {req.cd_requisicao} ({marca_couro}) — "
                            f"OS {nr_os}: m2={nova_m2:.2f}, qt={nova_qt}."
                        )
                    else:
                        logs.append(
                            f"[PARCIAL]   Req {req.cd_requisicao} ({marca_couro}) — "
                            f"OS {nr_os}: {', '.join(campos_atualizados)}."
                        )

                # Processa apenas a requisição mais antiga por OS
                break

        return {
            "sucesso": True,
            "atualizadas": atualizadas,
            "encerradas": encerradas,
            "logs": logs
        }
