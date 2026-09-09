from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from .models import Operador, Processo, Requisicao, MovimentacaoProducao, QualidadeMovimentacao
from .views import ler_qrcode_movimentacao


class MovimentacaoQRCodeTests(TestCase):
    def setUp(self):
        self.processo = Processo.objects.create(nome='Teste')
        self.user = User.objects.create_user('operador', password='senha')
        self.operador = Operador.objects.create(usuario=self.user)
        self.operador.processos.add(self.processo)
        self.requisicao = Requisicao.objects.create(cd_requisicao=900001, quantidade=10, lote='L-P')
        self.factory = APIRequestFactory()

    def _post(self, payload, **headers):
        request = self.factory.post(
            reverse('ler_qrcode'), payload, format='json', **headers
        )
        return ler_qrcode_movimentacao(request)

    def test_chave_operacao_eh_idempotente(self):
        payload = {
            'cd_requisicao': self.requisicao.cd_requisicao,
            'operador_id': self.operador.id,
            'processo_id': self.processo.id,
            'quantidade': 2,
            'chave_operacao': 'op-teste-1',
        }
        primeira = self._post(payload)
        segunda = self._post(payload)
        self.assertTrue(primeira.data['sucesso'])
        self.assertTrue(segunda.data['duplicada'])
        self.assertEqual(MovimentacaoProducao.objects.count(), 1)

    def test_status_nao_aprovado_exige_autorizacao(self):
        payload = {
            'cd_requisicao': self.requisicao.cd_requisicao,
            'operador_id': self.operador.id,
            'processo_id': self.processo.id,
            'quantidade': 1,
            'status_qualidade': 'REFUGO',
            'justificativa_qualidade': 'Defeito visual confirmado',
        }
        resposta = self._post(payload)
        self.assertEqual(resposta.status_code, 401)
        self.assertFalse(QualidadeMovimentacao.objects.exists())

    def test_fluxo_bloqueado_nao_pode_ser_movimentado_sem_liberacao(self):
        supervisor = User.objects.create_user(
            'supervisor', password='senha-supervisor', is_staff=True
        )
        payload = {
            'cd_requisicao': self.requisicao.cd_requisicao,
            'operador_id': self.operador.id,
            'processo_id': self.processo.id,
            'quantidade': 2,
            'status_qualidade': 'BLOQUEADO',
            'justificativa_qualidade': 'Aguardando inspeção',
            'supervisor_username': supervisor.username,
            'supervisor_password': 'senha-supervisor',
        }
        self.assertEqual(self._post(payload).status_code, 200)

        outro_processo = Processo.objects.create(nome='Outro processo')
        self.operador.processos.add(outro_processo)
        payload.update({
            'processo_id': outro_processo.id,
            'quantidade': 1,
            'chave_operacao': 'bloqueio-2',
        })
        resposta = self._post(payload)
        self.assertEqual(resposta.status_code, 409)
        self.assertTrue(resposta.data['qualidade_bloqueada'])
