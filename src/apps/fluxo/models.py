from django.db import models
# 🌟 ADICIONE ESTES DOIS IMPORTS NOVOS SE AINDA NÃO ESTIVEREM LÁ EM CIMA:
from django.db.models.signals import pre_save, post_save
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.dispatch import receiver
from datetime import date, datetime, time

# Imports dos seus outros apps
from src.apps.pedido.models import PedidoRequisicao
from src.apps.estoque_pq.models import Produto
import difflib
import qrcode
import base64
from io import BytesIO



# 1. SETORES DA FÁBRICA / MÁQUINAS
class Processo(models.Model):
    nome = models.CharField(('Nome'), max_length=100, null=False, blank=True)
    
    def __str__(self):
        return f"{self.nome}"


# 2. TIPOS DE COURO QUE VOCÊ PRODUZ (Pilar Base)
class Artigo(models.Model):
    nome = models.CharField(('Nome'), max_length=100, null=False, blank=True)
    meta_mes = models.IntegerField(('Meta mês'), null=True, blank=True)

    def __str__(self):
        return f"{self.nome}"


# 3. A "RECEITA" DO ARTIGO (Roteiro Teórico Informativo)
class RoteiroArtigo(models.Model):
    artigo = models.ForeignKey(Artigo, on_delete=models.CASCADE, related_name='roteiros')
    processo = models.ForeignKey(Processo, on_delete=models.CASCADE)
    regulagem = models.CharField(('Regulagem'), max_length=150, null=True, blank=True)
    ordem = models.PositiveIntegerField(('Ordem de Execução'), blank=True, null=True)
    
    class Meta:
        ordering = ['ordem']
        unique_together = ('artigo', 'ordem') # Evita repetir o mesmo processo seguidamente no roteiro
        verbose_name = 'Roteiro do Artigo'
        verbose_name_plural = 'Roteiros dos Artigos'

    def __str__(self):
        return f"{self.ordem}º - {self.processo.nome} ({self.artigo.nome})"


