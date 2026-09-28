# 个性化学习资源平台 · Learning Guidance Agent

根据经用户确认的学习基础、目标与偏好，结合课程知识生成讲解、练习和文本思维导图，提供自动核验、来源追溯与个人历史。

当前已实现首期业务代码：注册登录、每课程独立画像与对话草稿、个人模型设置、四类协议适配、课程目录与 pgvector 检索、LangGraph 工作流、任务调度、三类资源展示及历史；新增管理员公共教材上传、正文校对和索引管理。已用真实 PostgreSQL 与明确标记的模型替身跑通完整流程；**尚未配置真实聊天/嵌入服务，因此不宣称真实模型质量验收或正式交付完成**。逐项状态见 [plan.md](plan.md)，证据见 [实施报告](docs/test/implementation-phase2.md)。

## 技术与目录

Node.js 24.14.1、Python 3.13.0；Vue 3 / TypeScript / Vite；FastAPI / SQLAlchemy / Alembic；PostgreSQL / pgvector；LangGraph。Python 依赖由 uv.lock 锁定，前端由 package-lock.json 锁定。

| 目录 | 内容 |
| --- | --- |
| frontend/ | 登录、工作台、画像、模型设置、资源及历史页面 |
| backend/app/ | 认证、接口、业务、持久化与单进程任务调度 |
| backend/migrations/ | 三个 Alembic 迁移版本，包含管理员权限字段 |
| agents/ | 四类协议、节点、LangGraph、检索及核验 |
| knowledge/<course_id>/ | course.yaml 元数据及 content/*.md 公共正文 |
| scripts/ | 目录导入、索引、迁移检查、密钥轮换、验收执行及契约导出 |
| tests/ | 单元、协议、真实数据库集成测试、原始/修订验收样例 |
| docs/ | 四份原始 Word、设计、测试和使用/运行手册 |

`npm run dev` 必须读取 npm 的 `package.json`，Vite 构建读取 `vite.config.ts`；课程业务配置已采用 YAML。两种文件负责不同内容，课程目录不会从测试 JSON 中加载。个人模型设置保存在数据库，部署秘密放在根目录 `.env`。

## 本地运行

本次交付范围已确认仅为本地部署：Windows 本机运行前后端，现有 Docker 容器运行数据库。服务器部署、公网 HTTPS 和应用容器化留待后续，不作为本次本地验收条件。

### 1. 安装依赖

在项目根目录执行：

```powershell
uv sync --locked
cd frontend
npm ci
cd ..
```

### 2. 准备数据库和本地配置

本工作区已建立本地数据库容器 `lga-postgres-dev`，仅监听 `127.0.0.1:55432`。开发库 `lga_dev`、测试库 `lga_test` 相互独立，已实际验证 PostgreSQL 17.11 / pgvector 0.8.6。随机数据库凭据和 Fernet 密钥已保存在忽略的 `.env`；**不要覆盖已有 .env**。

已有容器未启动时：

```powershell
docker start lga-postgres-dev
```

其他环境可以使用自行维护的 PostgreSQL＋pgvector，复制 `.env.example` 为 `.env` 并填写 `DATABASE_URL`、`MODEL_CREDENTIAL_ENCRYPTION_KEY`。数据库地址格式为 `postgresql+psycopg://USER:PASSWORD@HOST:PORT/DB`，密码中的特殊字符须 URL 编码。Fernet 密钥必须由 `cryptography.fernet.Fernet.generate_key()` 生成。

也可以在已有 Docker 的全新本地环境、且尚无 `.env` 时执行：

```powershell
uv run --locked python -m scripts.setup_local_database
docker exec lga-postgres-dev pg_isready -U lga
docker exec lga-postgres-dev createdb -U lga lga_test
```

该脚本使用固定镜像摘要，只搭建本地开发数据库，不是服务器部署方案；容器数据保存在 `lga-postgres-data` volume。首次迁移需要有安装 vector 扩展的权限。运行时应使用专用受限账号，正式权限方案仍需部署评审。

```powershell
uv run --locked alembic upgrade head
uv run --locked python -m scripts.import_courses
uv run --locked python -m scripts.check_database
```

### 3. 启动前后端

首次初始化管理员：在 `.env` 设置 `ADMIN_USERNAME`（4—20位字母、数字或下划线）和 `ADMIN_PASSWORD`（8—64字符，含字母与数字），再执行：

```powershell
uv run --locked python -m scripts.bootstrap_admin
```

当前工作区已初始化 `admin`，随机密码保存在本地 `.env` 的 `ADMIN_PASSWORD`，不在代码或文档中公开。普通注册不能获得管理员权限，配置中的管理员名称也不能用于普通注册。初始化脚本重复运行不会重设密码或提升已有普通用户；修改 `.env` 密码不等于修改数据库中已创建账号的密码。

根目录终端：

```powershell
uv run --locked uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

另一个终端：

```powershell
cd frontend
npm run dev
```

访问 http://127.0.0.1:5173 。API 文档在 http://127.0.0.1:8000/docs 。`/health` 是存活检查，`/health/ready` 检查 PostgreSQL、pgvector 和调度器；就绪不代表外部模型和课程内容已经验收。

只能运行一个后端调度进程，不要增加 Uvicorn workers；应用用 PostgreSQL advisory lock 防止同库双调度。结束前后端用 Ctrl+C；停止本地数据库用 `docker stop lga-postgres-dev`，无需删除 volume。

### 4. 配置模型与知识

注册登录后，进入“模型设置”，选择协议并自行填写服务商的 Base URL、模型 ID、API Key，再主动执行连接测试。模型凭据与本站登录账号、密码无关；下方“我的配置记录”仅展示本人保存过的配置及密钥保存状态，不回显密钥。支持 Chat Completions、Responses、Anthropic Messages、Gemini；兼容服务逐协议验证，不自动切换模型。Base URL 包含版本根路径，例如 `/v1` 或 `/v1beta`，不包含具体方法路径。

默认仅允许公网 HTTPS；本地或内网服务由部署方在 `MODEL_ENDPOINT_ALLOWLIST` 配置精确 origin。API Key 后端加密，页面不回显。连接测试、对话提取和生成可能产生服务商费用。

统一嵌入配置在 `.env` 中填写：

```dotenv
EMBEDDING_PROTOCOL=openai_compatible
EMBEDDING_BASE_URL=https://YOUR_PROVIDER/v1
EMBEDDING_API_KEY=YOUR_KEY
EMBEDDING_MODEL=YOUR_EMBEDDING_MODEL
EMBEDDING_DIMENSIONS=YOUR_ACTUAL_DIMENSIONS
EMBEDDING_INDEX_VERSION=YOUR_UNIQUE_VERSION
```

上面的占位符必须替换为实际值；维度必须是模型实际输出的整数。不要将密钥放进课程 YAML、前端变量或 Git。保存 `.env` 后重启后端。

管理员登录后，点击导航中的“公共教材管理”：选择课程，上传 Markdown、文字版 PDF 或 Word `.docx`（单文件≤10 MB），预览并校正正文、填写来源信息、确认后保存，再手动建立索引。扫描版 PDF 先 OCR，旧版 `.doc` 先另存；不保留上传原文件，只将确认后的正文保存为公共 Markdown。详细步骤见[管理员教材手册](docs/manual/public-materials.md)。

也可以直接维护目录，YAML 示例及命令见 [教材配置说明](knowledge/README.md#教材配置步骤本地运行)。目录索引读取登记的 Markdown；网站上传会先将 PDF/Word 转换为可校对的文本。当前数据结构已有六个主题的原创演示教材、例题和三个可运行代码示例，均待人工复核；其他真实课程未擅自编造。索引工具默认拒绝未复核资料：

```powershell
uv run --locked python -m scripts.index_knowledge data_structure
```

内容负责人实际复核后，在 course.yaml 更新对应 `review_status: approved`。仅限明确的本地开发预览，可使用 `--allow-unreviewed-preview`；该选项不代表材料已通过人工验收。索引会向嵌入服务发送课程正文，可能产生费用。未配置嵌入、不存在匹配材料或索引未就绪时会阻止生成，不制造假向量或来源。

网站每次建立索引会自动生成该课程的新修订版本，更新教材无需手动修改 `.env` 或重建其他课程。全局 `EMBEDDING_INDEX_VERSION` 标识统一嵌入配置族；切换嵌入模型、维度时应更新它，并为所有需要使用的课程重建索引。CLI 仍使用全局值作为索引版本，CLI 更新已有资料时需使用新值。历史资源继续引用原片段。检索参数当前是可调开发初值，真实召回质量尚未测量。

## 检查与测试

根目录：

```powershell
uv run --locked pytest -q -p no:cacheprovider
uv run --locked ruff check backend agents scripts tests
uv run --locked ruff format --check backend agents scripts tests
uv run --locked alembic check
```

集成测试必须配置独立的 `TEST_DATABASE_URL`，数据库名以 `_test` 结尾。测试会清空其中业务数据；缺少配置时明确跳过，绝不能指向开发或用户数据。所有默认测试不调用付费模型，模型替身只在测试入口注入。

测试库名称还必须与 `DATABASE_URL` 指向的应用库不同，即使部署在不同服务器也不能同名；测试入口拒绝通过连接查询参数覆盖数据库地址。

前端目录：

```powershell
npm run build
npm run test:e2e
```

浏览器测试使用本机 Chrome 和 Edge，自动启动8001/5174端口的隔离服务，并清空测试库。不要与 Python 集成测试同时运行。运行结果位于忽略目录 `tests/results/`。

迁移往返检查也只对独立测试库执行，且会清空测试数据：

```powershell
uv run --locked python -m scripts.check_migrations
```

真实 DS01—DS30 验收脚本仅供已有模型、嵌入及费用额度后显式执行：

```powershell
uv run --locked python -m scripts.run_course_acceptance --username YOUR_TEST_USER --acknowledge-costs
```

脚本交互读取密码，保留全部首次记录；人工合理性复核仍需另行完成。原始 Word/JSON 保持10讲解、11练习、9导图；用户已确认的执行集只调整 DS13，执行口径为各10条。

实际报告可用 `uv run --locked python -m scripts.summarize_acceptance tests/results/live-ACTUAL_RUN.json --reviews tests/results/reviews-ACTUAL_RUN.json` 统计。字段模板、未知终态处理和人工复核要求见[真实验收流程](docs/test/live-acceptance.md)，没有人工记录时不会生成合理性通过结论。

## 文档与剩余验收

- [实现与接口说明](docs/design/implementation-v1.md)、[数据字典](docs/design/data-dictionary.md)、[OpenAPI](docs/design/openapi.json)
- [用户手册](docs/manual/user-guide.md)、[运行与恢复手册](docs/manual/operations.md)
- [首期测试报告](docs/test/implementation-phase2.md)、[需求与测试追踪](docs/test/coverage.md)
- [逐项验收任务卡](tests/acceptance/tasks.yaml)、[页面编号映射](docs/design/page-mapping.md)、[未发布交付说明](docs/manual/delivery-notes.md)

`uv run --locked python -m scripts.prepare_acceptance_tasks --check`核对98张验收任务卡；`uv run --locked python -m scripts.check_delivery`检查可共享文本/构建包是否含已配置密钥，并生成本地内容指纹清单。这些检查不调用模型，也不代替实际课程质量和人工验收。

本次仅要求本地部署；服务器、公网 HTTPS 和生产容量规划留后续。真实模型连通与DS30质量、第二门课程、课程材料复核、数据保留决策及人工验收仍未完成。当前没有发布标签，不代签团队评审和第二名成员复现。S12个人上传和S13可选功能按此前确认留待后续讨论。详见 plan.md 中未勾选项及说明。
