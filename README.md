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
