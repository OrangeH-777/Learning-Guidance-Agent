# 需求与测试追踪

2026-09-28。原始 IT/TC/DS 始终保留在 `acceptance_baseline.json`；原始 execution_status 不回写，防止混淆原始规格和运行结果。用户已批准执行集 DS13 的10/10/10调整，见 `acceptance_execution.json`。

## 现有自动化证据

| 需求/场景 | 可执行证据 | 验证边界 |
| --- | --- | --- |
| R01；TC001—006、044、046 | test_accounts_profiles.py、test_input_contracts.py、浏览器learning.spec.ts | 真实数据库账号/会话/撤销；浏览器注册退出；并非所有原步骤逐条正式签收 |
| R02；TC007—014 | test_input_contracts.py、test_profile_course_and_user_isolation、test_conversation_is_draft_until_user_confirms | 字段边界、版本、草稿、冲突；提取正确性使用模型替身，真实自然语言仍待测 |
| R03/R04；TC015、019、021—028 | test_resource_contracts.py、test_learning_workflow.py、test_generation_flow.py | 三类型结构、来源、事务、历史；真实个性化差异和课程合理性尚待人工 |
| R05；TC029、031、033—039、048—049、051、054 | test_task_runtime.py、test_task_reliability.py、test_generation_flow.py | 时限预算、重试上限、终态、并发幂等、容量、恢复、保存回滚；计时边界用缩短预算故障注入 |
| R06；TC040—043 | test_history_stable_pagination_filters_and_invalid_bounds、浏览器流程 | 12资源10/2分页、同时间稳定排序、筛选、上限、隔离与快照 |
| R07；TC047、052—056 | test_model_protocols.py、test_fact_and_security.py、test_learning_workflow.py、浏览器DOM注入 | 错误脱敏、URL/DNS策略、已知事实错误、来源阻断、核验异常、DOM不执行脚本；非完备内容安全证明 |
| R09 多课程 | test_profile_course_and_user_isolation、test_vector_query_enforces_user_course_and_index_before_ranking、test_disabled_course_keeps_history_and_sources_but_refuses_new_tasks、浏览器课程切换 | 使用test_course验证画像/草稿隔离、无索引阻断；停用课程仍可读历史和来源，未宣称已有第二门正式课程 |
| R10 四类协议/个人设置 | test_model_protocols.py、test_model_key_encryption_versions_and_user_isolation | 四类HTTP契约、鉴权头、停止条件、错误与密钥版本；真实厂商兼容性未验收 |
| R11 索引与检索 | test_knowledge_index.py | 真实pgvector写入、过滤与排序，替身向量；同版重复、新版保留旧来源；相关性需真实向量模型 |
| TC050 非生成负载 | test_load.py；tests/results/load.json | 10会话/100历史/100请求，ASGI TestClient＋真实PostgreSQL，不含网络与模型延迟 |
| TC057 浏览器 | frontend/e2e/learning.spec.ts | Chrome/Edge完整流程、窄屏、键盘、DOM脚本不执行；人工全场景走查未签收 |
| TC058 第二人复现 | README、操作手册 | 步骤已写，尚无第二人执行 |
| TC059—060、DS01—30 | scripts.run_course_acceptance、修订执行集 | 可显式执行真实服务批次；本轮未配置服务/额度，30条首次结果与人工打分均未产生 |

补充2026-09-28：`test_two_executing_jobs_and_queued_deadline`验证实际同时执行数、重复投递与排队超时；`test_unavailable_prompt_version_fails_without_model_call`验证提示词版本不可用时不调用模型；成功/失败生成测试断言遥测耗时、版本和凭据隔离；`test_test_database_guard.py`验证破坏性测试库隔离守卫。浏览器补测刷新后显式恢复草稿、取消修改和课程切换，画像版本保持不变。

继续实施补充：`test_api_responses.py`校验20个业务操作的成功/错误契约，内部响应异常不回显私密字段；`test_executor_failures.py`验证失败终态、取消后迟到响应、数据库故障补记；`test_output_security.py`验证注入文本只作为数据、模型不能赋予human_pass、外发消息不含账号/密码/密钥。`failure-states.spec.ts`覆盖加载、空态、503、断网退出及401；主流程新增历史筛选返回。

98张逐项任务卡位于`tests/acceptance/tasks.yaml`，以原始规格和已确认DS13修订生成。运行`python -m scripts.prepare_acceptance_tasks --check`检查完整性；每张卡含前置条件、原输入和预期、支持性命令、实际结果记录字段。支持性自动测试通过不会自动把整张TC/IT或人工验收标为通过。

## 交付追踪核对

| 需求 | 实现/设计入口 | 用户说明 | 尚缺的最终验收 |
| --- | --- | --- | --- |
| R01 | auth.py、dependencies.py、实现说明“认证” | 用户手册“账号与课程” | 第二人复现与团队签收 |
| R02 | profiles.py、conversations.py、ProfileView | 用户手册“学习画像” | 真实提取语义及冲突样例 |
| R03 | tasks.py、generation.py、learning.py | 用户手册“生成、失败与重试” | 两种画像真实个性化效果 |
| R04 | resources.py、资源契约、ResourceView | 用户手册“阅读与历史” | DS30内容人工质量 |
| R05 | runtime.py、state.py、executor.py | 用户手册异常说明、运行手册 | 真实服务网络/现场演练 |
| R06 | resources.py、HistoryView | 用户手册“阅读与历史” | 团队签收 |
| R07 | sources.py、data_structure.py、model_nodes.py | AI提示、来源与限制说明 | 课程依据复核、真实模型注入/事实质量 |
| R09 | catalog.py、profiles.py、多课程外键/查询 | 课程/画像/历史说明 | 第二实际课程及其验收材料 |
| R10 | http.py、models.py、响应契约 | 用户手册“个人模型” | 四种协议实际服务范围 |
| R11 | indexing.py、embedding.py、vector.py | README嵌入配置、运行手册索引版本 | 真实嵌入、召回参数评审 |
| R12 | 当前只预留所有者/可见性及SQL隔离 | 明确个人上传未开放 | S12专项设计和实现，按此前确认后期安排 |

上述核对完成“需求—实现—测试—用户说明”对应关系，不代表全部功能已通过外部服务及人工门禁。R08/S13仍遵循单独范围决定。

未把上表的单项相似自动化场景改写为“TC001—060全部通过”。TC017语义范围、TC020真实画像差异、TC030/032刷新断网的完整时间观测、TC047全环境日志审计、所有真实模型内容类断言仍需要专项补测或人工核验。

## IT集成任务

IT01—08继续按原始规格执行，现有可复用证据分别来自认证/画像接口、完整生成、状态机/时限、异常恢复、来源、资源历史和浏览器流程。任何包含真实模型、人员确认或完整外部故障演练的IT尚不整体标“通过”。执行人应把每个原始步骤映射到具体报告，不以测试数代替集成验收。

## 真实课程质量记录模板

每个DS首次任务记录：case_id、task_id、course_id、主题、类型、画像版本、模型、嵌入与提示词版本、开始/截止/结束时间、内部重试、最终状态和错误。失败不得替换；手动重试另列 parent_task_id。

每个成功资源人工记录：主题、结构、难度、事实、答案解析/逻辑关系；各项判定、依据、复核者、日期和问题。仅全部适用维度通过才计human_pass；不得由模型或脚本自动签署人工通过。

首次成功率分母固定30，目标90%；合理性分母为首次成功资源数，目标90%，无成功资源时记不适用。各类型独立统计，新课程单列，不混入数据结构分母。当前真实测量值全部为“未执行”。
