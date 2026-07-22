#!/usr/bin/python
# -*- coding: utf-8 -*-

import datetime
from decimal import Decimal
import pymssql
import decimal

from pathlib import Path
from src.apps.estoque_pq.models import Produto, ConsumoProduto
from src.apps.fluxo.models import Requisicao, CustoRequisicao

BASE_DIR = Path(__file__).resolve().parent.parent

date_now = datetime.datetime.now()


def custo_requisicao(*args):

    con = pymssql.connect(
        host='192.168.20.250',
        port='1433',
        user='sa',
        password='CR@R2018c',
        database='Marca_Evolution'
    )

    cursor = con.cursor()

    # ==============================
    # 🔥 CORREÇÃO DEFINITIVA DOS IDS
    # ==============================
    objetos = args[0] if args else []

    # caso: ['1,2,3']
    if isinstance(objetos, list) and len(objetos) == 1 and isinstance(objetos[0], str):
        if "," in objetos[0]:
            objetos = objetos[0].split(",")

    # caso: "1,2,3"
    elif isinstance(objetos, str):
        objetos = objetos.split(",")

    # garante lista
    if not isinstance(objetos, (list, tuple)):
        objetos = [objetos]

    print("OBJETOS:", objetos)

    for obj in objetos:

        obj = str(obj).strip()

        if not obj.isdigit():
            print(f"⚠️ ID inválido: {obj}")
            continue

        cursor.execute(f"""
            SELECT
                fp.Codigo,
                fp.Cd_Produto,
                p.Nome AS Produto,
                r.Peso,
                fp.Percentual,
                ISNULL(f.Acrescimo_Peso_Perc, 0) AS Acrescimo_Peso_Perc,
                (
                    SELECT TOP 1 Custo_Medio_Ultimo
                    FROM VwCalc_Custo_PQ_Medio
                    WHERE VwCalc_Custo_PQ_Medio.Cd_Produto = fp.Cd_Produto
                    AND f.Cd_Unidade_de_Producao = VwCalc_Custo_PQ_Medio.Cd_Unidade_de_Negocio
                    ORDER BY Ano_Mes DESC
                ) AS Vr_Unit,
                (r.Peso * (fp.Percentual + ISNULL(f.Acrescimo_Peso_Perc, 0)) / 100) AS Qt_Consumida,
                (r.Peso * (fp.Percentual + ISNULL(f.Acrescimo_Peso_Perc, 0)) / 100) * (
                    SELECT TOP 1 Custo_Medio_Ultimo
                    FROM VwCalc_Custo_PQ_Medio
                    WHERE VwCalc_Custo_PQ_Medio.Cd_Produto = fp.Cd_Produto
                    AND f.Cd_Unidade_de_Producao = VwCalc_Custo_PQ_Medio.Cd_Unidade_de_Negocio
                    ORDER BY Ano_Mes DESC
                ) AS Custo_Total,
                r.Fulao,
                r.Pecas,
                r.Codigo AS Cd_Requisicao,
                f.Codigo AS Cd_Formulacao,
                f.Nome AS Formulacao
            FROM Produto p
            RIGHT OUTER JOIN Formulacao_Produto fp ON p.Codigo = fp.Cd_Produto
            RIGHT OUTER JOIN Formulacao_Etapa fe ON fp.Etapa = fe.Etapa
                AND fp.Cd_Formulacao = fe.Cd_Formulacao
            LEFT OUTER JOIN Formulacao f ON f.Codigo = fe.Cd_Formulacao
            LEFT OUTER JOIN Requisicao r ON r.Cd_Formulacao = f.Codigo
            WHERE r.Codigo = {obj}
            AND (
                (
                    CONVERT(NUMERIC(18, 5), r.Peso / CASE WHEN r.Pecas = 0 THEN 1 ELSE r.Pecas END) >= fp.Pm_Inicial
                    AND CONVERT(NUMERIC(18, 5), r.Peso / CASE WHEN r.Pecas = 0 THEN 1 ELSE r.Pecas END) < fp.Pm_Final
                )
                OR fp.Pm_Inicial IS NULL
                OR fp.Pm_Final IS NULL
            )
            AND (
                (
                    CONVERT(NUMERIC(18, 5), r.Peso / CASE WHEN r.Pecas = 0 THEN 1 ELSE r.Pecas END) >= fe.Pm_Inicial
                    AND CONVERT(NUMERIC(18, 5), r.Peso / CASE WHEN r.Pecas = 0 THEN 1 ELSE r.Pecas END) < fe.Pm_Final
                )
                OR fe.Pm_Inicial IS NULL
                OR fe.Pm_Final IS NULL
            )
            AND p.Nome NOT LIKE 'agua%'
            ORDER BY fp.Etapa, fp.Ordem_Sequencial, p.Nome
        """)

        row = cursor.fetchall()

        if not row:
            print(f"⚠️ Nenhum dado encontrado para requisição {obj}")
            continue

        requisicoes = Requisicao.objects.filter(cd_requisicao=obj)

        if not requisicoes.exists():
            print(f"⚠️ Requisição {obj} não existe no Django")
            continue

        custo_adicional_lista = []
        custo_original = []
        produto_lista = []

        for item in row:

            cd_produto = item[1]
            nome_produto = item[2]
            
            # Salva o Custo Total do produto na lista para calcular o valor base da requisição depois
            custo_original.append(item[8] or 0)

            produto, _ = Produto.objects.get_or_create(
                cd_produto=cd_produto,
                defaults={
                    "produto": nome_produto,
                    "quantidade": 0,
                    "estoque_anterior": 0,
                    "contagem_fisica": 0,
                    "em_transito": 0,
                    "percentual": 0,
                    "ultimo_valor": item[6] or 0,
                }
            )

            # atualiza nome se mudou
            if produto.produto != nome_produto:
                produto.produto = nome_produto
                produto.save(update_fields=["produto"])

            # =========================
            # 🔥 SALVA CONSUMO AUTOMÁTICO
            # =========================

            ConsumoProduto.objects.update_or_create(
                                    produto=produto,
                                    cd_requisicao=item[11],
                                    percentual=item[4],  # evita duplicar mesma fórmula

                                    defaults={
                                        "peso": item[3] or 0,
                                        "acrescimo": item[5] or 0,
                                        "quantidade_consumida": item[7] or 0,
                                        "custo_unitario": item[6] or 0,
                                        "custo_total": item[8] or 0,
                                    }
                                )
            
            for req in requisicoes:
                for adicional in req.custos.all():

                    if item[2] == str(adicional.produto) and str(adicional.produto) not in produto_lista:

                        custo_real = float(round(
                            (decimal.Decimal(adicional.adicional or 0) / 100) * decimal.Decimal(item[6] or 0),
                            2
                        ))

                        custo_adicional_lista.append(custo_real)
                        produto_lista.append(str(adicional.produto))

                        req.custos.filter(produto__produto=item[2]).update(
                            custo=round(item[8] or 0, 2),
                            custo_extra=custo_real
                        )

        total_custo = round(float(sum(custo_original)), 2)
        peso = float(row[0][3] or 0)

        if peso > 0 and total_custo > 0:
            custo_kg = total_custo / peso
        else:
            custo_kg = total_custo

        print("CUSTO KG:", custo_kg)

        # Calcula o Custo Real por M² (se a requisição já tiver expedido os metros)
        req = Requisicao.objects.filter(cd_requisicao=obj).first()
        m2_final = float(req.m2 or 0) if req else 0
        qt_final = float(req.qt or 0) if req else 0

        # Cálculos de Área Média
        am_entrada = (float(req.qt_mt or 0) / float(req.quantidade)) if req and req.quantidade and req.quantidade > 0 else 0
        exp_am_saida = (m2_final / qt_final) if qt_final > 0 else 0

        custo_real_total = total_custo + float(sum(custo_adicional_lista))
        custo_por_m2 = (custo_real_total / m2_final) if m2_final > 0 else 0

        Requisicao.objects.filter(cd_requisicao=obj).update(
            custo_requisicao_inicial=(total_custo / peso if peso > 0 else 0),
            custo_requisicao=custo_kg + float(sum(custo_adicional_lista)),
            rendimento_custo=custo_por_m2,
            exp_m2=m2_final,
            exp_qt=qt_final,
            am=am_entrada,
            exp_am=exp_am_saida,
            rend=(m2_final / peso) if (peso > 0 and m2_final > 0) else 0
        )
        
        # Calcular M² Proporcional para Justificativas Dinâmicas
        if req:
            justificativas = req.justificativas_registadas.all()
            total_justificado = sum(j.quantidade for j in justificativas)
            if total_justificado > 0 and m2_final > 0:
                for j in justificativas:
                    # M2 proporcional = (Qt da justificativa / Qt Total) * M2 Final
                    j.m2_proporcional = (j.quantidade / total_justificado) * m2_final
                    j.save(update_fields=['m2_proporcional'])

        print(f'custo extra: {total_custo}')
        print(f'custo real: {total_custo + float(sum(custo_adicional_lista))}')

        # ==============================
        # BLOCO ORIGINAL DE PRODUTOS
        # ==============================
        lista_lote = []

        for item in row:

            cd_produto = item[1]
            nome_produto = item[2]

            produto, _ = Produto.objects.get_or_create(
                cd_produto=cd_produto,
                defaults={
                    "produto": nome_produto,
                    "quantidade": 0,
                    "estoque_anterior": 0,
                    "contagem_fisica": 0,
                    "em_transito": 0,
                    "percentual": 0,
                    "consumo_diario": 0,
                    "ultimo_valor": 0
                }
            )

            custo = item[8] or 0
            adicional = item[6] or 0
            custo_real = round(item[5] or 0, 2)
            exp_am = (item[5] / item[4]) if item[4] else 0

            # Cria ou atualiza o custo para a requisicao correta e o produto correto
            for req in requisicoes:
                # Calcula o rendimento real (M² / Peso Inicial) se os dados já existirem (da OS encerrada)
                peso_inicial = item[3] or 0
                m2_real = float(req.m2 or 0)
                rendimento_real = (m2_real / float(peso_inicial)) if (peso_inicial > 0 and m2_real > 0) else 0

                CustoRequisicao.objects.update_or_create(
                    requisicao=req,
                    produto=produto,
                    defaults={
                        'custo': custo,
                        'adicional': adicional,
                        'custo_extra': custo_real,
                        'exp_am': exp_am,
                        'exp_m2': m2_real,
                        'exp_qt': req.qt or 0,
                        'rend': rendimento_real
                    }
                )

            lista_lote.append(item)

    con.close()