# 4. A SUA ORDEM DE PRODUÇÃO REAL (O Lote)
class Requisicao(models.Model):
    data = models.DateTimeField(('Data do Pedido'), auto_now_add=True)
    cd_requisicao = models.IntegerField(('cd Requisicao'), blank=False, null=False, unique=True)
    artigo = models.CharField(('Artigo'), max_length=100, default=None, null=True, blank=True)
    SETOR = [
                ("Cal", "Caleiro"),
                ("Cur", "Curtimento"),
                ("REC", "Recurtimento"),
                ]
    setor = models.CharField(max_length=3, choices=SETOR, null=True, blank=True)
    
    # 🌟 NOVO CAMPO: O vínculo físico com o Artigo Genérico do menu Artigos
    artigo_padrao = models.ForeignKey(
        Artigo, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='requisicoes_vinculadas',
        verbose_name='Artigo Genérico Vinculado'
    )

    classe = models.CharField(('Classe'), max_length=100, default=None, null=True, blank=True)
    nr_pedido = models.CharField(('Nrº Pedido'), max_length=50, null=True, blank=True)
    espessura = models.CharField(('Espessura'), max_length=100, default=None, null=True, blank=True)
    cor = models.CharField(('Cor'), max_length=100, default=None, null=True, blank=True)
    quantidade = models.BigIntegerField(('Qt.Peças'), null=True, blank=True)
    fulao = models.IntegerField(('Fulão'), null=True, blank=True)
    lote = models.CharField(('Lote'), max_length=15, null=True, blank=True)
    ficha = models.CharField(('Ficha'), max_length=100, default=None, null=True, blank=True)
    qt_mt = models.DecimalField(('Qt. M² WB'), max_digits=20, decimal_places=2, null=True, blank=True)
    dt_requisicao = models.DateTimeField(('Data requisição'), null=True, blank=True)
    modificado = models.DateTimeField(('Modificado em'), auto_now=True)
    encerrado = models.BooleanField(default=False, null=True)
    
    qt = models.BigIntegerField(('Qt'), default=0, null=True, blank=True)
    m2 = models.FloatField(('M²'), default=0, null=True, blank=True)
    # am = models.FloatField(('AM'), default=0, null=True, blank=True)
    # exp_qt = models.BigIntegerField(('Expediçao Qt'), default=0, null=True, blank=True)
    # exp_m2 = models.FloatField(('Expediçao M²'), default=0, null=True, blank=True)
    # exp_am = models.FloatField(('Expediçao AM'), default=0, null=True, blank=True)
    # rend = models.FloatField(('Rendimento'), default=0, null=True, blank=True)
    kg_blue = models.DecimalField(('KG/M² - BLUE'), max_digits=10, decimal_places=2, blank=True, null=True)
    seco = models.DecimalField(('KG/M² - SECO'), max_digits=10, decimal_places=2, blank=True, null=True)
    custo_requisicao_inicial = models.DecimalField(('Custo Kg Inicial'), max_digits=10, decimal_places=2, blank=True, null=True)
    custo_requisicao = models.DecimalField(('Custo Kg Real'), max_digits=10, decimal_places=2, blank=True, null=True)
    rendimento_custo = models.DecimalField(('Rendimento Custo'), max_digits=10, decimal_places=2, blank=True, null=True)
    pallet = models.CharField(('Pallet'), max_length=100, default=None, null=True, blank=True)
    obs = models.TextField(verbose_name="Observação", blank=True, null=True)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        from datetime import date, datetime, time
        
        for campo in ['data', 'dt_requisicao', 'modificado']:
            if hasattr(instance, campo):
                valor = getattr(instance, campo)
                # Se for estritamente uma Data simples, injeta o relógio (00:00:00)
                if type(valor) is date:
                    setattr(instance, campo, datetime.combine(valor, time.min))
        return instance

    def clean(self):
        super().clean()
        links = self.pedido_links.all()

        for link in links:
            pedido = link.pedido
            if not pedido:
                continue

            outras_requisicoes = Requisicao.objects.filter(pedido_links__pedido=pedido).exclude(pk=self.pk)
            total_quantidade = sum(req.quantidade or 0 for req in outras_requisicoes)

            if self.quantidade and (total_quantidade + self.quantidade > pedido.quantidade * 5.1):
                raise ValidationError(
                    f"A quantidade desta requisição ({self.quantidade}) somada às outras já vinculadas ao pedido {pedido.cd_pedido} excede o limite estipulado."
                )

    def get_processo_atual(self):
        """ Retorna o fluxo atual (O OBJETO) da requisição para a view calcular datas. """
        fluxo_ativo = self.fluxos.filter(encerrado=False).order_by('-dt_processo', '-id').first()
        if fluxo_ativo and fluxo_ativo.processo:
            return fluxo_ativo # Devolve o objeto, não apenas a string!
        
        ultimo_fluxo = self.fluxos.order_by('-dt_processo', '-id').first()
        if ultimo_fluxo and ultimo_fluxo.processo:
            return ultimo_fluxo
            
        return "Não definido"

    def get_fluxos_ordenados(self):
        """ Retorna todos os fluxos da requisição, ordenados pela data do processo. """
        return self.fluxos.order_by('dt_processo', 'id')
    
    def get_qrcode_base64(self):
        """ Gera um QR Code 100% offline e retorna como imagem base64 """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=5,
            border=2,
        )
        # Coloca o número da requisição dentro do QR Code
        qr.add_data(str(self.cd_requisicao))
        qr.make(fit=True)

        # Gera a imagem
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Converte a imagem para texto Base64 para ser lida no HTML
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        return f"data:image/png;base64,{img_str}"

    def __str__(self):
        return f"{self.cd_requisicao} - {self.artigo}"
    
    def to_dict(self):
        return {
            'value': self.pk,
            'cd_requisicao': self.cd_requisicao,
            'pedido': self.nr_pedido,
            'artigo': self.artigo,
            'quantidade': self.quantidade,
            'status': self.encerrado, # Status simplificado para true/false
            'dt_requisicao': self.dt_requisicao,
        }



# ----------------------------------------------------------------------------------
# 1. PRE_SAVE: Altera a requisição ANTES dela ir para o banco (Não precisa de .save())
# ----------------------------------------------------------------------------------
@receiver(pre_save, sender=Requisicao)
def antes_de_salvar_requisicao(sender, instance, **kwargs):
    # 1. Puxa os dados do Pedido se a requisição já existir (para edições)
    if instance.pk: 
        link = instance.pedido_links.first()
        if link and instance.classe is None:
            pedido = link.pedido
            instance.classe = pedido.selecao
            instance.artigo = pedido.artigo
            instance.nr_pedido = pedido.nr_contract

    # 2. Vinculação Automática do Artigo Padrão
    if instance.artigo and not instance.artigo_padrao:
        texto_limpo = str(instance.artigo).strip().upper()
        todos_artigos_cadastrados = Artigo.objects.all()
        
        artigo_encontrado = None
        artigos_ordenados = sorted(todos_artigos_cadastrados, key=lambda x: len(x.nome), reverse=True)
        palavras_req = set(texto_limpo.split())

        for a in artigos_ordenados:
            nome_cadastrado = a.nome.strip().upper()
            palavras_cadastrado = set(nome_cadastrado.split())
            
            if nome_cadastrado in texto_limpo or palavras_cadastrado.issubset(palavras_req):
                artigo_encontrado = a
                break
        
        # Se não achou exato, usa similaridade
        if not artigo_encontrado:
            nomes_cadastrados = [a.nome for a in todos_artigos_cadastrados]
            matches = difflib.get_close_matches(instance.artigo, nomes_cadastrados, n=1, cutoff=0.5)
            if matches:
                artigo_encontrado = Artigo.objects.filter(nome=matches[0]).first()

        # Vincula o artigo (Como é pre_save, não precisa do comando instance.save() !)
        if artigo_encontrado:
            instance.artigo_padrao = artigo_encontrado


