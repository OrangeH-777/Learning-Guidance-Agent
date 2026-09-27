# 基于多智能体协作的个性化学习资源平台

Learning Guidance Agent 面向大学生，根据经用户确认的知识基础、学习目标和兴趣偏好，协作生成课程讲解、带答案解析的练习题和文本思维导图，并提供核验、保存与个人历史。

**当前版本为项目架构骨架。** 已提供前端占位页面、后端健康检查、PostgreSQL/pgvector 检查入口、Alembic 配置、依赖锁定及模块目录。登录、画像、课程选择、个人模型设置、检索、智能体生成和上传功能尚未实现。完整任务与确认框见 [plan.md](plan.md)。

2026-09-27已进入S1设计与契约实施：新增[模块与流程设计](docs/design/architecture.md)、[需求变更记录](docs/requirements/change-record.md)、三类资源结构契约、注册/画像/对话输入校验，以及原Word测试规格导入。当前接口仍只有健康检查，新增契约不等于完整业务已经可用。实施与验证结果见[本次记录](docs/test/implementation-2026-09-27.md)。

## 需求依据与已确认变更

原始依据位于 `docs/`：`项目内容.docx`、`项目启动文档.docx`、`第一循环文档.docx`、`第二循环文档.docx`。原文件保持不变，后续实施采用本次讨论确认的调整：

| 项目 | 当前实施方向 |
| --- | --- |
| 数据库 | PostgreSQL＋pgvector，替代原文档 SQLite |
| 环境 | Node.js 24、Python 3.13，Python 使用 uv 管理 |
| 课程 | 首期支持选择多个课程；数据结构保留为已有需求与测试样例的基础课程 |
| 公共知识 | `knowledge/<course_id>/` 分课程维护，供所有用户在相应课程中检索 |
| 私有知识 | 后续实现个人教材上传，检索限定“所选课程公共知识＋本人私有知识” |
| 聊天模型 | 每个用户配置自己的协议、Base URL、API Key、模型ID；凭据后端加密保存 |
| 嵌入模型 | 部署方独立统一配置，索引与个人聊天模型解耦 |
| 部署 | 当前提供本地开发方式；系统可运行后再讨论 Docker 等部署配置 |

原需求 R01—R07 保留，新增课程、模型设置和知识功能的任务见 plan.md。学习路径与上下文问答 R08 仍为需另外评审的可选项。视频、动画、模型训练、在线代码执行、教师后台不在已确认范围。

## 技术组成

| 层次 | 技术与职责 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Vue Router、Axios |
| 业务后端 | FastAPI、Pydantic、SQLAlchemy、Psycopg、Alembic |
| 工作流 | LangGraph；规划、生成、核验、格式整理模块占位 |
| 数据与检索 | PostgreSQL、pgvector；真实数据库及检索逻辑待接入 |
| 工程工具 | uv、npm、pytest、Ruff |

Node 固定版本见 `.node-version` / `.nvmrc`，当前为 `24.14.1`；Python 固定版本见 `.python-version`，当前为 `3.13.0`。精确依赖分别记录于 `uv.lock` 和 `frontend/package-lock.json`，不手工修改锁文件。

