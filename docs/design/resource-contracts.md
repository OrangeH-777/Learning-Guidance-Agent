# 三类资源结构契约

日期：2026-09-27。对应S1-08。可执行定义位于 `agents/schemas/resources.py`，测试样例位于 `tests/fixtures/resource_contracts.json`。

## 共同边界

三类资源使用 `resource_type` 区分：`lecture`、`exercise`、`mindmap`。共同字段为1—100个Unicode字符的 `title` 和非空且不重复的 `source_ids`。文本字段必须为非空字符串，额外字段被拒绝。

此处定义的是模型候选正文，模型不能提交用户归属、人工审核状态或任务完成状态。AI提示、真实模型与版本、资源归属及保存状态由工作流与业务服务添加。结构校验不等于内容核验：source_id是否真实、是否属于课程和当前用户可见范围，仍须由检索/核验服务检查。

## 字段

| 类型 | 必需结构 | 结构检查 |
| --- | --- | --- |
| lecture | learning_objectives、prerequisites、sections、examples、summary | 目标/先修/章节/实例列表非空，每章有heading和explanation，每例有title和content |
| exercise | questions | 至少一题，稳定question_id不重复，每题有题干、答案、analysis |
| mindmap | root | 根与每个节点有label，以children表示子节点，根至少一个分支 |

练习中的 `question_type` 为 `single_choice` 或 `short_answer`。单选题有至少两个带label/content的选项，选项label不重复，answer必须指向实际选项；简答题answer为文字。选择题答案是否正确、简答题是否存在多解，由内容核验另行判断。

`fixture:`开头的样例来源只用于结构测试，不是已核实的课程资料。它们不应被索引程序或资源发布路径接受为真实来源。当前尚未实现索引与发布，后续须用真实来源检查保证这一边界。

## 验证

```powershell
uv run --locked pytest tests/contract/test_resource_contracts.py -q
```

覆盖三类结构往返、缺少解析、空来源、非法答案选项、重复题号、空导图、超长标题及模型伪造human_pass/user_id等情况。以上测试不访问真实模型，不宣称内容质量已通过人工评审。
