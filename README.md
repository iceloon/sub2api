# Sub2API Ultrafast 二开

这是 [Wei-Shaw/sub2api](https://github.com/Wei-Shaw/sub2api) 的完整二次开发分支，不是精简版。

- 定制分支：`feature/openai-ultrafast`
- 上游主线：`main`，只跟踪官方仓库，不放业务改动
- 镜像：`iceloon/sub2api:ultrafast`

`main` 与官方代码保持一致。部署、构建和日常使用都走 `feature/openai-ultrafast`。

## 二开内容

相对官方主线，只增加了分组级 OpenAI Ultrafast 计费：

- 管理后台的 OpenAI / Composite 分组新增开关：**按 Ultrafast 计费（6 倍）**。
- 开启后，该分组的 OpenAI 请求写入 `service_tier=ultrafast`。
- `gpt-6.1-sol`、`gpt-6-sol`、`gpt-6-luna` 和 `gpt-6-astra` 按标准价的 6 倍计费。
- 上游响应即使回 `default`，也不会把费用降回 Standard。官方 Fast 开关会被这种回执降价，这是本分支单独处理的点。
- 与「强制 Fast」同时开启时，以 Ultrafast 为准。
- 数据库新增 `groups.force_openai_ultrafast`，默认关闭。
- 部署 Compose 的应用镜像从 `weishaw/sub2api:latest` 改为 `iceloon/sub2api:ultrafast`。
- `.github/workflows/daily-upstream-ultrafast.yml` 每天检查官方 `main`。有新提交时，把更新合并进 `feature/openai-ultrafast`，保留 Ultrafast 改动，并构建 GHCR 镜像。

官方 Fast 仍然是 2 倍，只作用于 `priority` / `fast`。Ultrafast 不读取渠道里的 Fast 倍率，也不会和 Fast 的 2 倍叠乘。

## 分支

```text
main                        对齐 Wei-Shaw/sub2api 的 main
feature/openai-ultrafast    完整上游代码 + Ultrafast 二开
```

本地远程：

```bash
git remote add upstream https://github.com/Wei-Shaw/sub2api.git
git remote set-url --push upstream DISABLED
```

同步官方主线：

```bash
git fetch upstream
git switch main
git merge --ff-only upstream/main
git push origin main

git switch feature/openai-ultrafast
git rebase main
git push --force-with-lease origin feature/openai-ultrafast
```

有冲突时先解决，再跑测试。不要把二开提交直接堆回 `main`。

## 部署

需要 Docker 20.10+ 和 Docker Compose v2。以下命令在仓库根目录执行。

```bash
git clone -b feature/openai-ultrafast https://github.com/iceloon/sub2api.git
cd sub2api

docker build \
  --build-arg GOPROXY=https://goproxy.cn,direct \
  --build-arg GOSUMDB=sum.golang.google.cn \
  --build-arg NPM_CONFIG_REGISTRY=https://registry.npmmirror.com \
  -t iceloon/sub2api:ultrafast .

cd deploy
cp .env.example .env
chmod 600 .env
```

`.env` 至少填写这三项，每项都用 `openssl rand -hex 32` 单独生成：

```bash
POSTGRES_PASSWORD=
JWT_SECRET=
TOTP_ENCRYPTION_KEY=
BIND_HOST=127.0.0.1
SERVER_PORT=8080
TZ=Asia/Shanghai
ADMIN_EMAIL=
ADMIN_PASSWORD=
```

`ADMIN_EMAIL` 和 `ADMIN_PASSWORD` 留空时，首次启动会在日志里生成管理员账号。`BIND_HOST=127.0.0.1` 只允许本机访问；需要局域网访问时再改成 `0.0.0.0`。

```bash
mkdir -p data postgres_data redis_data
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml ps
docker compose -f docker-compose.local.yml logs -f sub2api
```

打开 `http://127.0.0.1:8080`。健康检查是 `http://127.0.0.1:8080/health`。

完整 Compose 在 [deploy/docker-compose.local.yml](deploy/docker-compose.local.yml)。它包含应用、PostgreSQL 18 和 Redis 8，数据分别落在 `deploy/data`、`deploy/postgres_data`、`deploy/redis_data`。应用镜像固定为：

```yaml
services:
  sub2api:
    image: iceloon/sub2api:ultrafast
    container_name: sub2api
    restart: unless-stopped
    ports:
      - "${BIND_HOST:-0.0.0.0}:${SERVER_PORT:-8080}:8080"
    volumes:
      - ./data:/app/data:Z
    environment:
      - AUTO_SETUP=true
      - DATABASE_HOST=postgres
      - DATABASE_PASSWORD=${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
      - REDIS_HOST=redis
      - JWT_SECRET=${JWT_SECRET:-}
      - TOTP_ENCRYPTION_KEY=${TOTP_ENCRYPTION_KEY:-}
      - ADMIN_EMAIL=${ADMIN_EMAIL:-}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD:-}
      - TZ=${TZ:-Asia/Shanghai}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  postgres:
    image: postgres:18-alpine
    container_name: sub2api-postgres
    restart: unless-stopped
    volumes:
      - ./postgres_data:/var/lib/postgresql/data:Z
    environment:
      - POSTGRES_USER=${POSTGRES_USER:-sub2api}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
      - POSTGRES_DB=${POSTGRES_DB:-sub2api}
      - TZ=${TZ:-Asia/Shanghai}

  redis:
    image: redis:8-alpine
    container_name: sub2api-redis
    restart: unless-stopped
    volumes:
      - ./redis_data:/data:Z
    command: ["redis-server", "--save", "60", "1", "--appendonly", "yes", "--appendfsync", "everysec"]
```

仓库文件里还有网关超时、连接池和镜像任务等环境变量，部署时直接用仓库文件，不要手抄上面的摘要替代它。

不要使用官方一键脚本。那个脚本会下载 `weishaw/sub2api:latest`，没有本分支的 Ultrafast 计费。

常用命令：

```bash
docker compose -f docker-compose.local.yml restart sub2api
docker compose -f docker-compose.local.yml logs -f sub2api
docker compose -f docker-compose.local.yml down
```

升级镜像：

```bash
# 仓库根目录重新构建
docker build -t iceloon/sub2api:ultrafast .

# deploy 目录重建应用容器，数据库目录保留
docker compose -f docker-compose.local.yml up -d --no-deps --force-recreate sub2api
```

## 使用 Ultrafast

1. 用管理员账号打开后台。
2. 编辑 OpenAI 分组。
3. 打开「按 Ultrafast 计费（6 倍）」并保存。
4. 新请求立即按 Ultrafast 计费。已经建立的 WebSocket 要重连。

用量记录里的 `service_tier` 应为 `ultrafast`。费用按同一模型标准价的 6 倍计算，长上下文倍率仍按原规则叠加。

## 每日同步

`.github/workflows/daily-upstream-ultrafast.yml` 每天 02:17 UTC 检查 `Wei-Shaw/sub2api` 的 `main`。没有新提交就结束。有新提交时：

1. 把上游合并进 `feature/openai-ultrafast`。
2. 冲突时保留本分支改动，再用 `.github/scripts/apply_ultrafast_patch.py` 补回 Ultrafast 关键点。
3. 构建并推送 `ghcr.io/iceloon/sub2api:ultrafast`。

这个 Action 不改 `origin/main`。

## 许可证

上游代码仍遵循其 [GNU Lesser General Public License v3.0](LICENSE)。本分支的改动同样按该许可证提供。
