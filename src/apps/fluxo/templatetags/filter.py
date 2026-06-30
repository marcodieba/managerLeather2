# import django_filters
# from .models import Processo, FluxoRequisicao, Requisicao

# class RequisicaoFilter(django_filters.FilterSet):
#     requisicao_id = django_filters.CharFilter(lookup_expr='icontains')

#     class Meta:
#         model = FluxoRequisicao
#         fields = ['id', 'requisicao_id']

from django import template

register = template.Library()

@register.filter
def subtract(value, arg):
    try:
        return value - arg
    except (ValueError, TypeError):
        return ''  # Ou outra manipulação de erro

@register.filter
def percent(value, arg):
    try:
        return (value / arg) * 100
    except (ValueError, TypeError):
        return 'Error'  # Ou outra manipulação de erro

@register.filter
def soma_extras(custos):
    return sum(c.custo_extra for c in custos)


@register.filter(name='divide')
def divide(value, arg):
    """Divide o valor pelo argumento."""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError):
        return ''  # Ou algum outro valor padrão para erros

@register.filter
def somar(value, arg):
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return float(value) if isinstance(value, (int, float)) else 0