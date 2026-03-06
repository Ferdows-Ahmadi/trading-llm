FROM node:22-alpine

WORKDIR /app

COPY package.json pnpm-workspace.yaml turbo.json /app/
COPY apps/web/package.json /app/apps/web/package.json
COPY packages /app/packages

RUN corepack enable && pnpm install --filter @trading/web... --frozen-lockfile=false

COPY apps/web /app/apps/web

WORKDIR /app/apps/web

EXPOSE 3000

CMD ["pnpm", "dev", "--hostname", "0.0.0.0", "--port", "3000"]
