# 公共课程知识

此目录只存放可供所有用户检索的公共课程资料。每门课程独立建目录，资料必须具有可核查来源和使用权限。当前 `data_structure/` 已有六个主题的原创教学摘要和参考出处，均标为待人工复核；未配置真实嵌入，开发库尚未建立真实知识索引。

已新增网站“公共教材管理”：管理员可上传 `.md`、文字版 `.pdf` 和 `.docx`，校对提取正文并确认后，系统自动生成下述 Markdown 与 YAML 配置。推荐直接按[管理员教材手册](../docs/manual/public-materials.md)操作。以下步骤用于手工维护课程目录；两条路径共用同一知识格式。

## 教材配置步骤（本地运行）

### 1. 整理正文

命令行目录导入器只读取 UTF-8 编码的 `.md` 文件，不会直接解析 PDF、Word、图片或自动抓取网页。请先将可使用的教材内容整理为 Markdown，或使用网站上传提取；扫描件需要先识别文字并校对公式、代码和表格。建议按章节分文件，以 Markdown 标题区分知识点。

数据结构教材放入 `knowledge/data_structure/content/`，例如 `textbook_ch01.md`。新增课程则建立 `knowledge/<course_id>/content/` 和对应 `course.yaml`。课程 ID 使用小写英文字母开头，后续只用小写字母、数字、下划线，最长64字符，且必须与文件夹名一致。

仅把文件放入目录不会导入：每个正文文件都需要在下面的 `sources` 中登记。`sources/` 目录只是预留，不会自动扫描原始教材。

### 2. 登记 course.yaml

已有课程请保留原配置，在 `sources` 列表末尾增加条目，并更新课程顶层 `version`。以下是独立课程配置的字段示例；创建时替换示例名称、来源链接、授权说明和负责人，勿覆盖现有数据结构配置：

```yaml
id: example_course
name: 示例课程名称
description: 本课程涵盖的知识范围
version: textbook-v1
enabled: true
maintainer: 实际课程维护者
topics:
  - 第一章主题
prerequisites: []
sources:
  - id: textbook_ch01
    title: 教材名称·第一章
    file: content/textbook_ch01.md
    source_url: https://example.com/replace-with-real-book-page
    section: 第一章，实际页码范围
    license: 填写实际授权或使用依据
    version: chapter-v1
    review_status: pending_human_review
```

所有示例字段均需保留，不能增加未定义字段。同一课程内来源 `id` 不可重复；`file` 是相对课程目录的路径，不得指向外部文件。`source_url` 必须是实际 HTTP(S) 来源地址，可用出版社的教材介绍页；它用于来源追溯，不会自动下载正文，不接受本地磁盘路径。

实际检查正文准确性和使用权限后，将对应来源的 `review_status` 改为 `approved`。默认索引要求所有条目均已批准。

### 3. 配置统一嵌入模型

在项目根目录已有 `.env` 中填写下列字段，保留原数据库和加密密钥配置：

```dotenv
EMBEDDING_PROTOCOL=openai_compatible
EMBEDDING_BASE_URL=https://YOUR_PROVIDER/v1
EMBEDDING_API_KEY=YOUR_KEY
EMBEDDING_MODEL=YOUR_EMBEDDING_MODEL
EMBEDDING_DIMENSIONS=YOUR_ACTUAL_INTEGER
EMBEDDING_INDEX_VERSION=knowledge-v1
```

替换全部占位值：地址是嵌入服务根路径，不含 `/embeddings`；模型必须支持嵌入，维度填写该模型实际输出的整数。目前嵌入适配支持 OpenAI 兼容的 embeddings 协议；个人聊天模型的四协议设置与此独立。当前适配器要求非空 API Key。本地/内网服务另需在 `.env` 的 `MODEL_ENDPOINT_ALLOWLIST` 中放行该服务的精确 origin。

