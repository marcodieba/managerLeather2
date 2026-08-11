from django.core.management.base import BaseCommand
from src.apps.fluxo.selectrequisicao import SelectRequisicao
import traceback

class Command(BaseCommand):
    help = 'Sincroniza as requisições (similar ao botão na interface)'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando sincronização de requisições...')
        
        try:
            sincronizador = SelectRequisicao()
            sincronizador.post_requisicao()
            self.stdout.write(self.style.SUCCESS('Sincronização concluída com sucesso!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro na sincronização: {str(e)}'))
            traceback.print_exc()
