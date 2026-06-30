from django import forms
from .models import Requisicao  # Importe o seu model Requisicao

class RequisicaoForm(forms.ModelForm):
    class Meta:
        model = Requisicao
        fields = "__all__"
    
# class RequisicaoForm(forms.ModelForm):
#     pedidos_existentes = forms.ModelMultipleChoiceField(
#         queryset=Pedido.objects.filter(requisicao__isnull=True),
#         required=False,
#         widget=forms.SelectMultiple(attrs={'size': 10}),
#         label="Pedidos existentes para vincular"
#     )

#     class Meta:
#         model = Requisicao
#         fields = '__all__'

#     def __init__(self, *args, **kwargs):
#         super(RequisicaoForm, self).__init__(*args, **kwargs)
#         if self.instance.pk:
#             # Inclui os pedidos já vinculados, para exibição no formulário
#             self.fields['pedidos_existentes'].queryset = Pedido.objects.filter(
#                 models.Q(requisicao__isnull=True) | models.Q(requisicao=self.instance)
#             )
#             self.fields['pedidos_existentes'].initial = self.instance.pedidos.all()

#     def save(self, commit=True):
#         instance = super().save(commit)
#         if commit:
#             self.cleaned_data.get('pedidos_existentes').update(requisicao=instance)
#         return instance
