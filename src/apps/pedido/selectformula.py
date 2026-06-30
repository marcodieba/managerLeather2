#!/usr/bin/python
# -*- coding: utf-8 -*-

# import pymssql
# 201.182.222.33:3390
# import pyodbc
from datetime import datetime
from decimal import Decimal
from unicodedata import decimal
import pymssql
import re
import sqlite3


class SelectPedidos(object):

    def pedidos_marca(self):
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
        formulas = [37590,
                    37171,
                    36901,
                    36795,
                    37256,
                    37353,
                    36688,
                    37224,
                    37375,
                    37122,
                    37257,
                    37313,
                    37249,
                    37584
                    ]

        for obj in formulas:
            cursor.execute(""" SELECT TOP 100 PERCENT
                                (SELECT SUM(subquery.Vr_Unit)) AS total_soma
                                FROM (
                                    SELECT (SELECT TOP 1 Custo_Medio_Ultimo FROM VwCalc_Custo_PQ_Medio 
                                            WHERE VwCalc_Custo_PQ_Medio.Cd_Produto = Formulacao_Produto.Cd_Produto
                                            AND Formulacao.Cd_Unidade_de_Producao = VwCalc_Custo_PQ_Medio.Cd_Unidade_de_Negocio
                                            ORDER BY Ano_Mes DESC) * Percentual / 100 AS Vr_Unit
                                    FROM
                                        Produto 
                                        RIGHT OUTER JOIN Formulacao_Produto ON  Produto.Codigo = Formulacao_Produto.Cd_Produto 
                                        RIGHT OUTER JOIN Formulacao_Etapa ON Formulacao_Produto.Etapa = Formulacao_Etapa.Etapa  
                                            and  Formulacao_Produto.Cd_Formulacao = Formulacao_Etapa.Cd_Formulacao 
                                        LEFT OUTER JOIN Formulacao  ON Formulacao.Codigo = Formulacao_Etapa.Cd_Formulacao
                                        LEFT OUTER JOIN Formulacao_Grupo ON Formulacao_Grupo.Codigo = Formulacao.Cd_Formulacao_Grupo
                                
                                        WHERE
                                        Formulacao.Codigo = {form}
                                        and   (((convert(numeric(18,5), Formulacao.Peso_Teste / Formulacao.Quantidade_Teste)) 
                                            >= Formulacao_Produto.Pm_Inicial and 
                                            (convert(numeric(18,5), Formulacao.Peso_Teste / Formulacao.Quantidade_Teste)) 
                                            < Formulacao_Produto.Pm_Final) or
                                            Formulacao_Produto.Pm_Inicial IS null or
                                            Formulacao_Produto.Pm_Final IS null)
                                
                                        and   (((convert(numeric(18,5), Formulacao.Peso_Teste / Formulacao.Quantidade_Teste)) 
                                            >= Formulacao_Etapa.Pm_Inicial and 
                                            (convert(numeric(18,5), Formulacao.Peso_Teste / Formulacao.Quantidade_Teste))
                                            < Formulacao_Etapa.Pm_Final) or
                                            Formulacao_Etapa.Pm_Inicial IS null or
                                            Formulacao_Etapa.Pm_Final IS null)
                                ) AS subquery """.format(form=obj))

            # print(str(list(cursor.fetchall())))
            # d = str(list(cursor.fetchone())[0])
            # print(d.replace('.',','))
            

p = SelectPedidos()
p.pedidos_marca()
# p.dbsqlite()
