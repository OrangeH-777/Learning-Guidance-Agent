# 首期实现说明

2026-09-27，当前工作区。用户确认每课程独立画像、Argon2id、数据库会话/CSRF、Fernet、公网 HTTPS 默认策略与 YAML＋Markdown；确认修订执行集 DS13；本轮仅首期，S12/S13 后续讨论。用户随后要求继续，按已提出的手动模型 ID、文本 JSON 严格校验、固定规则＋模型辅助核验、纯文本展示和兼容 embeddings 方案实施。

## 数据与接口

当前路径和输入字段见 [OpenAPI](openapi.json)，物理字段见 [数据字典](data-dictionary.md)。可通过 `python -m scripts.export_contracts` 重新导出，不连接数据库。

2026-09-28补齐全部20个业务操作的响应模型：认证、课程、画像/草稿、个人模型、任务、历史、三类资源及来源；204保持空响应。`backend/app/schemas/responses.py`严格拒绝额外字段，资源正文使用同一判别联合，公开模型设置没有API Key或密文字段。401/403/404/409/422/429/500/502/503统一错误契约纳入OpenAPI；内部返回校验失败仅返回脱敏500。现有`/api`路径作为首期接口基线，修改需同步契约与前端回归，团队最终设计签收单列S1-16。

| API | 行为 |
| --- | --- |
| POST /api/auth/register、/login | 建立数据库会话；返回当前用户与 CSRF token，Cookie 保存随机会话凭据 |
| GET /api/auth/session；POST /api/auth/logout | 恢复会话；撤销当前会话 |
| GET /api/courses | 返回课程、启停状态、知识就绪状态 |
| GET/PUT /api/courses/{id}/profile | 本人该课程的最新确认版本；expected_version 乐观并发检查 |
| GET …/profile/draft；POST …/profile/conversation | 获取课程独立草稿；模型只提取字段，不自动确认 |
| GET/PUT/DELETE /api/model-settings；POST …/test | 本人设置、增加版本、停用当前设置、主动连通测试 |
| POST/GET /api/tasks；GET /api/tasks/{id} | 受理生成、最近任务、本人任务状态 |
| POST /api/tasks/{id}/retry | 仅失败任务可重试，新增任务，沿用原画像与模型配置版本 |
| GET /api/resources、/api/resources/{id} | 本人成功资源的稳定分页、筛选及原快照重读 |
| GET /api/courses/{id}/sources/{id} | 按课程和公共/本人私有权限读取原来源片段 |

错误响应统一为 `{"error":{"code":"...","message":"..."}}`，输入错误还包含安全字段位置。未知账号和错误密码使用相同提示；跨用户 UUID 和不存在 UUID 同为404。密码、API Key、外部错误正文和数据库连接串不会写入业务错误响应。

所有权从会话确定，客户端不能指定 user_id。业务表使用 UUID 和 UTC 带时区时间；页面转换为北京时间。同用户请求 key 唯一，活动任务使用部分唯一索引，资源 task_id 唯一。画像和个人模型配置只追加版本，用户行锁串行化版本写入。当前画像由最新版本查询得到，不存在多个可修改的“当前指针”。

课程序号采用 `[a-z][a-z0-9_]{0,63}`；用户名4—20 ASCII字符；密码8—64 Unicode字符且包含字母和数字；画像字段1—500；对话1—1000；主题1—100；模型ID1—200；URL最多2048；请求 key1—64；分页默认10且最大50。前端用 Unicode code point 计数，不使用浏览器的 UTF-16 截断。

## 认证、密钥和网络边界

密码由 Argon2id 带随机盐哈希，未知账号也执行同类密码校验以减少差异。Cookie 为 HttpOnly、SameSite=Lax，2小时过期；HTTPS 部署设 `COOKIE_SECURE=true`。变更请求验证会话绑定 CSRF token，Origin 必须属于配置白名单；登录注册也检查 Origin 和跨站请求标志。

Fernet 加密个人 API Key，数据库只存密文；修改创建新版本，留空保留旧密钥；DELETE 创建停用版本。已受理任务仍需旧版密文，因此停用不等于清除所有历史密文。正式保留期与清除政策尚待部署讨论，不承诺已实现永久删除。密钥轮换参见运行手册。

Base URL 默认仅允许公网 HTTPS；内网与本地服务必须由 `MODEL_ENDPOINT_ALLOWLIST` 精确列出 scheme/host/port。拒绝 URL 凭据、query、fragment；DNS 返回的所有地址均检查，连接固定为已验证 IP，同时保持原 Host 和 TLS SNI，阻止 DNS 重绑定绕过。禁用自动重定向、环境代理和底层自动重试。下载的响应上限2MiB。

