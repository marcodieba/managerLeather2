#!/usr/bin/python
# -*- coding: utf-8 -*-

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import pymssql
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class SelectPedidos(object):

    def _registros_sao_diferentes(self, remoto, local):
        if str(remoto[1] or '').strip() != str(local[1] or '').strip(): return True  # cliente
        if str(remoto[3] or '').strip() != str(local[3] or '').strip(): return True  # nr_contract
        if str(remoto[4] or '').strip() != str(local[4] or '').strip(): return True  # selecao
        if str(remoto[5] or '').strip() != str(local[5] or '').strip(): return True  # artigo
        if str(remoto[7] or '').strip() != str(local[7] or '').strip(): return True  # produto
        
        # Comparação de decimais com tolerância
        if abs(float(remoto[8] or 0.0) - float(local[8] or 0.0)) > 0.0001: return True           # quantidade
        
        # --- AJUSTE 1: Adicionada comparação da quantidade entregue ---
        if abs(float(remoto[9] or 0.0) - float(local[9] or 0.0)) > 0.0001: return True           # quantidade_entregue
        
        if str(remoto[10] or '') != str(local[10] or ''): return True               # dt_programada
        if str(remoto[13] or '').strip() != str(local[13] or '').strip(): return True  # espessura
        if str(remoto[14] or '').strip() != str(local[14] or '').strip(): return True  # unidade_medida
        return False

    def _formatar_dt(self, valor):
        """Converte datetime para string ISO ou retorna None (jamais a string 'None')."""
        if valor is None:
            return None
        if isinstance(valor, str):
            return valor.strip() or None
        # datetime/date vindo do pymssql
        return str(valor)

    def pedidos_marca(self):
        con = pymssql.connect(
            host='192.168.20.250', port='1433',
            user='sa', password='CR@R2018c',
            database='Marca_Evolution'
        )
        cursor = con.cursor()
        # --- AJUSTE 2: Removido o CAST para DECIMAL(10,2) no SQL para evitar arredondamento precoce ---
        cursor.execute("""
            WITH PesosExpedidos AS (
                                    SELECT 
                                        PWB.Cd_Pedido_Comercial_Detalhes, 
                                        SUM(EE.Pes2) AS Pes2_Expedidos
                                    FROM Pedido_Comercial_Programacao_WB PWB
                                    INNER JOIN Estoque_Expedicao EE 
                                        ON EE.Cd_Pedido_Comercial_Artigo = PWB.Codigo
                                    GROUP BY PWB.Cd_Pedido_Comercial_Detalhes
                                ),

                                DatasProgramadas AS (
                                    SELECT 
                                        Cd_Pedido_Comercial_Detalhes, 
                                        MAX(Dt_Programada) AS Dt_Programada
                                    FROM Pedido_Comercial_Programacao_WB
                                    GROUP BY Cd_Pedido_Comercial_Detalhes
                                )

                                SELECT
                                    PP.Codigo, 
                                    C.Nome_Fantasia_CNPJ AS Cliente, 
                                    PCPWB.Codigo AS Cd_contrato,
                                    CONCAT(P.Nr_Invoice_PI, '-', PCPWB.Sequencia) AS Nr_Contract_Seq, 
                                    PP.Selecao,
                                    PP.Artigo_Descricao AS Artigo, 
                                    P.Dt_pedido,

                                    CASE
                                        WHEN PP.Artigo_Produto = 'C' THEN 'COURO WB'
                                        WHEN PP.Artigo_Produto = 'S' THEN 'COURO SEMI'
                                        WHEN PP.Artigo_Produto = 'A' THEN 'COURO ACAB'
                                        WHEN PP.Artigo_Produto = 'R' THEN 'RASPA'
                                        ELSE 'COURO OUTROS'
                                    END AS Produto,

                                    PP.Quantidade_Sqft,
                                    ISNULL(PES.Pes2_Expedidos, 0) AS Pes2_Bruto,
                                    DP.Dt_Programada,

                                    -- NOVA COLUNA dt_embarque
                                    CASE 
                                        WHEN DP.Dt_Programada IS NULL THEN NULL
                                        WHEN CID.UF = 'SP' THEN DATEADD(DAY, -5, DP.Dt_Programada)
                                        WHEN CID.UF = 'GO' THEN DATEADD(DAY, -3, DP.Dt_Programada)
                                        WHEN CID.UF = 'RS' THEN DATEADD(DAY, -7, DP.Dt_Programada)
                                        WHEN CID.UF = 'PA' THEN DATEADD(DAY, -1, DP.Dt_Programada)
                                        ELSE DP.Dt_Programada
                                    END AS dt_embarque,

                                    CASE 
                                        WHEN P.Efetivar = 0 THEN 'N' 
                                        ELSE 'S' 
                                    END AS Fechados,

                                    PP.Espessura, 
                                    PP.Unid_Medida,
                                    CID.Nome,
                                    CID.UF AS UF,
                                    P.Nr_Pedido_Cliente

                                FROM Pedido_Comercial_Detalhes PP

                                INNER JOIN Pedido_Comercial P 
                                    ON P.Codigo = PP.Cd_Pedido_Comercial

                                INNER JOIN Fornecedor_Cliente_CNPJ C 
                                    ON C.Codigo = P.Cd_Cliente_CNPJ

                                INNER JOIN Cidade CID 
                                    ON CID.Codigo = C.Cd_Cidade 

                                LEFT JOIN Pedido_Comercial_Programacao_WB PCPWB 
                                    ON PCPWB.Cd_Pedido_Comercial_Detalhes = PP.Codigo

                                LEFT JOIN PesosExpedidos PES 
                                    ON PES.Cd_Pedido_Comercial_Detalhes = PP.Codigo

                                LEFT JOIN DatasProgramadas DP 
                                    ON DP.Cd_Pedido_Comercial_Detalhes = PP.Codigo

                                WHERE 
                                    PP.Encerra_Det IS NULL 
                                    AND P.Efetivar = 0
                                    AND (
                                        PES.Pes2_Expedidos IS NULL 
                                        OR PP.Quantidade_Sqft >= (6 + PES.Pes2_Expedidos / 10.764)
                                    );
        """)
        rows = cursor.fetchall()
        cursor.close()
        con.close()
        return rows

    def dbsqlite(self):
        connsqlite = sqlite3.connect(BASE_DIR.joinpath('../core/db.sqlite3'))
        connsqlite.execute("PRAGMA journal_mode=WAL;")  # evita locks
        cursorsqlite = connsqlite.cursor()

        print("Buscando dados do Marca Evolution...")
        query_set = self.pedidos_marca()

        pedidos_remotos_map = {item[0]: item for item in query_set}
        print(f"  → {len(pedidos_remotos_map)} pedidos encontrados no SQL Server.")

        print("Buscando dados do banco local (SQLite)...")
        try:
            tabela = cursorsqlite.execute(
                'SELECT cd_pedido, cliente, cidade, uf, nr_pedido_interno, nr_contract, selecao, artigo, '
                'dt_pedido, produto, quantidade, quantidade_entregue, dt_programada, fechado, '
                'espessura, unidade_medida FROM pedido_pedido ORDER BY nr_contract'
            )
            pedidos_locais_map = {item[0]: item for item in tabela.fetchall()}
        except sqlite3.OperationalError as e:
            print(f"  ❌ ERRO ao ler tabela pedido_pedido: {e}")
            connsqlite.close()
            return

        print(f"  → {len(pedidos_locais_map)} pedidos encontrados no SQLite.")

        lista_para_inserir = []
        lista_para_atualizar = []
        lista_para_fechar = []

        print("Comparando bancos de dados...")

        for cd_pedido, dados_remotos in pedidos_remotos_map.items():
            dados = list(dados_remotos)
            # print(lista_para_atualizar)
            # --- AJUSTE 3: Cálculo de precisão decimal no Python ---
            pes2_bruto = Decimal(str(dados[9] or 0.0))
            qtd_entregue = (pes2_bruto / Decimal('10.764')).quantize(Decimal('0.000'), rounding=ROUND_HALF_UP)
            
            # Converte datas com segurança
            dados[6]  = self._formatar_dt(dados[6])   # dt_pedido
            dados[8]  = float(dados[8] or 0.0)         # quantidade
            dados[9]  = float(qtd_entregue)            # quantidade_entregue (CORRIGIDO)
            dados[10] = self._formatar_dt(dados[10])   # dt_programada
            dados[11] = self._formatar_dt(dados[11])   # dt_programada
            dados_tupla = tuple(dados)

            if cd_pedido not in pedidos_locais_map:
                lista_para_inserir.append((
                    dados_tupla[0],   # cd_pedido
                    dados_tupla[1],   # cliente
                    dados_tupla[15],  # Cidade
                    dados_tupla[16],  # UF
                    dados_tupla[2],   # nr_pedido_interno
                    dados_tupla[17],  # cod. Pedido Cliente
                    dados_tupla[3],   # nr_contract
                    dados_tupla[4],   # selecao
                    dados_tupla[5],   # artigo
                    dados_tupla[6],   # dt_pedido
                    dados_tupla[7],   # produto
                    dados_tupla[8],   # quantidade
                    dados_tupla[9],   # quantidade_entregue (AGORA COM VALOR REAL)
                    dados_tupla[10],  # dt_programada
                    dados_tupla[11],  # dt_embarque
                    0,                # fechado
                    dados_tupla[13],  # espessura
                    dados_tupla[14],  # unidade_medida
                    
                ))
            else:
                dados_locais = pedidos_locais_map[cd_pedido]
                if self._registros_sao_diferentes(dados_tupla, dados_locais):
                    # --- AJUSTE 4: Incluído quantidade_entregue no UPDATE ---
                    lista_para_atualizar.append((
                        dados_tupla[1],   # cliente
                        # dados_tupla[15],  # Cidade
                        # dados_tupla[16],  # UF
                        dados_tupla[3],   # nr_contract
                        dados_tupla[4],   # selecao
                        dados_tupla[5],   # artigo
                        dados_tupla[7],   # produto
                        dados_tupla[8],   # quantidade
                        dados_tupla[9],   # quantidade_entregue (NOVO)
                        dados_tupla[10],  # dt_programada
                        dados_tupla[11],  # dt_embarque
                        dados_tupla[13],  # espessura
                        dados_tupla[14],  # unidade_medida
                        cd_pedido,        # WHERE
                    ))

        for cd_pedido_local in pedidos_locais_map:
            if cd_pedido_local not in pedidos_remotos_map:
                lista_para_fechar.append((1, cd_pedido_local))

        if not any([lista_para_inserir, lista_para_atualizar, lista_para_fechar]):
            print("✅ Nenhuma alteração detectada. Banco local já sincronizado.")
            connsqlite.close()
            return

        try:
            if lista_para_inserir:
                print(f"  → Inserindo {len(lista_para_inserir)} novos pedidos...")
                cursorsqlite.executemany("""
                    INSERT INTO pedido_pedido
                        (cd_pedido, cliente, cidade, uf, nr_pedido_interno, nr_pedido_cliente, nr_contract, selecao, artigo,
                         dt_pedido, produto, quantidade, quantidade_entregue, dt_programada, dt_embarque,
                         fechado, espessura, unidade_medida)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, lista_para_inserir)

            if lista_para_atualizar:
                print(f"  → Atualizando {len(lista_para_atualizar)} pedidos modificados...")
                # --- AJUSTE 5: Query SQL atualizada para incluir a coluna quantidade_entregue ---
                cursorsqlite.executemany("""
                    UPDATE pedido_pedido
                    SET cliente=?, nr_contract=?, selecao=?, artigo=?, produto=?,
                        quantidade=?, quantidade_entregue=?, dt_programada=?, dt_embarque=?, espessura=?, unidade_medida=?
                    WHERE cd_pedido = ?
                """, lista_para_atualizar)

            if lista_para_fechar:
                print(f"  → Fechando {len(lista_para_fechar)} pedidos antigos...")
                cursorsqlite.executemany("""
                    UPDATE pedido_pedido SET fechado = ? WHERE cd_pedido = ?
                """, lista_para_fechar)

            connsqlite.commit()
            print("✅ Sincronização concluída com sucesso!")

        except sqlite3.IntegrityError as e:
            connsqlite.rollback()
            print(f"❌ ERRO de integridade (duplicidade/constraint): {e}")
        except sqlite3.OperationalError as e:
            connsqlite.rollback()
            print(f"❌ ERRO operacional SQLite (schema/coluna?): {e}")
        except Exception as e:
            connsqlite.rollback()
            print(f"❌ ERRO inesperado: {e}")
        finally:
            cursorsqlite.close()
            connsqlite.close()


p = SelectPedidos()
p.dbsqlite()
