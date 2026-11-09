# 个性化学习资源平台 · Learning Guidance Agent

## 项目介绍

面向大学生的多智能体学习平台，以《数据结构》为示例课程。学生选择教材章节、填写学习需求后，系统结合个人学习画像生成概念讲解、练习题或文本思维导图。管理员可按章上传、校对和维护公共教材。

## 技术栈

- 前端：Vue 3、TypeScript、Vite，使用 Node.js 24.14.1 和 npm 11。
- 后端：Python 3.13、FastAPI、LangGraph，使用 uv 管理依赖。
- 数据库：PostgreSQL（pgvector）、SQLAlchemy 和 Alembic。
- 测试：pytest 用于后端测试，Playwright 用于浏览器测试。

## 本地运行

**Docker Desktop**　已有容器时，依次启动数据库 `lga-postgres-dev`、后端 `lga-backend` 和前端 `lga-frontend`，然后打开 [Docker 版工作台](http://127.0.0.1:8088)。三个容器可分别管理。首次构建见 [独立容器运行说明](docker/README.md)。

**本机开发**　以下 PowerShell 命令均从项目根目录执行。与容器版共用数据库时，一次只运行一个后端调度器。

**后端**　首次运行 `uv sync --locked` 安装依赖。已有本项目本地数据库和 `.env` 时，运行 `docker start lga-postgres-dev` 启动数据库。全新环境可在 Docker 启动后运行 `uv run --locked python -m scripts.setup_local_database`，创建数据库容器和本地 `.env`。

数据库就绪后，首次初始化数据表和课程目录：

```powershell
uv run --locked alembic upgrade head
uv run --locked python -m scripts.import_courses
```

启动后端：

```powershell
uv run --locked uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

**前端**　另开一个终端，首次运行 `npm ci` 安装依赖：

```powershell
cd frontend
npm ci
npm run dev
```

打开 [本地工作台](http://127.0.0.1:5173)，登录后在“模型设置”填写模型地址、模型 ID 和 API Key，完成连接测试。首次启用教材管理时，在根目录 `.env` 设置 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD`，再运行 `uv run --locked python -m scripts.bootstrap_admin`。

## 运行测试

以下命令在项目根目录执行。集成测试和浏览器测试都会清空 `TEST_DATABASE_URL` 指定的数据库，请使用独立的 `*_test` 库并依次运行。使用上述脚本新建本地环境时，首次测试前执行 `docker exec lga-postgres-dev createdb -U lga lga_test`。

```powershell
# 后端单元测试与接口契约测试
uv run --locked pytest -q tests/unit tests/contract

# PostgreSQL 集成测试
uv run --locked pytest -q tests/integration

# 浏览器测试（本机 Chrome 和 Edge，自动启动测试前后端）
npm --prefix frontend run test:e2e
```

只看公共教材管理的操作流程，可以运行 `npm --prefix frontend run test:e2e -- admin-materials.spec.ts --project=chrome --headed`。浏览器用例在 [frontend/e2e](frontend/e2e)，后端用例在 [tests](tests)。