当前使用应用层所有权校验和 SQL 内权限谓词，不启用 PostgreSQL RLS；数据库账户不得向浏览器或模型开放。RLS 作为后续防御评审事项保留。

## 模型与核验

四类适配器均使用单次非流式文本调用；没有模型自动发现或静默切换。OpenAI Chat/Responses 使用 Bearer，Messages 使用 x-api-key，Gemini 使用 x-goog-api-key。Base URL 包含版本根路径；Messages 请求 max_tokens=4096，其余未擅自设置温度、推理级别等不同厂商支持程度不一的参数。

返回文字必须是完整 JSON 对象，不自动去除代码围栏或猜测缺失字段。三类资源使用共享 Pydantic 判别联合；非法 JSON、结构缺失和核验不通过进入有限内容重生成。服务商拒绝、输出截断、未知格式均不能作为成功内容。

LangGraph：planning → generating → validating → formatting。格式整理是确定性的结构序列化，随后重新验证结构、来源及内容。图只返回候选，后端在同一事务中保存资源与 completed。任何核验异常失败关闭。固定规则覆盖结构、题号/选项/答案关系、来源权限以及少量数据结构事实回归；模型辅助检查主题、材料支持、复杂度与前提、题答和安全。自动核验不保证事实完全正确；human_pass 只由真实人工复核形成，本次所有生成记录默认false。

依据官方格式实现并以替身验证：[OpenAI 文本生成](https://developers.openai.com/api/docs/guides/text)、[Responses 迁移说明](https://developers.openai.com/api/docs/guides/migrate-to-responses)、[Anthropic Messages](https://platform.claude.com/docs/en/build-with-claude/working-with-messages)、[Gemini generateContent](https://ai.google.dev/api/generate-content)。未获得真实服务配置，不能声明任何兼容服务已通过线上验收。

## 调度与恢复

总期限从受理时开始，最多180秒；单次模型最多60秒且不得超过剩余预算。通信仅补试1次，内容最多重生成2次，计数分离；429尊重Retry-After，超过剩余预算不再次请求。迟到响应被丢弃。

同库使用 PostgreSQL 会话 advisory lock 限制一个调度进程；用户行锁、容量 advisory lock、活动任务唯一索引共同保护受理。默认同时活动任务最多2，单用户1，不设额外等待槽。`TASK_QUEUE_CAPACITY` 可显式配置，增大值须重新测量180秒预算，不将当前默认值视为生产容量结论。

启动将遗留非终态标 INTERRUPTED。运行时保存失败会回滚，再补记失败；数据库暂不可用时保留待补记队列。调度锁连接丢失则停止接收并取消工作，恢复后需重启进程，避免失锁后双进程执行。

提示词版本使用节点实现和资源/工作流契约的内容指纹，统一换行后计算SHA-256；接受任务时固定版本，代码升级后不能静默用新提示词执行旧版本重试，版本不可用时报PROMPT_VERSION_UNAVAILABLE。任务telemetry记录task_id、各阶段耗时、协议/模型、知识/提示词版本、调用/通信补试次数和提供方返回的用量；错误保存在error_code。未知token用量保持null，不估造数字，不在遥测中存完整画像和凭据。数据库不可用时无法保证写入遥测，不能将缺记录解释为成功。

## 知识与展示

课程 YAML 保存元数据、正文相对路径、来源URL、章节、版本和审查状态；Markdown只存课程正文。目录导入不建立向量，不伪造就绪状态。索引先完成外部嵌入，再短事务写入并切换课程活动版本；版本关联材料与元数据哈希、模型、维度和切块参数，变更必须新建版本。旧来源片段不覆盖。

切块做 NFC 和换行规范化，按段落/标题组织，开发初值1200字符，无重叠。当前是精确余弦查询，SQL先限定用户、课程、版本、模型和维度，再排序；top-k=6、距离阈值0.8只是可调开发初值，尚无真实模型的召回评测。关键词仅保留接口，不启用未评审的中文分词/混合排序。

前端按结构显示讲解、练习与树形文本，所有内容均使用 Vue 转义插值；代码围栏内容作为文本 code 展示。不使用 v-html，不渲染模型给出的HTML或可点击链接。AI提示与人工状态由服务端固定生成。正式页面不提供测试替身切换开关。

## 尚待外部条件

第二门及后续实际课程、内容负责人复核、真实嵌入服务及费用额度、各模型协议真实连通、DS30质量评估、正式部署参数与数据保留政策、第二人复现及团队验收尚未完成。它们在plan中保持未勾选，S12/S13不进入本次首期。
