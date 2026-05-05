# viewer

Minimalist viewer for stapply public datasets. Static SPA (Vite + React + Tailwind) deployed to Cloudflare Pages at `data.stapply.ai`.

Datasets are fetched at runtime from `storage.stapply.ai` (Cloudflare R2).

## Develop

```bash
npm install
npm run dev
```

## Deploy

First time:

```bash
npx wrangler login
npx wrangler pages project create stapply-data-viewer --production-branch main
```

Then attach the custom domain `data.stapply.ai` in the Cloudflare dashboard (Pages → project → Custom domains).

For each release:

```bash
npm run deploy
```
