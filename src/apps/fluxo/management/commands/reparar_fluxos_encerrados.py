from django.core.management.base import BaseCommand
from django.db import transaction

from src.apps.fluxo.models import FluxoRequisicao, Requisicao
from src.apps.fluxo.sync_os_encerra import SyncOrdemServico


class Command(BaseCommand):
    help = (
        "Sincroniza o ERP e corrige fluxos ativos de requisições encerradas, "
        "usando a última saída registrada na Medidora como referência."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Grava as correções. Sem esta opção, apenas simula.",
        )
        parser.add_argument(
            "--skip-sync",
            action="store_true",
            help="Não consulta o ERP antes da análise.",
        )

    def handle(self, *args, **options):
        aplicar = options["apply"]
        ignorar_sync = options["skip_sync"]

        if aplicar and ignorar_sync:
            self.stderr.write(
                self.style.ERROR(
                    "Por segurança, --apply exige a sincronização do ERP. "
                    "Use --skip-sync apenas para simulação."
                )
            )
            return

        if aplicar and not ignorar_sync:
            self.stdout.write("Sincronizando ordens do ERP...")
            resultado_sync = SyncOrdemServico().sync_e_encerra_requisicoes()
            if not resultado_sync.get("sucesso"):
                self.stderr.write(
                    self.style.ERROR(
                        f"Falha na sincronização: {resultado_sync.get('erro')}"
                    )
                )
                return
            self.stdout.write(
                self.style.SUCCESS(
                    f"ERP sincronizado: {resultado_sync.get('atualizadas', 0)} "
                    "requisições atualizadas."
                )
            )
        elif not aplicar and not ignorar_sync:
            self.stdout.write(
                self.style.WARNING(
                    "Simulação: a sincronização do ERP não será executada. "
                    "Use --apply para sincronizar e gravar."
                )
            )

        candidatos = (
            Requisicao.objects.filter(encerrado=True)
            .prefetch_related("fluxos__processo")
            .order_by("id")
        )
        total_candidatos = 0
        total_fluxos = 0
        for requisicao in candidatos:
            fluxos = list(requisicao.fluxos.all())
            ativos = [fluxo for fluxo in fluxos if not fluxo.encerrado]

            if not ativos:
                continue

            data_saida = max(
                (
                    fluxo.dt_saida
                    for fluxo in fluxos
                    if fluxo.encerrado and fluxo.dt_saida
                ),
                default=None,
            )
            if data_saida is None:
                self.stdout.write(
                    f"Req {requisicao.cd_requisicao}: ignorada; "
                    "não há saída histórica para datar a correção."
                )
                continue

            total_candidatos += 1
            total_fluxos += len(ativos)
            self.stdout.write(
                f"Req {requisicao.cd_requisicao}: "
                f"{len(ativos)} fluxo(s) ativo(s) serão zerado(s); "
                f"saída de referência: {data_saida:%d/%m/%Y %H:%M}."
            )

            if aplicar:
                with transaction.atomic():
                    for fluxo in FluxoRequisicao.objects.select_for_update().filter(
                        requisicao=requisicao,
                        encerrado=False,
                    ):
                        fluxo.quantidade = 0
                        fluxo.encerrado = True
                        fluxo.dt_saida = data_saida
                        fluxo.save(
                            update_fields=["quantidade", "encerrado", "dt_saida"]
                        )

        modo = "corrigidos" if aplicar else "encontrados"
        self.stdout.write(
            self.style.SUCCESS(
                        f"{total_candidatos} requisição(ões) {modo}; "
                        f"{total_fluxos} fluxo(s) processado(s)."
            )
        )
