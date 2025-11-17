# 项目需求文档（Sanic Web）

版本：v1.0.0  
更新时间：2025-11-17

## 版本历史
- v1.0.0：首版，完成功能规格、技术架构、数据流、接口规范与性能SLA。

## 目录结构
- 项目概览
- 功能规格说明
- 技术架构设计
- 数据流设计
- 接口规范
- 性能指标要求（SLA）

## 项目概览
- 类型：后端服务（Sanic）+ 前端（Vue3），容器化部署（Docker Compose）
- 入口：`serv.py:10-35` 加载环境与日志，创建 `Sanic("sanic-web")` 并自动注册蓝图，根路由 `"/"` 返回空（`serv.py:21-21`）
- 统一响应：`common/res_decorator.py:33-96` 封装 `{"code","msg","data"}`，捕获异常并记录请求/响应日志
- 鉴权：`common/token_decorator.py:8-37` 校验 `Authorization: Bearer <token>`，读取 `JWT_SECRET_KEY`
- 主要控制器：
  - 用户：`controllers/user_service_api.py:19-39,41-83`
  - Dify：`controllers/dify_chat_api.py:17-58`
  - 数据问答：`controllers/db_chat_api.py:14-36,39-51`
  - 文件：`controllers/file_chat_api.py:16-100`
- 数据层：`model/db_connection_pool.py:21-100` 单例连接池（SQLAlchemy）；同时存在原生 `pymysql`（见 `common/mysql_util.py`）
- 配置加载：`config/load_env.py:7-23`；容器环境变量见 `docker/docker-compose.yaml:33-61`

## 功能规格说明（按模块）
### 用户模块
- 登录认证：校验用户名/密码，生成 JWT Token（`controllers/user_service_api.py:19-39`）
- 聊天记录分页查询：需鉴权，支持搜索与按会话ID过滤（`controllers/user_service_api.py:41-56`）
- 聊天记录删除：需鉴权，批量删除（`controllers/user_service_api.py:58-69`）
- 聊天反馈评分：需鉴权，按 `chat_id` 提交 `rating`（`controllers/user_service_api.py:72-83`）

### Dify 交互模块
- 流式回答（SSE）：根据问题与上下文返回 `text/event-stream`（`controllers/dify_chat_api.py:17-31`）
- 问题建议：根据 `chat_id` 返回候选建议（`controllers/dify_chat_api.py:34-45`）
- 停止聊天：根据 `task_id` 与 `qa_type` 终止任务（`controllers/dify_chat_api.py:47-58`）

### 数据问答（Text2SQL）
- 数据问题到 SQL：接收 LLM 输出文本，执行 SQL 并返回结果（`controllers/db_chat_api.py:14-36`）
- 报告查询：根据标题关键字检索报告（`controllers/db_chat_api.py:39-51`）

### 文件问答/管理
- 文件上传：接收附件上传到 MinIO，返回文件 Key（`controllers/file_chat_api.py:56-66`）
- 上传并解析：解析多格式（Word/PDF/Excel/CSV）并返回内容 Key 集合（`controllers/file_chat_api.py:68-77`）
- 读取文件首行/列：按文件 Key 读取 Excel 首行/列（`controllers/file_chat_api.py:16-53`）
- 文件问题到 SQL：根据文件 Key 与 LLM 输出执行 SQL（`controllers/file_chat_api.py:80-100`）

### 通用搜索
- 返回搜索引擎首条结果链接（见 `controllers/common_chat_api.py`，文档阶段统一整理）

## 技术架构设计
### 分层架构
- 表示层：Sanic 蓝图（Controllers）
- 业务层：Services（用户、Dify、Text2SQL、文件等）
- 通用层：Common（响应、鉴权、MinIO、LLM、解析等）
- 数据层：Model（SQLAlchemy 连接池与 ORM 模型）+ 原生 `pymysql` 封装
- 外部系统：MinIO、Dify Canvas、数据库、MCP-Hub、Neo4j

