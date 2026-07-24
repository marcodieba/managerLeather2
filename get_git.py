import subprocess
import json

try:
    result = subprocess.run(['git', 'show', 'HEAD:src/apps/fluxo/views.py'], capture_output=True, text=True, check=True)
    with open('git_views.py', 'w', encoding='utf-8') as f:
        f.write(result.stdout)
    print("Sucesso!")
except Exception as e:
    print(f"Erro: {e}")
