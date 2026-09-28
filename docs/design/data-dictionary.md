# 数据字典

由 `python -m scripts.export_contracts` 从当前 SQLAlchemy 模型生成。时间使用带时区 UTC，展示转换为北京时间。

## courses

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| id | VARCHAR(64) | False | True | — |
| name | VARCHAR(100) | False | False | — |
| description | TEXT | False | False | — |
| enabled | BOOLEAN | False | False | — |
| content_version | VARCHAR(100) | False | False | — |
| active_index_version | VARCHAR(100) | True | False | — |

## users

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| username | VARCHAR(20) | False | False | — |
| password_hash | TEXT | False | False | — |
| is_admin | BOOLEAN | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |

## knowledge_documents

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| course_id | VARCHAR(64) | False | False | courses.id |
| owner_id | CHAR(32) | True | False | users.id |
| visibility | VARCHAR(10) | False | False | — |
| source_key | VARCHAR(200) | False | False | — |
| title | TEXT | False | False | — |
| locator | TEXT | False | False | — |
| license | TEXT | False | False | — |
| content_hash | VARCHAR(64) | False | False | — |
| version | VARCHAR(100) | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |

## login_sessions

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| user_id | CHAR(32) | False | False | users.id |
| token_hash | VARCHAR(64) | False | False | — |
| csrf_token | VARCHAR(128) | False | False | — |
| expires_at | DATETIME | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |

## model_configurations

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| user_id | CHAR(32) | False | False | users.id |
| version | INTEGER | False | False | — |
| protocol | VARCHAR(32) | False | False | — |
| base_url | TEXT | False | False | — |
| model_id | VARCHAR(200) | False | False | — |
| encrypted_key | TEXT | False | False | — |
| tested_at | DATETIME | True | False | — |
| retired | BOOLEAN | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |

## profile_drafts

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| user_id | CHAR(32) | False | False | users.id |
| course_id | VARCHAR(64) | False | False | courses.id |
| revision | INTEGER | False | False | — |
| fields | JSON | False | False | — |
| messages | JSON | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |

## profile_revisions

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| user_id | CHAR(32) | False | False | users.id |
| course_id | VARCHAR(64) | False | False | courses.id |
| version | INTEGER | False | False | — |
| fields | JSON | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |

## generation_tasks

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| user_id | CHAR(32) | False | False | users.id |
| course_id | VARCHAR(64) | False | False | courses.id |
| request_key | VARCHAR(64) | False | False | — |
| request_digest | VARCHAR(64) | False | False | — |
| parent_task_id | CHAR(32) | True | False | generation_tasks.id |
| status | VARCHAR(20) | False | False | — |
| topic | VARCHAR(100) | False | False | — |
| resource_type | VARCHAR(20) | False | False | — |
| profile_version | INTEGER | False | False | — |
| profile_snapshot | JSON | False | False | — |
| model_configuration_id | CHAR(32) | False | False | model_configurations.id |
| knowledge_version | VARCHAR(100) | False | False | — |
| prompt_version | VARCHAR(100) | False | False | — |
| deadline_at | DATETIME | False | False | — |
| finished_at | DATETIME | True | False | — |
| error_code | VARCHAR(40) | True | False | — |
| content_regenerations | INTEGER | False | False | — |
| telemetry | JSON | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |

## knowledge_chunks

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| document_id | CHAR(32) | False | False | knowledge_documents.id |
| ordinal | INTEGER | False | False | — |
| locator | TEXT | False | False | — |
| content | TEXT | False | False | — |
| index_version | VARCHAR(100) | False | False | — |
| embedding_model | VARCHAR(200) | False | False | — |
| dimensions | INTEGER | False | False | — |
| embedding | VECTOR | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |

## resources

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| task_id | CHAR(32) | False | False | generation_tasks.id |
| user_id | CHAR(32) | False | False | users.id |
| course_id | VARCHAR(64) | False | False | courses.id |
| topic | VARCHAR(100) | False | False | — |
| resource_type | VARCHAR(20) | False | False | — |
| content | JSON | False | False | — |
| metadata_snapshot | JSON | False | False | — |
| source_ids | JSON | False | False | — |
| human_pass | BOOLEAN | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |

## validation_records

| 字段 | 类型 | 可空 | 主键 | 外键 |
| --- | --- | --- | --- | --- |
| task_id | CHAR(32) | False | False | generation_tasks.id |
| attempt | INTEGER | False | False | — |
| passed | BOOLEAN | False | False | — |
| checks | JSON | False | False | — |
| id | CHAR(32) | False | True | — |
| created_at | DATETIME | False | False | — |