### 技术栈选型
- Web 框架：Sanic（异步高性能）
- 数据访问：SQLAlchemy 2.x + 会话池；部分路径使用 `pymysql`（历史与便捷性）
- 存储：MinIO（对象存储，适配文件解析与访问）
- 认证：JWT（`pyjwt`）
- LLM 生态：OpenAI/Qwen（`langchain`/`langgraph` 等）
- 部署：Dockerfile + Docker Compose；Nginx 反向代理前后端

## 数据流设计（示意图）
- 登录鉴权流：前端→`POST /user/login`→生成Token→前端持有→受保护接口携带 `Authorization`
- Dify SSE 流：前端→`POST /dify/get_answer`（鉴权）→`ResponseStream` 推流→前端 `EventSource` 消费
- 文件上传解析流：前端→`POST /file/upload_file_and_parse`→MinIO→解析器→返回多 Key（内容/表格/文本等）
- Text2SQL 执行流：前端→`POST /llm/process_llm_out`→解析 SQL→数据库执行→返回数据集
- 图参考：`docs/diagrams/architecture.drawio`、`docs/diagrams/dataflows/*.drawio`（提交时附 PNG）

## 接口规范
### 设计原则
- 一致性：REST 风格；SSE 用 `text/event-stream`
- 统一响应：`{"code": number, "msg": string, "data": any}`；错误统一枚举（`constants/code_enum.py:4-15`）
- 鉴权：受保护接口必须携带 `Authorization: Bearer <token>`（`common/token_decorator.py:13-35`）
- 日志：请求/响应在装饰器中统一打点（`common/res_decorator.py:67-71,80-94`）

### 主要接口定义
- `POST /user/login`：请求 `{username,password}`；响应 `{token}`
- `POST /user/query_user_record`（鉴权）：`{page,limit,search_text?,chat_id?}`；响应 `{list,total,...}`
- `POST /user/delete_user_record`（鉴权）：`{record_ids: number[]}`；响应 `{success: true}`
- `POST /user/dify_fead_back`（鉴权）：`{chat_id,rating}`；响应 `{success: true}`
- `POST /dify/get_answer`（鉴权）：SSE；事件序列按 `DiFyCodeEnum` 定义（`constants/code_enum.py:48-56`）
- `POST /dify/get_dify_suggested`（鉴权）：`{chat_id}`；响应 `string[]`
- `POST /dify/stop_chat`（鉴权）：`{task_id,qa_type}`；响应 `{success: true}`
- `POST /llm/process_llm_out`：`form{llm_text}`；响应 `rows/columns`
- `GET /llm/query_guided_report`：`?query_str=`；响应 `list`
- `POST /file/upload_file`：`multipart/form-data`；响应 `file_key`
- `POST /file/upload_file_and_parse`：`multipart/form-data`；响应 `{..._key_dict}`
- `POST /file/read_file|read_file_column`：`{file_qa_str}`；响应 `string[]`
- `POST /file/process_file_llm_out`：`?file_key=` + body 为 LLM 输出；响应 `rows/columns`

## 性能指标要求（SLA）
- 普通 JSON 接口：
  - P50 ≤ 300ms；P95 ≤ 800ms；错误率 ≤ 0.5%
  - 并发能力：单实例（`workers=2`，DB池=10）目标 150–300 RPS（轻负载），视查询复杂度而定
- SSE 接口：
  - 首包时间 ≤ 1.5s；完整回答时间按模型与上下游而定；服务记录推流起止与事件类型
- 压测与调优建议：
  - 通过增加 `SERVER_WORKERS`、调大 DB `pool_size/max_overflow`（`model/db_connection_pool.py:43-51`）进行扩容
  - 建议按接口维度记录耗时分布，结合 Nginx/前端端到端监测

---
（图与更细化的请求/响应示例在《项目使用文档》与 `docs/diagrams/*` 中配套提供）