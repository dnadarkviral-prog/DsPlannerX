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
