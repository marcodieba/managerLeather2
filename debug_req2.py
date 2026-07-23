import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.core.leatherManager.settings")
django.setup()

from src.apps.fluxo.models import Requisicao, FluxoRequisicao

def debug_info(cd_requisicao, processo_id):
    print(f"\n--- Debugging Requisicao {cd_requisicao} on Process {processo_id} ---")
    req = Requisicao.objects.get(cd_requisicao=cd_requisicao)
    
    print("Fluxos History:")
    for f in req.fluxos.all().order_by('id'):
        print(f"  ID:{f.id} Proc:{f.processo_id} Qtd:{f.quantidade} Encerrado:{f.encerrado}")
        
    ultimo_fluxo_diferente = req.fluxos.exclude(processo_id=processo_id).order_by('-id').first()
    
    if ultimo_fluxo_diferente:
        processo_anterior_id = ultimo_fluxo_diferente.processo_id
        qtd_anterior = sum((f.quantidade or 0) for f in req.fluxos.filter(processo_id=processo_anterior_id))
        print(f"  processo_anterior_id: {processo_anterior_id}, qtd_anterior: {qtd_anterior}")
    else:
        qtd_anterior = float(req.quantidade or req.qt or 0)
        print(f"  No previous process. qtd_anterior: {qtd_anterior}")
        
    qtd_atual = sum((f.quantidade or 0) for f in req.fluxos.filter(processo_id=processo_id))
    print(f"  qtd_atual (in process {processo_id}): {qtd_atual}")
    
    qtd_sugerida = qtd_anterior - qtd_atual
    if qtd_sugerida < 0:
        qtd_sugerida = 0
        
    print(f"  => qtd_sugerida = {qtd_sugerida}")

    print("\nAlternative approach (total available logic):")
    fluxos_para_consumir = list(req.fluxos.filter(encerrado=False).order_by('dt_processo', 'id'))
    total_disponivel = sum(f.quantidade for f in fluxos_para_consumir if f.quantidade)
    print(f"  total_disponivel (encerrado=False): {total_disponivel}")
    print("  Fluxos abertos:")
    for f in fluxos_para_consumir:
        print(f"    ID:{f.id} Proc:{f.processo_id} Qtd:{f.quantidade}")

try:
    # Just grab any requisicao with fluxos to test
    req = Requisicao.objects.filter(fluxos__isnull=False).first()
    if req:
        # get the last flux process to simulate scanning it again
        last_flux = req.fluxos.order_by('-id').first()
        debug_info(req.cd_requisicao, last_flux.processo_id)
except Exception as e:
    print("Error:", e)