uv 使用项目内 `.venv` 和 `uv.lock` 管理环境，复现时使用 `uv sync --locked`。参见 [uv 项目结构说明](https://docs.astral.sh/uv/concepts/projects/layout/)。

## 目录

```text
Learning-Guidance-Agent/
├── frontend/                 Vue 应用与构建配置
│   └── src/
│       ├── api/              HTTP 客户端
│       ├── components/       通用组件预留
│       ├── router/           路由
│       ├── views/            当前占位页，业务页后续添加
│       ├── types/            业务类型预留
│       └── styles/           基础样式
├── backend/
│   ├── app/
│   │   ├── main.py           应用入口与生命周期
│   │   ├── api/              健康检查与业务路由入口
│   │   ├── core/             环境配置
│   │   ├── db/               数据库连接、元数据与检查
│   │   ├── schemas/          接口数据结构预留
│   │   ├── repositories/     数据访问预留
│   │   ├── services/         业务服务预留
│   │   └── tasks/            任务调度和恢复预留
│   └── migrations/           Alembic 配置；尚无业务迁移
├── agents/                   工作流、节点、协议、提示词、检索与核验
├── knowledge/
│   └── data_structure/       数据结构公共知识空目录
│       ├── content/
│       └── sources/
├── tests/                    unit、integration、contract、system、fixtures
├── scripts/                  数据库检查命令
├── docs/                     原始文档及后续过程文档目录
├── reference/                本地参考项目，已排除出本项目 Git 跟踪范围
├── .env.example              配置样例，不含真实密钥
├── pyproject.toml / uv.lock  Python 依赖及锁文件
├── alembic.ini               数据库迁移入口
├── plan.md                   从初始化到交付的任务清单
└── README.md
```

后端与智能体在同一 Python 环境中运行。未来任务由单后端进程中的受控异步执行器管理，状态持久化；首期不支持多个 Uvicorn worker 同时调度。实现细节与压力验证按 plan.md 推进。

QwenPaw 仅用于参考业务接口、运行调度、模型适配和配置分层；本项目不依赖其 React、AgentScope、插件平台或桌面能力。

## 快速启动骨架

### 1. 准备运行时

安装 Node.js 24、npm 11 和 uv。进入项目根目录后核对：

```powershell
node --version
npm --version
uv --version
```

如没有 `.python-version` 指定的 Python，可执行 `uv python install 3.13.0`，然后：

```powershell
uv sync --locked
Copy-Item .env.example .env
```

已有 `.env` 时保留原配置，不重复复制覆盖。Linux 对应的复制命令为 `cp -n .env.example .env`，其余 `uv`、`npm` 命令一致。

`.env` 由后端从项目根目录加载。当前启动无需模型密钥，也不要求数据库已经可用；这只用于验证骨架服务，不能执行业务流程。

### 2. 启动后端

在项目根目录的终端执行：

```powershell
uv run --locked uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

- [存活检查](http://127.0.0.1:8000/health)：正常返回 `status=ok` 和 `stage=scaffold`，不表示数据库或业务已就绪。
- [数据库就绪检查](http://127.0.0.1:8000/health/ready)：只有 PostgreSQL 可访问且已启用 pgvector 时返回 HTTP 200；缺少配置、连接失败或扩展缺失返回 HTTP 503。
- [接口说明](http://127.0.0.1:8000/docs)：当前仅包含健康检查接口。

### 3. 启动前端

另开终端，从项目根目录执行：

```powershell
cd frontend
npm ci
npm run dev
```

打开 [本地前端](http://127.0.0.1:5173)，点击“检查后端连接”。Vite 将 `/api` 和 `/health` 代理到 `127.0.0.1:8000`，浏览器不直接访问模型服务。端口冲突时会明确退出，请先处理占用。

结束服务时分别在前后端终端按 `Ctrl+C`。

## PostgreSQL 与 pgvector

项目不会自动安装系统数据库、创建账号、修改现有数据库或启用扩展。准备一个项目专用 PostgreSQL 数据库，并由数据库维护者安装匹配版本的 pgvector 服务端扩展。Python 的 `pgvector` 包不等于数据库已安装扩展。

管理员在**项目数据库**中执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

pgvector 需在每个使用它的数据库中启用，安装方式见 [pgvector 官方说明](https://github.com/pgvector/pgvector#installation)。

在根目录 `.env` 填入实际连接信息，例如：

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/learning_guidance
```

将 `USER`、`PASSWORD` 和数据库名替换为实际值；密码含 `@`、`:`、`/` 等字符时须做 URL 编码。不要将真实连接串提交到仓库或贴入问题日志。

执行只读检查：

```powershell
uv run --locked python -m scripts.check_database
```

成功返回 `status=ok`；未配置或不可用时退出码为 1，输出不包含连接凭据。该命令只检查连接和扩展，不建业务表，也不证明读写权限、迁移、事务或负载测试已经通过。

Alembic 已配置，可运行 `uv run --locked alembic history` 查看迁移历史。**当前没有业务表或迁移版本**；首个表结构经评审并编写迁移后，才使用 `uv run --locked alembic upgrade head` 建表。模型定义、迁移与回退测试列在 plan.md，不能将目前空迁移历史视为数据库初始化完成。

## 模型与知识配置边界

个人模型设置计划支持以下协议，当前仅预留模块：

| 协议 | 接入方向 |
| --- | --- |
| OpenAI Chat Completions | 该协议的原生或兼容服务 |
| OpenAI Responses | Responses 协议服务 |
| Anthropic Messages | Messages 协议服务 |
| Gemini 原生协议 | Gemini 协议服务 |

用户将填写协议、Base URL、API Key、模型ID。密钥由后端加密保存，页面只显示脱敏状态；服务商兼容程度与实际能力须单独验证，不能仅凭“兼容”名称宣称全部支持。具体服务商预设及能力矩阵在实现阶段确认。

`EMBEDDING_*` 是部署方的嵌入配置，独立于个人聊天设置。当前没有指定嵌入服务商、模型或维度，也没有索引程序；应在知识检索阶段确认后填写。`.env.example` 注明了尚未启用的配置，当前实际读取的只有 `DATABASE_URL` 和 `DATABASE_CONNECT_TIMEOUT_SECONDS`。

公共资料组织规则见 [knowledge/README.md](knowledge/README.md)。私有上传后续实施，其原文件、片段、向量、引用和缓存都须按照当前用户与课程隔离，不加入 Git。当前没有上传入口或静态文件下载通道。

## 检查与构建

根目录执行：

```powershell
uv run --locked pytest -q
uv run --locked ruff check backend agents scripts tests
uv run --locked ruff format --check backend agents scripts tests
```

前端目录执行：

```powershell
npm run build
npm run preview
```

构建产物位于 `frontend/dist/`，预览地址为 [构建预览](http://127.0.0.1:4173)。本地预览代理仍要求后端在 8000 端口运行。构建预览仅用于检查产物，不是部署方案。

当前测试验证健康检查、错误脱敏、输入边界、三类资源契约及原始验收规格一致性，不执行数据库或真实模型调用；业务测试、跨用户隔离、30条课程样例及真实协议验证均为后续工作。原文档DS样例实际为10条讲解、11条练习、9条导图，与其声明的各10条不一致，修订方式等待确认。

## 当前验证与限制

- 已配置 Python / Node 固定版本和依赖锁文件。
- 骨架交付时已通过3项基础测试、Ruff静态/格式检查、Vue类型检查与正式构建；Alembic空历史命令可运行。2026-09-27增加契约后共54项测试通过，本次未修改前端。
- 本地后端 `/health` 返回正常，前端返回HTTP 200，前端代理可访问后端；未配置数据库时 `/health/ready` 按预期返回HTTP 503。完整业务验收尚未开始。
- 本次未连接真实 PostgreSQL，未验证 pgvector 服务端、数据库读写或迁移。
- 本次未配置个人模型、嵌入模型或可信课程材料，未调用付费API。
- Docker、服务器部署、备份策略和实际发布在系统可运行后确认。

## 团队与协作

沿用原文档角色：陈志涵负责计划与需求，赵博龙负责后端，宇家宁负责前端，袁萱萱负责课程与内容质量，刘永兴负责配置与部署，沈超负责智能体与技术方案，黄俊杰负责测试。

后续按 Issue → 开发分支 → 自测 → 非作者评审 → 集成验证推进。不得提交 `.env`、数据库、用户材料、日志、虚拟环境、依赖目录及真实凭据。本次未创建远程仓库、分支或发布标签；相关任务保留在 plan.md。
