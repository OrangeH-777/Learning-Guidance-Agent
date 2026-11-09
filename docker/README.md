# Docker Desktop 独立容器

| 容器 | 服务 | 本机入口 |
| --- | --- | --- |
| `lga-frontend` | Nginx 提供网页，并转发 API 请求 | [工作台](http://127.0.0.1:8088) |
| `lga-backend` | FastAPI 和生成任务调度器 | [接口文档](http://127.0.0.1:8008/docs) |
| `lga-postgres-dev` | 原有 PostgreSQL 与 pgvector | `127.0.0.1:55432` |

**日常使用**　在 Docker Desktop 的 **Containers** 中依次启动数据库、后端和前端。数据库及账号沿用现有数据卷；课程资料读写项目的 `knowledge/`，个人模型密钥继续使用根目录 `.env` 中的加密配置。与本机开发环境切换时，先停止当前后端，以便另一个后端取得调度锁。

**首次创建**　在 Windows 项目根目录打开 PowerShell，使用 Docker Desktop 的 Linux 容器模式。以下命令适用于已有项目 `.env`、教材目录和 `lga-postgres-dev` 数据库容器的环境；全新环境先按主 README 初始化本地数据库。

```powershell
docker start lga-postgres-dev
docker network create lga-net
docker network connect lga-net lga-postgres-dev
```

单独构建和启动后端。启动时会检查数据库、应用迁移、导入课程目录，并在配置了管理员凭据时初始化管理员。

```powershell
docker build -f docker/backend.Dockerfile -t lga-backend:local .
$settingsFile = (Resolve-Path -LiteralPath .env).Path
$materialsDir = (Resolve-Path -LiteralPath knowledge).Path
docker run -d --name lga-backend --network lga-net --restart unless-stopped `
  -p 127.0.0.1:8008:8000 `
  --mount "type=bind,source=$settingsFile,target=/app/.env,readonly" `
  --mount "type=bind,source=$materialsDir,target=/app/knowledge" `
  lga-backend:local
```

单独构建和启动前端。

```powershell
docker build -f docker/frontend.Dockerfile -t lga-frontend:local .
docker run -d --name lga-frontend --network lga-net --restart unless-stopped -p 127.0.0.1:8088:80 lga-frontend:local
```

打开 [就绪检查](http://127.0.0.1:8088/health/ready)，当 `database`、`pgvector` 和 `scheduler` 均为 `ok` 时即可使用工作台。后续可以在 Docker Desktop 中单独停止或启动任一容器。
