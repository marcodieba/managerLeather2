# LeatherManager - Documentação e Pipeline do Projeto

Este documento serve como um mapa geral da arquitetura atual do projeto **LeatherManager**, detalhando como o frontend e o backend estão estruturados, e mantendo um histórico das modificações recentes para garantir que a equipe não se perca durante a evolução do sistema.

---

## 1. Visão Geral da Arquitetura

O LeatherManager é dividido em duas partes principais:
- **Backend:** Desenvolvido em Python/Django (utilizando Django Rest Framework para fornecer a API).
- **Frontend:** Desenvolvido em React + TypeScript, utilizando Vite como empacotador e servidor de desenvolvimento.

### 1.1. Estrutura do Backend (`/src`)
O backend está centralizado na pasta `src/` e é composto pelas seguintes aplicações principais:
- **`core/`**: Configurações centrais do Django (banco de dados, settings, roteamento principal). O banco de dados utilizado atualmente é o SQLite (`db.sqlite3`).
- **`apps/fluxo/`**: Gerencia o fluxo de produção do chão de fábrica (Apontamentos, Requisições, Lotes, Máquinas, Rendimento, etc). Fornece endpoints cruciais para o Dashboard.
- **`apps/pedido/`**: Gerencia os pedidos comerciais, vínculo com os clientes e artigos.
- **`apps/estoque_pq/`**: Controle de estoque e almoxarifado (produtos químicos, etc).

### 1.2. Estrutura do Frontend (`/leathermanager-frontend`)
O frontend está construído como uma Single Page Application (SPA) moderna:
- **`src/components/`**: Componentes de UI reutilizáveis (Tabelas, Gráficos, Alertas).
- **`src/hooks/`**: Lógicas de estado e consumo da API. O arquivo principal aqui é o `useDashboard.ts`, que centraliza toda a lógica de filtragem e cálculo de KPIs do Dashboard.
- **`src/routes/`**: As páginas principais. O `Home.tsx` é a tela inicial onde reside o Dashboard Principal de Produção.
- **`src/types/`**: Definições de tipagem do TypeScript (ex: `Requisicao`, `FluxoRequisicao`).
- **`src/styles/`**: Arquivos de estilização (CSS). O `dashboard.css` controla a aparência visual do painel principal (tema Cyberpunk/Glassmorphism).

---

## 2. Padrões de Desenvolvimento

- **Comunicação Front/Back:** O frontend consome os dados via requisições HTTP (GET/POST/PUT) para a API REST gerada pelo Django (normalmente mapeada no IP local ou porta do backend).
- **Filtragem de Dados do Dashboard:** O backend envia um volume grande de histórico de requisições recentes (`fetchRequisicoesDashboard`) e os filtros (Máquina, Período, Setor, Artigo, Pedido) são processados de forma reativa pelo React no `useDashboard.ts` (client-side), garantindo velocidade ao usuário sem sobrecarregar o banco de dados com múltiplas requisições sequenciais.
- **Integrações (Syncs):** Há scripts rodando no backend para puxar/enviar dados para bancos legados do sistema SQL Server ("Marca_Evolution").

---

## 3. Changelog / Pipeline de Modificações (Histórico)

*Sempre que uma alteração significativa for feita (no frontend ou backend), este histórico deve ser atualizado informando a data e a mudança.*

### [24 de Julho de 2026] - Refatoração do Dashboard Principal
- **Frontend (`Home.tsx` & `useDashboard.ts`):**
  - Implementação da barra de **Filtros Avançados** no Dashboard Principal, permitindo pesquisa cumulativa por: *Período de movimentação, Artigo, Pedido, Lote e Máquina/Processo*.
  - O filtro de *Máquina/Processo* agora exibe de forma precisa o **WIP (Work In Progress)**: ou seja, informa quais lotes estão no chão de fábrica aguardando a próxima etapa (a máquina escolhida) ou que já entraram nela mas ainda não saíram.
  - Correção na lógica de tipagem (`toUpperCase`) dos campos "Pedido" e "Lote" para prevenir erros silenciosos (tela em branco) quando os dados vêm do backend como números puros.
- **Backend / Frontend (Mapeamento de Artigos):**
  - Identificada a necessidade de utilizar o campo correto para filtro de Artigos.
  - Backend (`apps/fluxo/serializers.py`): Adicionado o campo `artigo_generico` no serializador de Requisições, lendo a informação de `artigo_padrao.nome`.
  - Frontend (`types/index.ts` & `useDashboard.ts`): Dashboard atualizado para priorizar o campo `artigo_generico` na lista suspensa (dropdown) e nas pesquisas de Artigo.
- **Acessibilidade UI:**
  - Removida a seleção "laranja" por padrão do filtro de Setores ("Todos"), para evitar confusão visual com os botões de ação ("Atualizar").
- **Documentação:** Criação deste arquivo `PIPELINE.md` para acompanhamento contínuo da saúde do projeto.

### [27 de Julho de 2026] - Refatoração e Limpeza de Rotas do Backend
- **Backend (`core/leatherManager/urls.py`):**
  - Remoção de código severamente duplicado onde os `ViewSets` do DRF (Pedidos, Processos, Requisições, etc.) eram inicializados manualmente (`as_view()`) e mapeados na raiz do projeto, poluindo o *namespace* global. Agora o tráfego de API flui de forma limpa pelo `DefaultRouter` do `apps.fluxo.urls` sob o prefixo `/api/`.
  - Remoção das definições duplicadas das rotas HTML de `ordem-servico/` e `busca/requisicao/` que já estão corretamente tratadas dentro de seus apps correspondentes.
  - A interface de administração do Django (`django-admin`) e as chamadas via `reverse()` não foram afetadas por esta consolidação. O Frontend (React) também permanece intocado, pois já apontava de forma isolada para as rotas corretas (sob `/api/`).

---

> **Aviso para os desenvolvedores e IAs:**
> Ao realizar qualquer nova adição de endpoints, refatoração de UI, criação de tabelas no banco de dados ou integração com o sistema "Marca_Evolution", insira a data e o resumo do que foi feito acima, na seção Changelog.

### [27 de Julho de 2026] - Novos Relatórios Industriais e UX
- **Frontend (Novas Páginas e Melhorias de UX):**
  - Implementação de um fluxo de navegação direta a partir do **Dashboard Principal** para análise profunda de lotes WIP. Adicionados botões de ação na tabela de *Status de Lotes em Processo (WIP)* (arquivo `WipLotesTable.tsx`) para direcionamento rápido (`[Rend.]` e `[€ Custo]`).
  - Criação da página **Relatório de Rendimento** (`RelatorioRendimento.tsx`), acessível via `ids` na query string, apresentando tabelas analíticas de lead time e perda de processos por lote de forma responsiva.
  - Criação da página **Custo de Produção** (`CustoProducao.tsx`), focada em análise financeira (Capital Empatado / WIP Financeiro) e baseada no campo `custo_requisicao`.
  - Atualização do `main.tsx` e `Navbar/index.tsx` para integrar perfeitamente os novos links e rotas na estrutura React-Router.
  - Atualização do hook `useDashboard.ts` (estado `LoteWipStat`) para agrupar as referências de requisição `requisicoesIds`, permitindo a transição fluída entre o lote visualizado no dashboard e as requisições enviadas ao backend nas novas rotas de relatório.
