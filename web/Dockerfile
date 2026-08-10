FROM node:20-alpine AS build

WORKDIR /app

COPY web/package.json web/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY web .
RUN pnpm build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx-web.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
