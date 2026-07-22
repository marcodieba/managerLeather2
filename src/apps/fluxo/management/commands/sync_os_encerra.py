from django.core.management.base import BaseCommand
from src.apps.fluxo.sync_os_encerra import SyncOrdemServico

class Command(BaseCommand):
    help = 'Sincroniza ordens de serviço do Marca_Evolution e encerra requisições locais (abertas)'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('Iniciando sincronização de Ordens de Serviço...'))
        
        sync_tool = SyncOrdemServico()
        resultado = sync_tool.sync_e_encerra_requisicoes()
        
        if resultado.get("sucesso"):
            for log_msg in resultado.get("logs", []):
                self.stdout.write(self.style.SUCCESS(log_msg))
                
            self.stdout.write(self.style.SUCCESS(f'Sincronização concluída! {resultado.get("atualizadas")} requisições encerradas.'))
        else:
            self.stdout.write(self.style.ERROR(f'Erro na sincronização: {resultado.get("erro")}'))
