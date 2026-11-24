# ZhalHub

一个可自托管的 AstrBot 插件市场。用户可以通过邮箱注册账号，绑定 GitHub
或 Gitee，发布自己拥有的公开插件仓库，并手动检测 `metadata.yaml` 中的新版本
号。市场同时提供 AstrBot 兼容的 `market.json` 和 `market-md5.json`。

## 功能

- 公开浏览、搜索插件，查看 Star、AstrBot 版本约束、支持平台和标签。
- 插件详情提供概览、文档、更新日志和版本；已归档版本可下载 ZIP。
- 中英文和亮暗主题；在「我的主页」直接修改昵称和头像。
- 邮箱及密码注册、登录和可撤销浏览器会话。
- GitHub、Gitee OAuth 账号绑定。
- 仅允许发布绑定账号有写入权限的公开仓库。
- 自动校验 `metadata.yaml`、仓库归属、插件 ID 和版本号。
- 在「我的插件」查看插件卡片、认领已有条目、检测新版和上下架；不设置人工审核流程。
- 首次启动自动导入仓库根目录现有的 `market.json`。
- 推荐使用 Docker Compose 部署，Caddy 自动管理 HTTPS。

## 仓库要求

插件仓库根目录必须包含 `metadata.yaml`，建议同时提供 `logo.png` 和
`README.md`、`docs/README.md` 和 `CHANGELOG.md`。版本号使用 PEP 440 格式，例如 `1.2.0`；也兼容常见的
`v1.2.0` 写法。

```yaml
author: 饰乐
name: astrbot_plugin_example
display_name: 示例插件
version: 1.0.0
repo: https://github.com/example/astrbot_plugin_example
desc: 示例插件描述
astrbot_version: ">=4.20,<5"
support_platforms: [telegram]
tags: [工具]
```

`repo` 必须与用户通过 OAuth 选择的仓库完全一致。第一版仅支持公开仓库。
每次发布会将元数据所在提交归档为 ZIP；修改已发布的内容需要提高 `version`。

## Docker 部署

服务器需要安装 Docker Engine 和 Docker Compose 插件，并确保域名的 A/AAAA
记录已经指向服务器，80、443 端口可从公网访问。

```bash
cp .env.example .env
```

编辑 `.env`，至少修改：

- `DOMAIN`、`PUBLIC_URL`、`FRONTEND_URL`
- `POSTGRES_PASSWORD`
- `AUTH_SECRET_KEY`
- `OAUTH_ENCRYPTION_KEY`
- GitHub/Gitee OAuth Client ID 和 Client Secret

可以通过以下命令生成 OAuth 加密密钥：

```bash
docker run --rm python:3.12-slim sh -c \
  "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

启动服务：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

如果服务器已有 Nginx 占用 80/443，可让容器只监听环回地址：

```bash
docker compose -f compose.yaml -f deploy/compose.nginx.yaml up -d --build
```

然后由现有 Nginx 将站点域名反向代理到 `http://127.0.0.1:8088`。

更新服务：

```bash
git pull --ff-only
docker compose up -d --build
```

备份 PostgreSQL：

```bash
docker compose exec -T db pg_dump -U market market > market-backup.sql
```

归档 ZIP 保存在 `plugin_packages` 持久卷，Logo 保存在 `plugin_assets`；备份或迁移时请同时保存这两个卷。不要用 `docker compose down -v` 更新服务。

## OAuth 应用

### GitHub

在 GitHub Developer Settings 中创建 OAuth App：

- Homepage URL：`https://你的域名`
- Authorization callback URL：
  `https://你的域名/api/v1/oauth/github/callback`

将 Client ID 和 Client Secret 写入 `.env`，并设置 `GITHUB_ENABLED=true`。

### Gitee

在 Gitee 第三方应用中配置：

- 应用主页：`https://你的域名`
- 回调地址：`https://你的域名/api/v1/oauth/gitee/callback`

将应用凭据写入 `.env`，并设置 `GITEE_ENABLED=true`。

## 统一配置

非秘密配置集中在 [`config/config.yaml`](config/config.yaml)。敏感值由 `.env`
提供，并通过 `${NAME:-default}` 语法注入。常用设置包括：

- 站点名称和公网地址
- 数据库连接
- Cookie 和令牌有效期
- OAuth 平台开关及回调地址
- 市场标题、描述和远程文件大小限制
- `market.max_package_bytes`（默认 16 MiB）、`market.max_unpacked_bytes`（默认 128 MiB）和 `market.max_avatar_bytes`（默认 512 KiB）
- 允许的代码托管平台

生产环境设置 `APP_ENV=production` 后，后端会拒绝默认认证密钥。

## AstrBot 插件源

部署完成后，在 AstrBot 插件源管理中添加：

```text
https://你的域名/market.json
```

对应的缓存指纹地址为：

```text
https://你的域名/market-md5.json
```

## 本地开发

后端：

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 会将 `/api`、`/market.json` 和 `market-md5.json` 代理到本地后端。

运行检查：

```bash
cd backend
uv run ruff format .
uv run ruff check .
uv run pytest

cd ../frontend
npm run build
```

## 数据迁移

空数据库首次启动时，后端会读取根目录的 `market.json` 并导入已有插件。
数据库已有任何插件后不会重复导入。后续发布、更新和下架均以数据库为准，
兼容 JSON 由 API 动态生成。

Docker 启动时会通过 Alembic 升级现有库，不清除账号或插件。历史插件导入后可分批补抓文档和 Star：

```bash
docker compose exec -T backend sh -c 'cd /app/backend && python -m app.backfill --offset 0 --limit 10'
```

后续按 `--offset 10`、`--offset 20` 继续。只补 ZIP 时可加 `--archives-only`：仅使用已记录的提交，且包内的作者、插件名和版本必须匹配，不会覆盖已有文档。可在容器中通过 `GITHUB_BACKFILL_TOKEN` / `GITEE_BACKFILL_TOKEN` 提供只读凭据以提高文档同步 API 限额。
