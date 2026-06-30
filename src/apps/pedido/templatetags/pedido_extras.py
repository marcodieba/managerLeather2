# apps/pedido/templatetags/pedido_extras.py
from django import template
from datetime import date as datetime_date, datetime
import locale

register = template.Library()

# --------------------------------------------------------------------------
# NOVO FILTRO PARA FORMATAÇÃO DE NÚMEROS (substitui o que eu sugeri antes)
# --------------------------------------------------------------------------
@register.filter(name='format_br')
def format_br(value):
    """
    Filtro para formatar um número no padrão pt-BR (ex: 1.234,56).
    Este filtro é mais simples e não depende do `locale`, evitando problemas
    em alguns servidores.
    """
    try:
        # Formata o número com 2 casas decimais e separador de milhar temporário '_'
        formatted_value = f'{float(value):_.2f}'
        # Substitui o separador decimal por vírgula e o de milhar por ponto
        return formatted_value.replace('.', ',').replace('_', '.')
    except (ValueError, TypeError):
        # Se o valor não for um número válido, retorna o próprio valor sem formatar.
        return value

# ==========================================================================
# SEUS FILTROS ORIGINAIS (mantidos sem nenhuma alteração)
# ==========================================================================

@register.filter
def dias_ate_ou_desde(data_alvo_input, data_referencia_input=None):
    """
    Calcula a diferença em dias entre uma data_alvo_input e uma data_referencia_input (padrão: hoje).
    Retorna um número inteiro de dias.
    Positivo se data_alvo_input é no futuro em relação à data_referencia_input.
    Negativo se data_alvo_input é no passado em relação à data_referencia_input.
    Zero se as datas são iguais.
    """
    data_alvo = None
    data_referencia = None

    # Processar data_alvo_input
    if isinstance(data_alvo_input, datetime):
        data_alvo = data_alvo_input.date()
    elif isinstance(data_alvo_input, datetime_date):
        data_alvo = data_alvo_input
    else:
        return "" # Retorna string vazia se data_alvo_input não for um tipo esperado

    # Processar data_referencia_input
    if data_referencia_input is None:
        data_referencia = datetime_date.today()
    elif isinstance(data_referencia_input, datetime):
        data_referencia = data_referencia_input.date()
    elif isinstance(data_referencia_input, datetime_date):
        data_referencia = data_referencia_input
    else:
        # Fallback se data_referencia_input for de tipo inesperado
        data_referencia = datetime_date.today()
        
    if data_alvo is None: # Checagem adicional caso a conversão inicial de data_alvo falhe
        return ""

    delta = data_alvo - data_referencia
    return delta.days

@register.filter
def get_item(dictionary, key):
    """
    Permite acessar um item de dicionário com uma variável como chave no template.
    Uso: {{ my_dictionary|get_item:my_key_variable }}
    """
    return dictionary.get(key)

@register.filter
def soma_qt_mt(requisicao_links):
    return sum(
        link.requisicao.qt_mt or 0
        for link in requisicao_links
        if link.requisicao.qt_mt is not None
    )

@register.filter
def soma_quantidades(pedidos):
    return sum([p.quantidade for p in pedidos if p.quantidade])

@register.filter
def moeda_brasileira(value):
    try:
        locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
    except locale.Error:
        # fallback para não quebrar se locale não estiver disponível
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return locale.currency(value, grouping=True, symbol=False)