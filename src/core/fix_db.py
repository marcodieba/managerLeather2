import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'db.sqlite3')

if not os.path.exists(db_path):
    print("Erro: db.sqlite3 não encontrado na raiz do projeto.")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

try:
    print("Iniciando varredura por dados corrompidos no SQLite...")
    
    # Imprime quais linhas estão corrompidas para o usuário saber
    c.execute("SELECT id, cd_requisicao, quantidade, fulao FROM fluxo_requisicao WHERE typeof(cd_requisicao) = 'text' OR typeof(quantidade) = 'text' OR typeof(fulao) = 'text'")
    corrompidos = c.fetchall()
    for row in corrompidos:
        print(f"ATENÇÃO: Requisicao ID {row[0]} possui colunas corrompidas: cd_req='{row[1]}', qt='{row[2]}', fulao='{row[3]}'")

    # Corrige preservando a linha! 
    # Para cd_requisicao, usamos 100000000 + ID para garantir que seja UNIQUE e não dê erro!
    c.execute("UPDATE fluxo_requisicao SET cd_requisicao = 100000000 + id WHERE typeof(cd_requisicao) = 'text';")
    c.execute("UPDATE fluxo_requisicao SET quantidade = 0 WHERE typeof(quantidade) = 'text';")
    c.execute("UPDATE fluxo_requisicao SET fulao = 0 WHERE typeof(fulao) = 'text';")
    
    # Corrige tabela de Fluxo
    c.execute("UPDATE fluxo_fluxorequisicao SET quantidade = 0 WHERE typeof(quantidade) = 'text';")
    c.execute("UPDATE fluxo_fluxorequisicao SET processo_id = NULL WHERE typeof(processo_id) = 'text';")
    
    conn.commit()
    print("Limpeza concluída com sucesso! Os registros corrompidos foram resetados.")
except Exception as e:
    print(f"Ocorreu um erro: {e}")
finally:
    conn.close()
