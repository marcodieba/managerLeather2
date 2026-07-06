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


from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

date_now = datetime.datetime.now()
# .strftime('%Y-%m-%d %H:%M:%S')
print(date_now)
class SelectRequisicao(object):

    def requisicao_sea(self):
        server = 'tcp:192.168.20.250'
        database = 'Marca_Evolution'
        username = 'sa'
        password = 'CR@R2018c'
        # cnxn = pyodbc.connect('DRIVER={ODBC Driver 13 for SQL
        # Server};SERVER='+server+';DATABASE='+database+';UID='+username+';PWD='+ password)

        con = pymssql.connect(host='192.168.20.250',
                              port='1433',
                              user='sa',
                              password='CR@R2018c',
                              database='Marca_Evolution'
                              )

        cursor = con.cursor()
        # for obj in formulas:
        cursor.execute(""" SELECT 
                                Pedido_Comercial_Artigo_Programacao.Marca_no_Couro, 
                                isnull(Quantidade_WB,Quantidade_SA) as Quantidade_WB, 
                                isnull(Pes2_M2_WB,Pes2_M2_SA) as Pes2_M2_WB, 
                                Case when isnull(Quantidade_WB,Quantidade_SA) > 0 then convert(Numeric(18,2),isnull(Pes2_M2_WB,Pes2_M2_SA) / isnull(Quantidade_WB,Quantidade_SA)) else Null end as Media_WB,
                                isnull(Qt_Expedicao,0) as Quantidade_Exp, 
                                --isnull(Pedido_Comercial_Artigo_Programacao.Quantidade_Exp,0) 
                                isnull((Select SUM(EES.Qt_Expedicao) FROM Estoque_Expedicao_SeA EES Where EES.Cd_Pedido_Comercial_Movimento_OS = Pedido_Comercial_Artigo_Programacao.Codigo 
                                and
                                ((EES.Dt_Expedicao >= Convert(datetime,'01/04/2025')
                                and EES.Dt_Expedicao <= Convert(datetime, '09/04/2025')) or EES.Dt_Expedicao is null)
                                ),0) as Qt_Exp_Tot,

                                Estoque_Expedicao_SeA.M2_Pes2 as Pes2_M2_Exp ,

                                Case when Qt_Expedicao > 0 then convert(Numeric(18,2),Pedido_Comercial_Artigo_Programacao.Pes2_M2_Exp / Qt_Expedicao) else Null end as Media_Exp,

                                Nr_Item_Pedido,
                                Sea_Artigo.Nome + rtrim(' ' + isnull(Sea_Artigo_Cor.Nome,'')) + rtrim(' ' + isnull(WB_Sea_Espessura.Nome,'')) + ' ' + Classificacao as Artigo,

                                Case when Produto_Unidade.Nome_Resumido = 'M2' then
                                Pedido_Comercial_Artigo.Quantidade * 10.764 else Pedido_Comercial_Artigo.Quantidade end as Quantidade_Pedido_Pes2,

                                Pedido_Tipo.Nome as Pedido_Tipo,
                                Dt_Pedido,

                                Dt_Expedicao as Dt_Expedicao,
                                case when  isnull(Quantidade_WB,Quantidade_SA) is null then '1-WB' else case when Dt_Expedicao is null then '2-PROD.' else case when Quantidade_SA is null then '3-EXP.' else '4-SA_EXP' end end end Wb_Prod_Expedido,
                                isnull((Select SUM(Qt_Expedicao) FROM Estoque_Expedicao_SeA EES Where EES.Cd_Pedido_Comercial_Movimento_OS = Pedido_Comercial_Artigo_Programacao.Codigo),0) as Qt_Tot_Exp,
                                isnull((Select Count(*) FROM Estoque_Expedicao_SeA EES Where EES.Cd_Pedido_Comercial_Movimento_OS = Pedido_Comercial_Artigo_Programacao.Codigo),0) as Qt_Tot_Exp_It,

                                case when A.Unid_em_Couro = 1 then 'INTEIRO' else 'MEIO' end as Int_Meio

                                FROM Pedido_Comercial_Artigo_Programacao 
                                INNER JOIN Pedido_Comercial_Artigo ON Pedido_Comercial_Artigo_Programacao.Cd_Pedido_Comercial_Artigo = Pedido_Comercial_Artigo.Codigo
                                INNER JOIN Pedido_Comercial ON Pedido_Comercial.Codigo = Pedido_Comercial_Artigo.Cd_Pedido_Comercial
                                INNER JOIN Fornecedor_Cliente_CNPJ ON Fornecedor_Cliente_CNPJ.Codigo = Pedido_Comercial.Cd_Cliente_CNPJ
                                INNER JOIN Pedido_Tipo ON Pedido_Tipo.Codigo = Pedido_Comercial.Cd_Pedido_Tipo
                                INNER JOIN Cidade ON Cidade.Codigo = Fornecedor_Cliente_CNPJ.Cd_Cidade
                                INNER JOIn Pais ON Pais.Codigo = Fornecedor_Cliente_CNPJ.Cd_Pais
                                LEFT OUTER JOIN Sea_Artigo ON Sea_Artigo.Codigo = Pedido_Comercial_Artigo.Cd_Sea_Artigo
                                LEFT OUTER JOIN Sea_Artigo_Cor ON Sea_Artigo_Cor.Codigo = Pedido_Comercial_Artigo.Cd_Sea_Artigo_Cor
                                LEFT OUTER JOIN WB_Sea_Espessura ON WB_Sea_Espessura.Codigo = Pedido_Comercial_Artigo.Cd_Sea_Espessura_Final
                                LEFT OUTER JOIN Produto_Unidade ON Produto_Unidade.Codigo = Pedido_Comercial_Artigo.Cd_Produto_Unidade
                                LEFT OUTER JOIN Estoque_Expedicao_SeA ON Cd_Pedido_Comercial_Movimento_OS = Pedido_Comercial_Artigo_Programacao.Codigo
                                LEFT OUTER JOIN Fornecedor_Cliente Representante On Representante.Codigo = isnull(Pedido_Comercial.Cd_Representante,Fornecedor_Cliente_CNPJ.Cd_Representante)
                                LEFT OUTER JOIN Estoque_Expedicao EE on EE.Cd_Pedido_Comercial_artigo_Programacao = Pedido_Comercial_Artigo_Programacao.Codigo
                                LEFT OUTER JOIN WB_Artigo A on A.Codigo = EE.Cd_WB_Artigo
                                WHERE 
                                ((Dt_Expedicao >= Convert(datetime,'01/04/2025')
                                and Dt_Expedicao <= Convert(datetime,'08/04/2025')) or Dt_Expedicao is null)
                                and 
                                Pedido_Comercial_Artigo_Programacao.Cd_Unidade_de_Producao = 1

                                and Pedido_Comercial_Artigo_Programacao.Marca_no_Couro = 'AL*269'
                            """#.format(form=obj)
                            )

        # print(str(list(cursor.fetchall())))
        return cursor.fetchall()
            # d = str(list(cursor.fetchone())[0])
            # print(d.replace('.',','))
    
    def post_requisicao(self):
        connsqlite = sqlite3.connect(BASE_DIR.joinpath('../core/db.sqlite3'))
        cursorsqlite = connsqlite.cursor()
        query_set = self.requisicao_sea()
        # lista_requisicao = []
        # print(query_set)
        for cd_req in query_set:
            # data = cd_req[1].strftime('%d-%m-%Y %H:%M:%S')
            req_date = [date_now, cd_req[0], cd_req[1].strftime('%Y-%m-%d %H:%M:%S'), cd_req[2], cd_req[3], cd_req[4], date_now, 0]
            requisicao = cursorsqlite.execute("""
                                            SELECT cd_requisicao, artigo, dt_requisicao, lote, quantidade, qt_entregue 
                                            FROM fluxo_requisicao 
                                            WHERE cd_requisicao = ? 
                                            """, (cd_req[0],))
            if requisicao.fetchone() == None:
                cursorsqlite.executemany("""
                                            INSERT INTO fluxo_requisicao (data, cd_requisicao, dt_requisicao, lote, artigo, quantidade, modificado, encerrado)
                                            VALUES (?,?,?,?,?,?,?,?)
                                        """, (req_date,))
            else:
                print("Requisicoes Atualizadas")

            connsqlite.commit()
            cursorsqlite.close  

p = SelectRequisicao()
# p.requisicao_sea()
p.post_requisicao()
