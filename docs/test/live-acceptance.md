# 真实课程验收与人工复核

本流程对应S9-08—11。当前未执行真实模型批次；下列命令和模板是准备材料，不是通过记录。

## 执行条件与原始记录

先配置真实聊天/嵌入模型及费用额度，复核课程资料并完成正式索引，使用专用验收账号确认画像及个人模型。只能连接实际应用服务；8001浏览器替身服务不得用于真实质量验收。非回环应用地址必须使用HTTPS。

在项目根目录执行一次完整批次：

```powershell
uv run --locked python -m scripts.run_course_acceptance --username YOUR_TEST_USER --acknowledge-costs
```

执行集DS01—30类型各10条。每条先保存首次记录，再受理任务；任何失败、断网、拒绝或中断都保留，不能删掉后重跑来替换。DS任务卡引用这一批次，不要对每张卡再执行一遍全部30条。手动重试属于独立记录，不能合入首次分母。

报告位于忽略目录`tests/results/live-*.json`，包含主题、画像、个人模型版本、受理/截止/结束时间、内容重生成次数、聊天调用遥测、知识/提示词版本、成功资源及来源ID。未获提供方token统计时保持null；不估造费用。`local_artifact_sha256`标识运行脚本本地锁文件/执行集，不能冒充远程服务的部署版本，远程部署还须另行登记其代码版本。

报告可能包含课程正文和专用测试画像，应按本地验收材料保管，不能直接公开上传。脚本不记录密码、CSRF或模型密钥。已观察到completed后读取详情断网只记observation_error，不覆盖已知终态；尚未观察到终态的断网记录必须核对原task_id后再统计，不能把未知状态改写成失败。

## 人工复核材料

对每个成功的首次资源，复核主题、结构、难度、事实、答案解析或导图关系，并记录复核者、日期、依据与缺陷。最后一个维度对讲解/导图评价推导和层级关系，不能因不是练习而省略。

将复核结果保存在本地JSON；以下只是字段模板，null必须由实际复核者填写为true或false，空姓名/依据或不完整判断会被统计工具拒绝：

```json
{
  "run_id": "从实际批次复制",
  "reviews": [
    {
      "case_id": "DS01",
      "resource_id": "对应首次任务成功资源的实际ID",
      "reviewer": "",
      "reviewed_at": "2026-09-28",
      "evidence": "",
      "judgments": {
        "topic": null,
        "structure": null,
        "difficulty": null,
        "facts": null,
        "answer_or_relationship": null
      }
    }
  ]
}
```

模板不构成人工通过，模型的safe/facts_correct或资源中的human_pass字段都不能替代这里的复核证据。统计工具核对批次、资源ID和完整性，不证明填写人的身份或判断真实有效；正式验收仍由负责人核实。

## 统计

```powershell
uv run --locked python -m scripts.summarize_acceptance tests/results/live-ACTUAL_RUN.json --reviews tests/results/reviews-ACTUAL_RUN.json
```

未提供`--reviews`时只显示客观任务结果，人工合理性为待复核。总体首次成功率分母固定30，各类型固定10；记录不足或有未知终态时不报告最终成功率。成功资源必须带实际task_id、resource_id和不超180秒的带时区任务时间。重复编号、错误类型、手动重试混入首次批次或超时后声称成功的记录都会被拒绝。

合理性分母为成功的首次资源数量；全部适用维度通过才计通过。任一成功资源尚未复核时不提前报告最终合理性率；无成功资源时记not_applicable。统计不改写原报告、人工复核输入或数据库，也不自动签署human_pass。

出现缺陷后保留原记录，另建整改和复测批次。目标90%只是验收目标，实际值由真实记录计算，不能拿单元测试中的test_fixture统计作为真实测量。
