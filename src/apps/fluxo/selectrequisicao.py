#!/usr/bin/python
# -*- coding: utf-8 -*-

# import pymssql
# 201.182.222.33:3390
# import pyodbc
import datetime
from decimal import Decimal
from unicodedata import decimal
import pymssql
import re
import sqlite3
import difflib

from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

date_now = datetime.datetime.now()
# .strftime('%Y-%m-%d %H:%M:%S')
# print(date_now)
class SelectRequisicao(object):
# (
#                                 SELECT TOP 1 RP.Observacao 
#                                 FROM Requisicao_Partida RP 
#                                 WHERE RP.Cd_Requisicao = Requisicao.Codigo 
#                                 AND RP.Sea_OS IS NOT NULL
#                                 ORDER BY RP.Sea_OS
#                             ) AS Pallet_Refila,


    def conexao(self):
        con = pymssql.connect(host='192.168.20.250',
                              port='1433',
                              user='sa',
                              password='CR@R2018c',
                              database='Marca_Evolution'
                              )
        return con.cursor()

    def requisicao(self):
        
        # cnxn = pyodbc.connect('DRIVER={ODBC Driver 13 for SQL
        # Server};SERVER='+server+';DATABASE='+database+';UID='+username+';PWD='+ password)

        

        cursor = self.conexao()
        # for obj in formulas:
        cursor.execute(""" SELECT TOP 300
                            Requisicao.Codigo,
                            Requisicao.Dt_Hr_Requisicao,

                            ISNULL(
                                STUFF(
                                    (
                                        SELECT ', ' + DistinctLotes.Sea_OS
                                        FROM (
                                            SELECT DISTINCT RP_Lote.Sea_OS
                                            FROM Requisicao_Partida RP_Lote
                                            WHERE RP_Lote.Cd_Requisicao = Requisicao.Codigo
                                            AND RP_Lote.Sea_OS IS NOT NULL
                                        ) AS DistinctLotes
                                        ORDER BY DistinctLotes.Sea_OS
                                        FOR XML PATH(''), TYPE
                                    ).value('.', 'NVARCHAR(MAX)')
                                , 1, 2, ''),
                            '') AS Lote,

                            ISNULL(Formulacao.Nome, '') + 
                            CASE 
                                WHEN Formulacao_Grupo.Nome IS NOT NULL 
                                THEN ' - ' + CONVERT(CHAR(20), Formulacao_Grupo.Nome)
                                ELSE ''
                            END AS Nm_05_Formulacao,

                            ISNULL(
                                STUFF(
                                    (
                                        SELECT ', ' + CAST(InnerData.QuantidadeParaAgg AS VARCHAR)
                                        FROM (
                                            SELECT TOP 10
                                                RP.Quantidade AS QuantidadeParaAgg,
                                                CASE WHEN RP.Sea_OS IS NULL THEN 1 ELSE 0 END AS SeaOS_Sort_Priority,
                                                RP.Sea_OS AS SeaOS_Sort_Value
                                            FROM Requisicao_Partida RP
                                            WHERE RP.Cd_Requisicao = Requisicao.Codigo
                                            ORDER BY
                                                CASE WHEN RP.Sea_OS IS NULL THEN 1 ELSE 0 END,
                                                RP.Sea_OS,
                                                RP.Quantidade
                                        ) AS InnerData
                                        ORDER BY
                                            InnerData.SeaOS_Sort_Priority,
                                            InnerData.SeaOS_Sort_Value,
                                            InnerData.QuantidadeParaAgg
                                        FOR XML PATH(''), TYPE
                                    ).value('.', 'NVARCHAR(MAX)')
                                , 1, 2, ''),
                            '') AS Pecas,

                            ISNULL(Requisicao.Peso, 0) AS Peso_Kgs,
                            ISNULL(Requisicao.Observacoes, '') AS Cd_Observacoes,
                            Requisicao.Fulao,

                            ISNULL(
                                STUFF(
                                    (
                                        SELECT ', ' + InnerData.ObservacaoParaAgg
                                        FROM (
                                            SELECT TOP 10
                                                RP.Observacao AS ObservacaoParaAgg,
                                                CASE WHEN RP.Sea_OS IS NULL THEN 1 ELSE 0 END AS SeaOS_Sort_Priority,
                                                RP.Sea_OS AS SeaOS_Sort_Value
                                            FROM Requisicao_Partida RP
                                            WHERE RP.Cd_Requisicao = Requisicao.Codigo
                                            ORDER BY
                                                CASE WHEN RP.Sea_OS IS NULL THEN 1 ELSE 0 END,
                                                RP.Sea_OS,
                                                RP.Observacao
                                        ) AS InnerData
                                        ORDER BY
                                            InnerData.SeaOS_Sort_Priority,
                                            InnerData.SeaOS_Sort_Value,
                                            InnerData.ObservacaoParaAgg
                                        FOR XML PATH(''), TYPE
                                    ).value('.', 'NVARCHAR(MAX)')
                                , 1, 2, ''),
                            '') AS Pallet_Refila,

                            ISNULL(Requisicao.Pecas, 0) AS total_pc

                        FROM Requisicao
                        LEFT JOIN Formulacao
                            ON Formulacao.Codigo = Requisicao.Cd_Formulacao
                        LEFT JOIN Unidade_de_Producao
                            ON Unidade_de_Producao.Codigo = Requisicao.Cd_Unidade_de_Producao
                        LEFT JOIN Funcionario Usuario_Origem
                            ON Usuario_Origem.Codigo = Requisicao.Cd_Usuario_Origem
                        LEFT JOIN Funcionario Ultimo_Usuario
                            ON Ultimo_Usuario.Codigo = Requisicao.Cd_Ultimo_Usuario
                        LEFT JOIN Formulacao_Grupo
                            ON Formulacao.Cd_Formulacao_Grupo = Formulacao_Grupo.Codigo

                        WHERE
                            Grupo_Industria = 'S'
                            OR Grupo_Industria = 'W'
                            AND EXISTS (
                                SELECT 1
                                FROM Requisicao_Partida RP_Exists
                                WHERE RP_Exists.Cd_Requisicao = Requisicao.Codigo
                            )

                        ORDER BY Requisicao.Dt_Hr_Requisicao DESC;
                        """#.format(form=obj)
                                )

        # print(str(list(cursor.fetchall())))
        return cursor.fetchall()
            # d = str(list(cursor.fetchone())[0])
            # print(d.replace('.',','))
    
    def post_requisicao(self):
        with sqlite3.connect(BASE_DIR.joinpath('../core/db.sqlite3'), timeout=10, isolation_level=None) as connsqlite:
        # connsqlite = sqlite3.connect(BASE_DIR.joinpath('../core/db.sqlite3'))
            cursorsqlite = connsqlite.cursor()
            query_set = self.requisicao()
            cursor = self.conexao()
            padrao = re.compile(r'^\d+-\d+-\d+$')
            padrao_refilo = re.compile(r'^:\d+$')
            cursorsqlite.execute('BEGIN')
            for cd_req in query_set:
                try:
                    rq = str(cd_req[4])
                    pcs = cd_req[4].split(',')
                    # print(cd_req[0])
                
                    if str(cd_req[8][0:9]) is not None or str(cd_req[8][0:9]) is not NULL:
                        pallet = cd_req[8].split(',')
                        lista_np = str(cd_req[6]).split(',')
                    refila = [float(item.split(':', 1)[-1]) for item in pallet if 'REFI' in item]
                except:
                    continue
                            # : item.split(':', 1)[1] if ':' in item else
                
                
                np = ''
                for item in lista_np:
                    if ':' in item:
                        # Divide o item em chave e valor, separando apenas no primeiro ':'
                        np = item.split(':', 1)
                nr_pedidos = [
                        item for item in np 
                        if isinstance(item, str) and padrao.match(item)
                    ]

                req_date = [date_now, cd_req[0], cd_req[1].strftime('%Y-%m-%d %H:%M:%S'), cd_req[2], cd_req[3], cd_req[9], cd_req[6], cd_req[7], date_now, 0]

                # ✅ NOVO BLOCO (NÃO ALTERA SUA LÓGICA)
                nome_formulacao = str(cd_req[3]).strip().upper()

                prefixo = nome_formulacao[:3]

                if prefixo == 'CUR':
                    setor = 'Cur'
                elif prefixo == 'CAL':
                    setor = 'Cal'
                else:
                    setor = 'REC'
                # ✅ FIM DO BLOCO NOVO

                requisicao = cursorsqlite.execute("""
                    SELECT cd_requisicao, artigo, dt_requisicao, lote, quantidade, qt_mt 
                    FROM fluxo_requisicao 
                    WHERE cd_requisicao = ? 
                """, (cd_req[0],))

                if req_date[6] == 'NULL':
                    req_date[6] = 'FICHA'

                resultado_remv_refilo = [nome for nome in pallet]
                for rm_refilo in pallet:
                    if 'REFI' in rm_refilo:
                        resultado_remv_refilo.remove(rm_refilo)

                nr_Pallet = str(resultado_remv_refilo)
                req_date.append(nr_Pallet.strip('[]'))

                metros_pallet = []
                pcs_ = []

                for obj in resultado_remv_refilo:

                    cursor.execute(f"""
                        SELECT 
                            ee_main.Codigo,
                            ee_main.Trava_Pallet,
                            ee_main.Nr_Pallet,
                            ee_main.Pes2,
                            ee_main.Pecas,
                            wba_main.Unid_em_Couro,
                            ee_main.Pecas * wba_main.Unid_em_Couro AS Couros,
                            ee_main.Peso_Pallet,
                            ee_main.Peso_Pallet_Lq
                        FROM
                            Estoque_Expedicao ee_main
                        LEFT OUTER JOIN
                            WB_Artigo wba_main ON wba_main.Codigo = ee_main.Cd_WB_Artigo
                        WHERE
                            ee_main.Nr_Pallet = '{obj.strip(' ')}'
                    """)

                    rows = cursor.fetchall()

                    for pc in pcs:
                        pc = str(pc).strip()

                        # ✅ CORREÇÃO (não altera lógica)
                        if not pc or not pc.isdigit():
                            continue

                        if pc not in pcs_:
                            pcs_.append(pc)   
                            for obj in rows:
                                # print(obj[3])
                                # print(obj[4])

                                metragem_pallet = (
                                    ((float(obj[3])/10.764)/obj[4]) if obj[4] > 0 else obj[3]
                                )

                                metros_pallet.append(metragem_pallet * int(pc))
            
                req_date.append(sum(metros_pallet))

                # ✅ ALTERAÇÃO MÍNIMA: adiciona campo setor
                cursorsqlite.execute("""
                                        INSERT INTO fluxo_requisicao (
                                            data, cd_requisicao, dt_requisicao, lote, artigo, quantidade,
                                            ficha, fulao, modificado, encerrado, pallet, qt_mt, setor
                                        )
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        ON CONFLICT(cd_requisicao) DO UPDATE SET
                                            data = excluded.data,
                                            dt_requisicao = excluded.dt_requisicao,
                                            lote = excluded.lote,
                                            artigo = excluded.artigo,
                                            quantidade = excluded.quantidade,
                                            obs = excluded.ficha,
                                            fulao = excluded.fulao,
                                            modificado = excluded.modificado,
                                            encerrado = excluded.encerrado,
                                            pallet = excluded.pallet,
                                            qt_mt = excluded.qt_mt,
                                            setor = excluded.setor
                                        WHERE 
                                            data != excluded.data OR
                                            dt_requisicao != excluded.dt_requisicao OR
                                            lote != excluded.lote OR
                                            artigo != excluded.artigo OR
                                            quantidade != excluded.quantidade OR
                                            obs != excluded.ficha OR
                                            fulao != excluded.fulao OR
                                            modificado != excluded.modificado OR
                                            encerrado != excluded.encerrado OR
                                            pallet != excluded.pallet OR
                                            qt_mt != excluded.qt_mt OR
                                            setor != excluded.setor
                                    """, req_date + [setor])


                # Recupera o ID da requisição mesmo que ela já existisse (caso de UPDATE)
                cursorsqlite.execute("""
                    SELECT id FROM fluxo_requisicao WHERE cd_requisicao = ?
                """, (cd_req[0],))
                row = cursorsqlite.fetchone()

                if not row:
                    continue  # Se por algum motivo não encontrou, evita erro

                requisicao_id = row[0]
                # =====================================================================
                # 1. CRIAR FLUXO DE RECURTIMENTO AUTOMÁTICO
                # =====================================================================
                # Busca ou cria o processo de Recurtimento
                cursorsqlite.execute("SELECT id FROM fluxo_processo WHERE nome LIKE '%Recurtimento%' LIMIT 1")
                proc_row = cursorsqlite.fetchone()
                if not proc_row:
                    cursorsqlite.execute("INSERT INTO fluxo_processo (nome) VALUES ('Recurtimento')")
                    processo_id_recurtimento = cursorsqlite.lastrowid
                else:
                    processo_id_recurtimento = proc_row[0]

                # Prepara os dados (Quantidade e Data da Requisição formatada)
                qtd_fluxo = req_date[5] if req_date[5] else 0
                dt_fluxo = str(req_date[2]) if req_date[2] else date_now.strftime('%Y-%m-%d %H:%M:%S')

                # Insere o fluxo apenas se ele ainda não existir para esta requisição
                cursorsqlite.execute("""
                    INSERT INTO fluxo_fluxorequisicao (requisicao_id, processo_id, quantidade, dt_processo, encerrado)
                    SELECT ?, ?, ?, ?, 0
                    WHERE NOT EXISTS (
                        SELECT 1 FROM fluxo_fluxorequisicao
                        WHERE requisicao_id = ? AND processo_id = ?
                    )
                """, (requisicao_id, processo_id_recurtimento, qtd_fluxo, dt_fluxo, requisicao_id, processo_id_recurtimento))

                # =====================================================================
                # 2. VINCULAR O ARTIGO GENÉRICO AUTOMATICAMENTE
                # =====================================================================
                texto_artigo_req = str(req_date[4]).strip().upper() # req_date[4] é o artigo original
                if texto_artigo_req and texto_artigo_req != 'NULL':
                    cursorsqlite.execute("SELECT id, nome FROM fluxo_artigo")
                    todos_artigos = cursorsqlite.fetchall()
                    
                    artigo_encontrado_id = None
                    palavras_req = set(texto_artigo_req.split())

                    # Tenta achar exato ou por palavras contidas
                    for a_id, a_nome in sorted(todos_artigos, key=lambda x: len(str(x[1])), reverse=True):
                        nome_cadastrado = str(a_nome).strip().upper()
                        palavras_cadastrado = set(nome_cadastrado.split())
                        
                        if nome_cadastrado in texto_artigo_req or palavras_cadastrado.issubset(palavras_req):
                            artigo_encontrado_id = a_id
                            break
                    
                    # Se não achou exato, usa similaridade do difflib
                    if not artigo_encontrado_id:
                        nomes_cadastrados = [a[1] for a in todos_artigos]
                        matches = difflib.get_close_matches(req_date[4], nomes_cadastrados, n=1, cutoff=0.5)
                        if matches:
                            artigo_encontrado_id = next(a[0] for a in todos_artigos if a[1] == matches[0])

                    # Se achou, dá o UPDATE direto na tabela de requisição
                    if artigo_encontrado_id:
                        cursorsqlite.execute("""
                            UPDATE fluxo_requisicao SET artigo_padrao_id = ? WHERE id = ?
                        """, (artigo_encontrado_id, requisicao_id))
                # =====================================================================

                for nr_contrato in nr_pedidos:
                    cursorsqlite.execute("SELECT id FROM pedido_pedido WHERE nr_contract = ?", (nr_contrato,))
                    pedido_row = cursorsqlite.fetchone()

                    if pedido_row:
                        pedido_id = pedido_row[0]
                        print(pedido_id)
                        cursorsqlite.execute("""
                            INSERT INTO pedido_pedidorequisicao (requisicao_id, pedido_id)
                            SELECT ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM pedido_pedidorequisicao
                                WHERE requisicao_id = ? AND pedido_id = ?
                            )
                        """, (requisicao_id, pedido_id, requisicao_id, pedido_id))

                if refila:
                    processo_id = 10
                    cursorsqlite.execute("""
                        INSERT INTO fluxo_refilo (requisicao_id, processo_id, qt_refila)
                        SELECT ?, ?, ?
                        WHERE NOT EXISTS (
                            SELECT 1 FROM fluxo_refilo
                            WHERE requisicao_id = ? AND processo_id = ?
                        )
                    """, (requisicao_id, processo_id, refila[0], requisicao_id, processo_id))

                # except:
                #     print(EOFError)
                
    
                connsqlite.commit()
                cursorsqlite.close  

p = SelectRequisicao()
# p.requisicao_sea()
p.post_requisicao()
