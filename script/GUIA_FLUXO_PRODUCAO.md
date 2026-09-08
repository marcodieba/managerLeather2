# Guia de operação do fluxo de produção

## Objetivo

Registrar o caminho real de cada requisição, mantendo a quantidade correta em
cada processo e permitindo que a Medidora informe exatamente quantos couros
foram recebidos e qual foi a classificação.

## 1. Antes de iniciar

1. Confirme o código da requisição, lote, artigo e quantidade total.
2. Confirme que o operador está vinculado ao processo correto.
3. Verifique se a quantidade física recebida corresponde ao saldo disponível.
4. Não reutilize uma requisição para outro lote sem autorização do responsável.

## 2. Início de cada processo

Cada processo deve ser iniciado pelo operador no momento em que os couros
entram fisicamente na máquina ou setor:

1. Abra o leitor de movimentação.
2. Bipe o QR Code da requisição.
3. Confira o processo exibido.
4. Informe a quantidade realmente recebida.
5. Registre a entrada.

O registro deve ser feito mesmo quando a quantidade for parcial. Por exemplo,
se a requisição tem 211 couros e o processo recebeu 100, registre 100, nunca
211.

O sistema encerra o registro do processo anterior somente quando a quantidade
é transferida. Isso preserva o histórico de onde cada parte do lote esteve.

## 3. Transferências parciais

Quando apenas parte do lote avançar:

- informe somente a quantidade que avançou;
- deixe o saldo restante no processo anterior;
- selecione o motivo correto quando houver perda, reprocesso ou separação;
- não lance novamente uma quantidade que já está aberta em outro processo.

Exemplo:

| Situação | Lançamento correto |
|---|---:|
| Requisição total | 211 |
| Primeira transferência | 100 |
| Saldo restante | 111 |
| Nova transferência | somente a quantidade efetivamente recebida |

## 4. Operação da Medidora

A Medidora é o ponto de conferência física e de classificação:

1. Bipe a requisição ao receber os couros.
2. Conte os couros fisicamente.
3. Informe somente a quantidade recebida naquele momento.
4. Selecione a classificação correta.
5. Salve a movimentação.
6. Confira se a quantidade e a classificação aparecem no histórico.

Se a Medidora receber 84 couros de uma requisição de 85, registre **84**.
Se houver recebimento acima do saldo indicado, o sistema deve bloquear o
lançamento e exigir motivo, usuário/senha de supervisor e justificativa. Não
repita o lançamento para “fechar” a diferença: faça um novo registro somente
quando os couros restantes forem realmente recebidos. Continue acumulando os
recebimentos reais e a classificação de cada entrada até totalizar a
quantidade física da requisição.

As classificações individuais de acabamento, como PISTOLA, TOP, VACUO,
TINGIMENTO e outras, continuam sendo registradas pelo nome real do processo.
Nos relatórios agrupados, elas podem aparecer somadas como **ACABAMENTO**.

## 5. Conferência após o lançamento

O operador deve verificar:

- quantidade lançada;
- processo de destino;
- classificação selecionada;
- operador identificado;
- existência de saldo restante;
- indicação de processo atual no histórico.

Se houver divergência, pare o próximo lançamento e comunique a supervisão.

## 6. Encerramento da requisição

O encerramento total da requisição é diferente do encerramento de uma etapa:

- **Etapa encerrada:** o lote saiu daquele processo.
- **Requisição encerrada:** o ERP informou `Cd_Sea_Posicao_OS = 7`.

A requisição pode ser encerrada pelo ERP na posição 7 mesmo que ainda não haja
registro na Medidora. A Medidora controla a quantidade e a classificação
recebidas; a posição 7 controla o encerramento administrativo da OS.

Se `Cd_Sea_Posicao_OS` for diferente de 7, a requisição deve permanecer aberta.

## 7. O que não fazer

- Não lançar a quantidade total quando somente parte foi recebida.
- Não duplicar uma entrada já registrada.
- Não marcar uma classificação diferente da observada fisicamente.
- Não iniciar um processo sem conferir o QR Code e a quantidade.
- Não usar autorização de supervisor para ultrapassar o total físico sem
  justificativa e conferência.
- Não confundir o check de uma etapa encerrada com o encerramento total da
  requisição.

## 8. Correção de divergências

Ao encontrar quantidade ou processo incorreto:

1. Não faça novos lançamentos para compensar o erro.
2. Anote a requisição, processo, quantidade correta e operador.
3. Informe a supervisão.
4. Registre a justificativa da correção.
5. Confirme novamente o histórico após o ajuste.

Correções em lote devem ser feitas somente após conferência do ERP e do
histórico da Medidora. Antes de aplicar qualquer comando de manutenção, execute
primeiro sua simulação e revise os registros listados.

## Tutorial visual

O roteiro em formato de desenho animado está em
`script/tutorial_fluxo_animado.html`. Abra o arquivo no navegador para avançar
pelas cenas de conferência, transferência parcial, autorização, Medidora,
totalização e encerramento pelo ERP.
