# DS - PLANNERX — Deploy Vercel

Este repositório contém somente os arquivos necessários para publicar o DS - PLANNERX na Vercel.

## Serviços necessários

- Vercel
- Postgres/Neon conectado ao projeto
- Vercel Blob público

## Variáveis de ambiente

Cadastre na Vercel:

```env
DATABASE_URL=...
BLOB_READ_WRITE_TOKEN=...
SESSION_SECRET=...
PLANNERX_USERNAME=...
PLANNERX_PASSWORD=...
PLANNERX_TIMEZONE=America/Sao_Paulo
```

`DATABASE_URL` e `BLOB_READ_WRITE_TOKEN` normalmente são criadas ao conectar os serviços de armazenamento ao projeto.

## Publicação

1. Envie estes arquivos para a raiz de um repositório no GitHub.
2. Importe o repositório na Vercel.
3. Conecte o Postgres/Neon e o Vercel Blob.
4. Cadastre as variáveis de ambiente.
5. Faça o deploy ou redeploy.

Não envie arquivos `.env`, bancos SQLite, pastas de ambiente virtual ou credenciais reais para um repositório público.


## Atualização v2.2
- Título da aba do navegador alterado para `DS-PLANNERX`.
- Favicon próprio do DS-PLANNERX adicionado em todas as páginas.

## Atualização v2.3 — planejamento mensal e fluxo de produção

- Modo de postagem personalizado por mês, com várias regras no mesmo mês.
- Calendário anual JAN–DEZ dentro de cada canal.
- Página de planejamento mensal com regras, datas calculadas, anotações e cards do mês.
- Marcação independente de vídeo publicado.
- Datas da agenda em roxo neon no dia, verde quando publicadas e vermelho quando vencidas sem publicação.
- Nova página **Fluxo de Produção**, com mês, título, data, operador e atividade realizada.
- Os lançamentos do fluxo alimentam as metas diárias do canal.
- Aviso de **META ALCANÇADA** com troféu e mensagens variadas.
- Migração automática e não destrutiva: as tabelas e colunas novas são adicionadas sem apagar canais, cards, títulos ou anexos existentes.

### Atualização segura

Substitua os arquivos do repositório e faça o commit normalmente. Não apague nem troque `DATABASE_URL`, o banco Neon ou o Blob Store já conectados. O primeiro acesso após o deploy executa apenas comandos `CREATE TABLE IF NOT EXISTS` e `ADD COLUMN IF NOT EXISTS`.


## Atualização v2.4.2 segura — planejamento mensal dentro das configurações

- O modo **Personalizado por mês** agora é montado diretamente na janela **Configurar**.
- Escolha o mês, adicione informações e crie quantas semanas ou trechos forem necessários.
- Botão **Gerar semanas** cria automaticamente os blocos do mês para edição individual.
- O resumo mostra todas as datas unificadas e a quantidade final de vídeos antes de salvar.
- O calendário do canal mostra somente os meses que realmente foram configurados.
- Cada mês abre uma área própria com o mesmo layout de cards do canal, inicialmente limpa, para criar apenas os vídeos daquele mês.
- Planejamentos existentes podem ser reabertos, editados ou removidos sem excluir os cards de vídeo.
- Migração incremental: adiciona apenas o campo de identificação das regras e preserva todos os dados já salvos.


## Atualização segura v2.4.2

Esta edição usa exatamente a estrutura de banco da versão estável v2.3.1. O planejamento personalizado foi reorganizado no código e no layout sem adicionar, remover ou renomear colunas no Neon. Os períodos são numerados automaticamente na interface.


## Atualização v2.5 — página mensal unificada

- Clicar em um mês do calendário mantém o usuário na página principal do canal.
- A mesma tela passa a mostrar apenas o planejamento, os cards, as datas e os indicadores do mês selecionado.
- A meta de produção mensal usa a quantidade de datas calculadas no planejamento daquele mês.
- Em produção, concluídos, títulos restantes e porcentagem são calculados somente com os cards daquele mês.
- Cada mês possui um Banco de Títulos independente, inicialmente vazio, cuja quantidade acompanha as datas planejadas.
- O formulário de novo vídeo já abre limitado ao mês selecionado e sugere a primeira data ainda sem card.
- A página antiga `/months/AAAA-MM` permanece compatível, mas redireciona para a página principal com o mês selecionado.
- A atualização não cria nem altera tabelas do Neon. Os bancos mensais usam posições reservadas na tabela de títulos existente, preservando o banco geral e todos os dados anteriores.
