# 模块与生成流程

版本：V0.2，2026-09-27。覆盖plan中的S1-05及已确认架构。认证、每课程独立画像和YAML配置已获用户确认；具体落地见implementation-v1.md。

## 模块与信任边界

```mermaid
flowchart LR
  Browser[Vue浏览器界面] -->|同源API 会话凭据| API[FastAPI接口]
  API --> Identity[服务端身份与对象授权]
  Identity --> Services[画像 课程 任务 资源 模型配置服务]
  Services --> DB[(PostgreSQL与pgvector)]
  Services --> Scheduler[单进程受控任务执行器]
  Scheduler --> Graph[LangGraph工作流]
  Graph --> Retriever[携带课程与用户上下文的检索入口]
  Retriever --> DB
  Graph --> Adapter[四类模型协议适配]
  Adapter --> Provider[用户选定的外部模型]
  Public[按课程维护的公共资料] --> Indexer[导入与索引]
  Indexer --> Embedding[部署方统一嵌入服务]
  Indexer --> DB
```

浏览器输入、模型输出、课程正文和未来上传内容均不能决定所有者或绕过授权。API从会话确定用户，服务层检查对象归属，检索限定课程及允许的可见性；模型凭据仅在服务端解密后用于所属用户的请求。

| 模块 | 拥有的责任 | 不拥有的责任 |
| --- | --- | --- |
| api | 请求校验、会话与授权入口、响应 | 自行编排模型节点 |
| services/repositories | 业务一致性、对象归属、事务和读写 | 信任客户端传入所有者 |
| tasks | 接收、限额、时限、状态、恢复 | 将未持久化结果标记成功 |
| agents/workflows与nodes | 规划、生成、核验、整理、受控纠错 | 更换用户身份或提升知识权限 |
| agents/providers | 协议转换、统一结果与错误 | 静默切换用户模型、泄露凭据 |
| agents/retrieval | 在授权范围内检索并返回可追溯依据 | 把不同用户材料混入上下文 |
| knowledge | 可共享、可定位的课程资料 | 保存个人上传和真实密钥 |

## 运行流程

```mermaid
sequenceDiagram
  participant U as 学生
  participant A as API与业务服务
  participant D as PostgreSQL
  participant W as 工作流
  participant M as 模型服务
  U->>A: 提交课程、画像版本、主题、类型、request_key
  A->>A: 鉴权、校验、查询幂等与容量
  A->>D: 保存任务快照及截止时间
  A-->>U: task_id和状态
  A->>W: 调度已受理任务
  W->>D: 在用户与课程范围检索可信依据
  W->>M: 规划与生成（共享剩余时间预算）
  M-->>W: 候选结构化内容
  W->>W: 校验结构、来源、内容与安全
  alt 核验通过
    W->>W: 整理并再次检查
    W->>A: 已核验结果
    A->>D: 同事务保存资源并提交completed
  else 核验未通过
    W->>W: 有预算时有限重生成，否则失败
    W->>A: 最终结果或错误
  end
  U->>A: 查询本人任务
  A-->>U: 服务端真实阶段、资源入口或错误
```

内容核验失败最多两次重生成；通信补试与内容重生成分开计数。任务总时限从受理开始包含排队、调用、核验及存储。无预算时不能启动新调用，迟到结果不能改变终态。

## 状态机

```mermaid
stateDiagram-v2
  [*] --> queued
  queued --> planning
  planning --> generating
  generating --> validating
  validating --> generating: 核验失败且仍可重试
  validating --> formatting
  formatting --> completed: 同事务保存成功
  queued --> failed
  planning --> failed
  generating --> failed
  validating --> failed
  formatting --> failed
  completed --> [*]
  failed --> [*]
```

所有非终态可因总时限、不可恢复故障或服务中断进入failed；completed和failed不可重新开启。手动重试创建关联原任务的新任务，默认沿用原画像快照；更换画像必须确认。

## 数据关系与存储职责

用户拥有会话、画像版本、任务、个人模型配置和资源访问权；课程关联公共资料和任务；每个成功任务对应一个资源；资源引用真实知识来源和生成时版本。任务创建后的画像、课程、主题及模型配置版本不随后续编辑回写。

资源保存与完成状态同事务；数据库唯一约束保护同用户request_key和单任务资源关系；条件更新保护终态。模型网络调用不持有长数据库事务。表结构及两个Alembic迁移已实现，见data-dictionary.md。

后续私有资料保存于非静态运行存储，片段、向量、来源、下载和缓存都保留相同用户与课程边界。嵌入模型变更需要新索引版本，不能把不同维度或不同模型空间的向量混用。

## 当前实现状态

前后端业务、数据库、工作流与检索代码已接通。真实PostgreSQL和HTTP/模型替身测试覆盖主链路，Chrome/Edge走查通过；真实模型、真实嵌入召回和人工内容验收尚未完成。详见implementation-v1.md和测试报告，不把替身成功等同于模型质量验收。
