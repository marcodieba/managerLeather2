#!/usr/bin/python
# -*- coding: utf-8 -*-

#import pymssql
#201.182.222.33:3390
# import pyodbc
from datetime import datetime
from decimal import Decimal
from unicodedata import decimal
import pymssql
import re
import sqlite3

from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

class SelectPedidos(object):

    def pedidos_marca(self):
        server = 'tcp:192.168.20.250'
        database = 'Marca_Evolution'
        username = 'sa'
        password = 'CR@R2018c'
#        cnxn = pyodbc.connect('DRIVER={ODBC Driver 13 for SQL Server};SERVER='+server+';DATABASE='+database+';UID='+username+';PWD='+ password)

        con = pymssql.connect(host = '192.168.20.250',
                              port = '1433',
                              user = 'sa',
                              password = 'CR@R2018c',
                              database = 'Marca_Evolution'
                             )

        cursor = con.cursor()

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
                                PCPWB.Codigo as Cd_contrato,
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
                                CAST(ISNULL(6 + PES.Pes2_Expedidos, 0) / 10.764 AS DECIMAL(10, 2)) AS Pes2_Expedidos,
                                DP.Dt_Programada,

                                CASE 
                                    WHEN P.Efetivar = 0 THEN 'N' 
                                    ELSE 'S' 
                                END AS Fechados,

                                PP.Espessura,
                                PP.Unid_Medida
                                

                            FROM Pedido_Comercial_Detalhes PP

                            -- Joins 1:1
                            INNER JOIN Pedido_Comercial P 
                                ON P.Codigo = PP.Cd_Pedido_Comercial
                            INNER JOIN Fornecedor_Cliente_CNPJ C 
                                ON C.Codigo = P.Cd_Cliente_CNPJ
							 LEFT OUTER JOIN Pedido_Comercial_Programacao_WB PCPWB  ON 
								--Pedido_Comercial.Nr_Invoice_PI = PCPWB.Nr_Contract and 
								PCPWB.Cd_Pedido_Comercial_Detalhes = PP.Codigo
                            -- Joins com CTEs agregadas
                            LEFT JOIN PesosExpedidos PES 
                                ON PES.Cd_Pedido_Comercial_Detalhes = PP.Codigo
                            LEFT JOIN DatasProgramadas DP 
                                ON DP.Cd_Pedido_Comercial_Detalhes = PP.Codigo



                            -- Filtro principal
                            WHERE PP.Encerra_Det IS NULL AND P.Efetivar = 0
                            AND (
                                    PES.Pes2_Expedidos IS NULL
                                    OR
                                    PP.Quantidade_Sqft >= (6 + PES.Pes2_Expedidos / 10.764));
                            """)
        # print(str(list(cursor.fetchall())))
        return cursor.fetchall()

    def dbsqlite(self):
        connsqlite = sqlite3.connect(BASE_DIR.joinpath('../core/db.sqlite3'))
        cursorsqlite = connsqlite.cursor()
        query_set = self.pedidos_marca()
        # for a in query_set:
        #     if a[3] == '051-2025':
        #         print(a)

        lista_pedidos = []
        tabela = cursorsqlite.execute('SELECT cd_pedido, cliente, nr_pedido_interno, nr_contract, selecao, artigo, dt_pedido, produto, quantidade, quantidade_entregue, dt_programada, fechado, espessura, unidade_medida FROM pedido_pedido ORDER BY nr_contract')
        tb = []
        for ta in tabela:
            
            if ta not in tb:
                tb.append(ta)
        # print(tb)
        # print()
        for obj in query_set:
            obj_filter = list(obj)
            obj_filter[6], obj_filter[8], obj_filter[9] = str(obj_filter[6]), float(obj_filter[8]), str(obj_filter[9])
            lista_pedidos.append(obj_filter)
        cd_list = [obj[0] for obj in tb]
        lista_ped_marca = [obj[0] for obj in lista_pedidos]
        # print(tb)
        if tb:
            cd_pedidos_incluidos = []
            for cd_pedido in lista_pedidos:
                # print(obj_filter[1],obj_filter[5],"OUTO", cd_pedido[2],cd_pedido[10])
                cd_ped = tuple(cd_pedido)
                # print(cd_list)
                # print(len(cd_ped))
                if cd_ped[0] not in cd_list and cd_ped[0] not in cd_pedidos_incluidos:
                    # print(cd_ped)
                    cd_pedidos_incluidos.append(cd_ped[0])
                    if cd_ped[9] == None:
                        cd_ped[9].replace(0)
                    cursorsqlite.executemany("""
                                                INSERT INTO pedido_pedido (cd_pedido, cliente, nr_pedido_interno, nr_contract, selecao, artigo, dt_pedido, produto, quantidade, quantidade_entregue, dt_programada, fechado, espessura, unidade_medida)
                                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                            """, [cd_ped])

                elif cd_ped[0] in cd_list and cd_ped[10] != None:
                    cursorsqlite.execute(""" UPDATE pedido_pedido SET dt_programada = ? WHERE cd_pedido = ? """, (cd_ped[10], cd_ped[0],))
                    # print('Data Programada atualizada {0} !'.format(cd_ped[10]))


            for drop in tb:
                dro = list(drop)
                # print(,  '----', )
                # print(float(dro[8]))
                try:
                    if dro[0] not in lista_ped_marca or float(dro[8]) <= float(dro[9]):
                        # print(dro)
                        cursorsqlite.execute(""" UPDATE pedido_pedido SET fechado = ? WHERE cd_pedido = ? """, (1, dro[0],))
                    # print('Pedido {0} Foi Encerrado !'.format(dro[3]))
                except:
                    continue
        else:
            cursorsqlite.executemany("""
                                    INSERT INTO pedido_pedido (cd_pedido, cliente, nr_pedido_interno, nr_contract, selecao, artigo, dt_pedido, produto, quantidade, quantidade_entregue, dt_programada, fechado, espessura, unidade_medida)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                """, lista_pedidos)
        print("FINALIZANDO...")
        connsqlite.commit()
        cursorsqlite.close

p = SelectPedidos()
p.dbsqlite()