应用在本机运行不等于模型也在本机。使用外部嵌入服务时，索引会发送教材正文并可能产生费用。索引版本首次可取 `knowledge-v1`，修改内容、元数据、切块配置或嵌入模型后应使用新版本。

### 4. 导入目录并建立索引

在项目根目录依次执行，数据库须已启动：

```powershell
uv run --locked alembic upgrade head
uv run --locked python -m scripts.import_courses
uv run --locked python -m scripts.index_knowledge data_structure
```

新课程将最后一条的 `data_structure` 替换为其目录 ID；每门课程分别运行索引命令。导入目录只更新课程信息，成功建立索引后才能检索。索引运行记录位于 `var/index-runs/`，失败记录只包含错误类型等诊断，不包含密钥。

仅在本地测试且接受未复核内容时，可显式执行：

```powershell
uv run --locked python -m scripts.index_knowledge data_structure --allow-unreviewed-preview
```

这个选项会真实写入向量并激活公共索引，所有用户均可能检索到；它不是只读预览，也不代表人工复核完成。

### 5. 启用与后续更新

保存 `.env` 并完成索引后，重启后端、刷新前端。在页面选择课程，配置并测试个人聊天模型、确认该课程画像，再生成资源并检查来源。

后续修改教材时，更新正文、来源 `version` 与课程顶层 `version`，设置新的 `EMBEDDING_INDEX_VERSION`，再次导入和建立索引。导入改变了课程顶层版本时会清除该课程的活动索引，需要重新构建；不要把导入成功当作检索已就绪。

**嵌入配置族是全局的，网站索引修订按课程独立生成**：网站日常教材更新只需重新建立该课程索引。CLI仍使用 `EMBEDDING_INDEX_VERSION` 原值作为版本，变更此值时，所有需要继续使用的课程都必须在新配置族下完成索引。建议暂停新生成请求后统一更新，避免一部分课程仍指向旧配置族而无法检索。历史资源引用的旧片段会保留。

放在本目录的教材属于所有用户共享的公共知识。个人私有教材上传尚未实现，留待 S12；不要把私有材料放在这里。

## 目录与检索约定

```text
knowledge/
  data_structure/
    course.yaml    # 课程、来源、章节、版本、审查状态
    content/       # 经核对的知识正文
    sources/       # 附加来源文件预留；主来源记录已在course.yaml中
  <course_id>/     # 后续确认课程后使用同样结构
    content/
    sources/
```

首期系统按多课程设计；YAML＋Markdown已确认。课程ID须与文件夹一致，正文路径只能解析到该课程目录内部。用户尚未指定第二门实际课程；测试中的 test_course 只是隔离测试数据，不加入正式目录。缺少可信材料或索引未就绪的课程不能显示为可正常生成。

公共知识与私人材料必须分开：用户上传内容属于运行数据，保存在受控私有存储中，不能写入本目录、前端静态目录或版本仓库。私有存储的部署方式在上传功能设计时确认，配置入口预留为 `PRIVATE_UPLOAD_DIR`。

后续检索必须先确定已登录用户与所选课程，只允许访问该课程的公共条目及当前用户拥有的私有条目。来源详情、文件读取、片段预览、缓存及生成引用使用相同权限边界。目录名称和客户端提交的用户ID不能代替服务端授权。

部署方统一配置嵌入模型。索引记录模型、维度、资料版本与索引版本，切换嵌入模型须重建；个人聊天模型切换不改变嵌入配置。已实现可配置段落切块和精确余弦检索；开发默认1200字符/top-k6/距离0.8，仍需真实召回评审；中文关键词仅保留接口。

先执行 `python -m scripts.import_courses` 导入目录，再配置嵌入并执行 `python -m scripts.index_knowledge data_structure`。默认拒绝未approved的材料；开发预览必须显式传 `--allow-unreviewed-preview`，不能借此冒称人工通过。失败运行记录在忽略目录 `var/index-runs/`，旧活动索引不会因新构建失败而被覆盖。
