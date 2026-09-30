FROM node:22-alpine AS build

# 包管理器只从国内镜像获取，并关闭 pnpm 的联网更新检查：
# 构建期访问 npm 官方源会长时间挂起并导致 Web 镜像构建失败。
ENV COREPACK_NPM_REGISTRY=https://registry.npmmirror.com \
    NPM_CONFIG_UPDATE_NOTIFIER=false

WORKDIR /app

COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN corepack enable \
    && pnpm config set registry https://registry.npmmirror.com \
    && pnpm install --frozen-lockfile

COPY web .
RUN pnpm build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx-web.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