# ----------------------------------------------------------------------------------
# 2. POST_SAVE: Cria novos objetos (O Fluxo de Recurtimento) DEPOIS de a req existir
# ----------------------------------------------------------------------------------
@receiver(post_save, sender=Requisicao)
def iniciar_fluxo_recurtimento(sender, instance, created, **kwargs):
    """
    Gatilho automático: Sempre que uma NOVA Requisição for criada no sistema,
    ela já entra automaticamente no setor de Recurtimento.
    """
    if created:
        # 1. Procurar o setor de Recurtimento
        processo_recurtimento, _ = Processo.objects.get_or_create(
            nome__icontains='Recurtimento', 
            defaults={'nome': 'Recurtimento'}
        )

        # 2. Define a data de início (Agora vai funcionar porque importamos o timezone)
        data_inicio = instance.dt_requisicao if instance.dt_requisicao else timezone.now().date()

        # 3. Criar o fluxo inicial automático
        FluxoRequisicao.objects.create(
            requisicao=instance,
            processo=processo_recurtimento,
            quantidade=instance.quantidade,
            dt_processo=data_inicio,
            encerrado=False
        )


class Refilo(models.Model):
    requisicao = models.ForeignKey(Requisicao, on_delete=models.CASCADE, related_name='refilos')
    processo = models.ForeignKey(Processo, on_delete=models.SET_NULL, null=True, blank=True)
    qt_refila = models.FloatField(default=0.00, blank=True, null=True)


# 5. O "GPS" (A Rastreabilidade Real em Tempo Real)
class FluxoRequisicao(models.Model):
    requisicao = models.ForeignKey(Requisicao, on_delete=models.CASCADE, related_name='fluxos')
    processo = models.ForeignKey(Processo, on_delete=models.SET_NULL, null=True, blank=True)
    quantidade = models.BigIntegerField(('Qt.Peças'), null=True, blank=True)
    dt_processo = models.DateTimeField(('Data e Hora de Entrada'), null=True, blank=True)
    dt_saida = models.DateTimeField(('Data e Hora de Saída'), null=True, blank=True)
    encerrado = models.BooleanField(('Encerrado neste setor?'), default=False)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        from datetime import date, datetime, time
        
        for campo in ['dt_processo', 'dt_saida']:
            if hasattr(instance, campo):
                valor = getattr(instance, campo)
                # Se for estritamente uma Data simples, injeta o relógio (00:00:00)
                if type(valor) is date:
                    setattr(instance, campo, datetime.combine(valor, time.min))
        return instance
    
    class Meta:
        verbose_name = 'Movimentação da Requisição'
        verbose_name_plural = 'Movimentações da Requisição'
        ordering = ['-dt_processo', '-id']

    def __str__(self):
        nome_processo = self.processo.nome if self.processo else "Desconhecido"
        return f"{self.requisicao.cd_requisicao} em {nome_processo}"


class CustoRequisicao(models.Model):
    requisicao = models.ForeignKey(Requisicao, on_delete=models.CASCADE, related_name='custos')
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='produtos')
    custo = models.DecimalField(('Custo'), default=0.0, max_digits=10, decimal_places=2)
    adicional = models.DecimalField(('Adicional'), max_digits=10, decimal_places=2)
    custo_extra = models.DecimalField(('Custo Extra'), default=0.0, max_digits=10, decimal_places=2)
    am = models.FloatField(('AM'), default=0, null=True, blank=True)
    exp_qt = models.BigIntegerField(('Expediçao Qt'), default=0, null=True, blank=True)
    exp_m2 = models.FloatField(('Expediçao M²'), default=0, null=True, blank=True)
    exp_am = models.FloatField(('Expediçao AM'), default=0, null=True, blank=True)
    rend = models.FloatField(('Rendimento'), default=0, null=True, blank=True)
    data = models.DateTimeField(('Criado em'), auto_now_add=True)


from django.contrib.auth.models import User

class Operador(models.Model):
    # Liga este perfil a um usuário real do Django
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='operador')
    
    # Liga o usuário ao setor onde ele trabalha
    processo = models.ForeignKey(Processo, on_delete=models.RESTRICT, verbose_name="Setor de Trabalho")

    def __str__(self):
        return f"{self.usuario.first_name or self.usuario.username} - {self.processo.nome}"


