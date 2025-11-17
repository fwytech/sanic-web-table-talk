# 项目使用文档（Sanic Web）

版本：v1.0.0  
更新时间：2025-11-17

## 版本历史
- v1.0.0：首版，包含部署指南、操作手册、API示例、故障排查与运维监控。

## 目录结构
- 系统部署指南
- 功能操作手册（分角色）
- API 调用示例
- 常见问题排查
- 运维监控指南

## 系统部署指南
### 环境要求
- 操作系统：Windows 10/11 或 Linux/Mac（Docker 24+，Compose v2+）
- Python：`>=3.11,<3.12`（后端开发环境）
- Node：`>=18`（前端开发环境）
- 容器：Docker 与 Docker Compose

### 依赖安装（本地开发）
- 后端
  - 安装 uv 并创建虚拟环境：
    - `uv venv --clear`
    - `./.venv/Scripts/activate`（Windows）或 `source .venv/bin/activate`（Unix）
    - `uv sync --no-cache`
  - 编辑 `.env.dev`（至少：`JWT_SECRET_KEY`、数据库/MinIO、模型/Dify 等）
  - 启动：`python serv.py`（端口 `SERVER_PORT`，默认 8088；参见 `serv.py:24-30`）
- 前端
  - `cd web && pnpm i && pnpm dev`（开发地址 `http://localhost:2048`，Vite 代理 `/sanic` 到后端）

### 容器部署（Docker Compose）
- 入口文件：`docker/docker-compose.yaml:1-116`，包含：
  - `chat-web`（Nginx）：端口 `8081`；加载模板 `./nginx.conf.template`
  - `chat-service`（后端）：端口映射 `${SERVER_PORT:-8089}`；读取环境变量（`SERVER_*`、`SQLALCHEMY_DATABASE_URI`、`MINIO_*`、`JWT_SECRET_KEY` 等）
  - `minio`：端口 `19000/19001`（默认用户 `admin/12345678`）
  - （可选）`mysql`、`mcphub`、`gpt-vis-api`、`neo4j-apoc`
- 启动命令：
  - `cd docker && docker compose up -d`
- 访问：
  - 前端生产：`http://localhost:8081`
  - 后端服务：通过 Nginx 反代 `/sanic` 到 `chat-service:${SERVER_PORT}`
  - MinIO 控制台：`http://localhost:19001`

### 配置说明（表格）
| 类别 | 键 | 示例 | 说明 |
|---|---|---|---|
| 服务器 | `SERVER_HOST` | `0.0.0.0` | 监听地址（`serv.py:24-30`） |
| 服务器 | `SERVER_PORT` | `8088/8089` | 服务端口（本地/容器） |
| 服务器 | `SERVER_WORKERS` | `2` | Sanic worker 数 |
| 数据库 | `SQLALCHEMY_DATABASE_URI` | `mysql+pymysql://...` | ORM 连接 URI（`model/db_connection_pool.py:40-51`） |
| 数据库 | `MYSQL_*` | `HOST/PORT/USER/PASSWORD/DATABASE` | 原生连接参数（如使用 `common/mysql_util.py`） |
| 存储 | `MINIO_ENDPOINT` | `127.0.0.1:19000` | MinIO API 地址 |
| 存储 | `MINIO_ACCESS_KEY` | `admin` | MinIO 用户 |
| 存储 | `MiNIO_SECRET_KEY` | `12345678` | MinIO 密码（注意拼写） |
| 存储 | `MINIO_BUCKET` | `files` | 默认桶名 |
| 安全 | `JWT_SECRET_KEY` | `******` | Token 加密密钥（`common/token_decorator.py:23-23`） |
| 外部 | `DIFY_SERVER_URL` | `http://...` | Dify Canvas 地址 |
| 外部 | `DIFY_DATABASE_QA_API_KEY` | `sk-...` | Dify API Key |
| 外部 | `MCP_HUB_*_GROUP_URL` | `http://...` | MCP-Hub 组地址 |
| LLM | `MODEL_BASE_URL` | `http://...` | 模型服务地址 |
| LLM | `MODEL_NAME` | `gpt-4o-mini` | 模型名 |
| LLM | `MODEL_API_KEY` | `sk-...` | 模型密钥 |
| LLM | `MODEL_TEMPERATURE` | `0.3` | 采样温度 |

## 功能操作手册（分角色）
### 普通用户
- 登录：在登录页输入用户名/密码，成功后在前端存储 Token（`POST /user/login`）
- 发起问答：
  - 通用智能问答（Dify 流式）：输入问题，收到流式回答；可查看溯源与任务ID（事件类型见 `constants/code_enum.py:48-56`）
  - 数据问答（Text2SQL）：输入问题后端将解析并执行 SQL，返回数据表/统计结果
  - 文件问答：上传文件→解析→选择列→发起问答，返回文件表级别数据
- 聊天记录：查看历史记录、搜索与删除
- 反馈评分：对聊天记录点赞/评分

### 管理员
- 配置：检查 `.env.{env}` 与容器环境变量；确保 `JWT_SECRET_KEY`、`MINIO_*`、数据库与 Dify Key 正确
- 资源：维护 MinIO 桶与权限；数据库连接与账号安全
- 监控：查看日志文件与容器健康状态；异常时定位控制器与服务调用链

## API 调用示例
### 登录并获取 Token（cURL）
```bash
curl -X POST http://localhost:8088/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo"}'
```
响应：`{"code":200,"msg":"ok","data":{"token":"..."}}`

### 携带鉴权访问（JS fetch）
```js
const token = "...";
const res = await fetch("http://localhost:8088/user/query_user_record", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ page: 1, limit: 20, search_text: "", chat_id: null })
});
const data = await res.json();
```

### Dify 流式 SSE（浏览器）
```js
const token = "...";
const es = new EventSource("http://localhost:8088/dify/get_answer", { withCredentials: false });
es.onmessage = (e) => { console.log(e.data); };
// 注意：生产环境通过 Nginx 反代为 /sanic/dify/get_answer
```

### Text2SQL（Python requests）
```python
import requests
url = "http://localhost:8088/llm/process_llm_out"
res = requests.post(url, data={"llm_text": "select * from users limit 10"})
print(res.json())
```

### 文件上传与解析（cURL）
```bash
curl -X POST http://localhost:8088/file/upload_file_and_parse \
  -F file=@./sample.xlsx
```
响应：`{"code":200,"msg":"ok","data":{"excel_key":"..."}}`

## 常见问题排查
- 401 无效 Token（`common/token_decorator.py:14-32`）
  - 现象：未携带 `Authorization` 或密钥不匹配
  - 处理：检查 `JWT_SECRET_KEY` 与前端存储；确认 `Bearer <token>` 格式
- MinIO 访问失败
  - 现象：获取文件 URL 报错或上传失败
  - 处理：核查 `MINIO_ENDPOINT/ACCESS_KEY/MiNIO_SECRET_KEY` 与桶权限；检查容器端口 `19000/19001`
- 数据库连接错误
  - 现象：SQL 执行超时或连接拒绝
  - 处理：校验 `SQLALCHEMY_DATABASE_URI`；调整连接池参数（`model/db_connection_pool.py:43-51`）；容器 `mysql` 是否启动
- Dify 返回异常
  - 现象：SSE 中出现 `error` 事件
  - 处理：检查 `DIFY_SERVER_URL` 与 API Key；查看服务端错误日志
- 前后端跨域/代理问题
  - 现象：开发模式接口无法访问
  - 处理：确认 Vite 代理指向 `http://localhost:8088`；生产确认 Nginx `/sanic` 反代配置

## 运维监控指南
- 日志查看
  - 后端：`logs/assistant.log` 按日滚动（配置见 `config/logging.conf`）；请求/响应日志在统一装饰器输出（`common/res_decorator.py:67-71,80-94`）
- 健康检查
  - `GET /`（`serv.py:21-21`）占位；容器层面查看 `chat-service`/`chat-web` 状态
- 关键环境核查清单
  - `SERVER_*`、`JWT_SECRET_KEY`、数据库与 MinIO、Dify 与 LLM Key、MCP-Hub 组地址
- 性能监测建议
  - 记录接口耗时与错误率；SSE 首包时间；根据负载调整 `SERVER_WORKERS` 与 DB 连接池参数

---
图例与接口更完整的字段说明可与《项目需求文档》交叉参考，所有示例以代码事实为准（已在文档中标注文件与行号）。