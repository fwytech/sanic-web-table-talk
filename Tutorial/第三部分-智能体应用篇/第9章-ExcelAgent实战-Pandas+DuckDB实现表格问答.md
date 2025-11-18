# 第9章 Excel Agent实战——Pandas + DuckDB实现表格问答

## 本章目标

1. 掌握Pandas动态读取Excel/CSV文件并映射为虚拟数据库表的核心技术
2. 理解DuckDB内存数据库在BI场景中的零配置优势与性能特点
3. 学会构建从文件上传→结构解析→SQL生成→结果可视化的完整数据流
4. 深入理解会话记忆机制如何避免用户重复上传文件

---

## 一、为什么需要Excel Agent?

### 1. 业务痛点

在实际业务中,大量数据分析师、运营人员习惯使用Excel/CSV存储业务数据:

- **销售报表**: 月度销售数据.xlsx
- **用户反馈**: 客户投诉统计.csv
- **财务对账**: 供应商账单明细.xls

**传统困境**:

1. 这些人员**不会写SQL**,只能手工筛选、透视表操作
2. 数据量超过10万行时Excel卡顿甚至崩溃
3. 每次分析需求都要重复"导入数据库 → 建表 → 写SQL"三步走

### 2. Excel Agent的核心价值

```
用户自然语言提问: "统计每个省份的销售额排名前5的商品"
           ↓
    Excel Agent自动完成:
    1. 解析Excel文件为虚拟表
    2. 生成SQL: SELECT 省份, 商品名称, SUM(销售额) ... GROUP BY ... ORDER BY ... LIMIT 5
    3. 在DuckDB内存中执行(无需建真实表)
    4. 返回图表 + 数据
```

**核心优势**:

- **零配置**: 无需导入MySQL/PostgreSQL,上传即查
- **零学习成本**: 业务人员用自然语言提问
- **零数据迁移**: 文件保持原样,分析结束即销毁

---

## 二、DuckDB vs 传统数据库: 为什么选择DuckDB?

### 1. 技术对比

| 维度 | MySQL/PostgreSQL | DuckDB |
|------|------------------|--------|
| **启动方式** | 需要独立进程(服务端-客户端架构) | 嵌入式,随Python进程启动 |
| **数据导入** | 需要CREATE TABLE + INSERT/LOAD DATA | 直接注册Pandas DataFrame |
| **内存占用** | ~100MB基础开销 | ~10MB(按需分配) |
| **OLAP性能** | 针对OLTP优化,分析查询较慢 | 列式存储,聚合查询快10-100倍 |
| **临时分析** | 需要手动清理临时表 | 连接关闭自动释放 |

### 2. 关键代码实现

**agent/excel/excel_excute_sql.py**(第45-50行):

```python
# 连接到DuckDB (这里使用内存数据库) 并注册DataFrame
con = duckdb.connect(database=":memory:")

# 注册DataFrame - 核心亮点!
table_name = state["db_info"]["table_name"]
con.register(table_name, df)  # df是Pandas读取的Excel数据
```

**设计亮点**:

- `:memory:` 表示纯内存数据库,查询速度极快
- `con.register()` 直接把Pandas DataFrame注册为虚拟表,无需任何DDL语句
- 连接对象销毁时自动释放内存,无需手动清理

---

## 三、Excel Agent完整工作流

### 1. LangGraph工作流定义

**agent/excel/excel_graph.py**(完整56行):

```python
import logging

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from agent.excel.excel_agent_state import ExcelAgentState
from agent.excel.excel_excute_sql import exe_sql_excel_query
from agent.excel.excel_mapping_node import read_excel_columns
from agent.excel.excel_sql_node import sql_generate_excel
from agent.text2sql.analysis.data_render_antv import data_render_ant
from agent.text2sql.analysis.data_render_apache import data_render_apache
from agent.text2sql.analysis.llm_summarizer import summarize

logger = logging.getLogger(__name__)


def data_render_condition(state: ExcelAgentState) -> str:
    """
    根据 chart_type 判断如果是表格则使用eChart进行渲染
    否则使用antV进行渲染
    """
    chart_type = state.get("chart_type")
    logger.info(f"chart_type: {chart_type}")
    if not chart_type or chart_type.lower() in ["mcp-server-chart-generate_table"]:
        return "data_render_apache"  # 直接跳转到总结节点

    return "data_render"


def create_excel_graph():
    """
    :return:
    """
    graph = StateGraph(ExcelAgentState)

    graph.add_node("excel_parsing", read_excel_columns)
    graph.add_node("sql_generator", sql_generate_excel)
    graph.add_node("sql_executor", exe_sql_excel_query)
    graph.add_node("data_render", data_render_ant)
    graph.add_node("data_render_apache", data_render_apache)
    graph.add_node("summarize", summarize)

    graph.set_entry_point("excel_parsing")
    graph.add_edge("excel_parsing", "sql_generator")
    graph.add_edge("sql_generator", "sql_executor")
    graph.add_edge("sql_executor", "summarize")

    graph.add_conditional_edges(
        "summarize", data_render_condition, {"data_render": "data_render", "data_render_apache": "data_render_apache"}
    )

    graph.add_edge("data_render", END)
    graph.add_edge("data_render_apache", END)
    graph_compiled: CompiledStateGraph = graph.compile()
    return graph_compiled
```

**流程图**:

```
excel_parsing(文件解析)
    ↓
sql_generator(SQL生成)
    ↓
sql_executor(SQL执行)
    ↓
summarize(结果总结)
    ↓
    ├─→ data_render(AntV图表) → END
    └─→ data_render_apache(ECharts表格) → END
```

**对比Text2SQL工作流**:

| 差异点 | Text2SQL | Excel Agent |
|--------|----------|-------------|
| 入口节点 | schema_inspector(数据库表检索) | excel_parsing(文件解析) |
| 动态分支 | 有(是否启用Neo4j) | 无(流程固定) |
| 数据源 | MySQL真实表 | DuckDB虚拟表 |

---

## 四、核心节点实现详解

### 节点1: excel_parsing——文件解析与表结构映射

**agent/excel/excel_mapping_node.py**(核心逻辑137-179行):

```python
# 生成表结构信息
schema_info = []

if extension in ["xlsx", "xls"]:
    if file_url.startswith("http://") or file_url.startswith("https://"):
        resp = requests.get(file_url)
        excel_file_data = pd.ExcelFile(io.BytesIO(resp.content))
    else:
        excel_file_data = pd.ExcelFile(file_url)
    table_comment = ".".join(path_parts[:-1])  # 使用文件名作为表注释

    for sheet_name in excel_file_data.sheet_names:
        # 读取每个sheet的前几行数据以推断数据类型
        if file_url.startswith("http://") or file_url.startswith("https://"):
            resp = requests.get(file_url)
            df = pd.read_excel(io.BytesIO(resp.content), sheet_name=sheet_name, nrows=5)
        else:
            df = pd.read_excel(file_url, sheet_name=sheet_name, nrows=5)

        # 生成表名（使用sheet名称）
        table_name = sheet_name.lower().replace(" ", "_").replace("-", "_")

        # 生成列信息
        columns_info = {}
        for column in df.columns:
            # 获取列的数据类型
            sample_data = df[column].dropna()
            if len(sample_data) > 0:
                dtype = str(sample_data.dtype)
            else:
                dtype = "object"  # 默认类型

            sql_type = map_pandas_dtype_to_sql(dtype)
            column_name = str(column).lower().replace(" ", "_").replace("-", "_")

            columns_info[column_name] = {"comment": str(column), "type": sql_type}  # 使用原始列名作为注释

        # 修改结构为指定格式
        schema_info.append(
            {
                "table_name": table_name,
                "columns": columns_info,
                "foreign_keys": [],
                "table_comment": table_comment,
            }
        )
```

**关键设计**:

1. **数据类型映射**(第23-54行):

```python
def map_pandas_dtype_to_sql(dtype: str) -> str:
    """
    将 pandas 数据类型映射到 SQL 数据类型
    """
    dtype_mapping = {
        "object": "VARCHAR(255)",
        "int64": "BIGINT",
        "int32": "INTEGER",
        "float64": "FLOAT",
        "float32": "FLOAT",
        "bool": "BOOLEAN",
        "datetime64[ns]": "DATETIME",
        "timedelta64[ns]": "VARCHAR(50)",
    }

    # 处理字符串类型
    if dtype.startswith("object"):
        return "VARCHAR(255)"
    # ... 其他类型推断逻辑
```

**为什么需要类型映射?**

- Pandas的`dtype`是Python类型(如`int64`)
- 但生成SQL时需要标准数据库类型(如`BIGINT`)
- LLM理解SQL类型更容易生成正确的聚合函数(如`SUM(BIGINT)` vs `SUM(VARCHAR)`)

2. **输出示例**:

```json
{
  "table_name": "手机销售数据",
  "columns": {
    "商品名称": {
      "comment": "商品名称",
      "type": "VARCHAR(255)"
    },
    "价格": {
      "comment": "价格",
      "type": "FLOAT"
    },
    "月份": {
      "comment": "月份",
      "type": "DATETIME"
    }
  },
  "foreign_keys": [],
  "table_comment": "销售数据"
}
```

---

### 节点2: sql_generator——针对Excel优化的Prompt

**agent/excel/excel_sql_node.py**(核心差异点):

**与Text2SQL Prompt的3个关键差异**:

| 差异点 | Text2SQL | Excel Agent |
|--------|----------|-------------|
| **数据库类型** | `MYSQL SQL查询语句` | `DUCKDB SQL查询语句` |
| **表关系参数** | 包含`table_relationship`参数 | 无此参数(Excel单表场景) |
| **兜底策略** | 返回`NULL` | 返回智能默认查询(第94-102行) |

**兜底策略代码**(第94-102行):

```python
if sql_query.upper() == "NULL" or len(sql_query) == 0:
    table_name = state["db_info"].get("table_name", "excel_table")
    columns_map = state["db_info"].get("columns", {})
    # 优先选择业务关键列
    preferred_cols = [
        key for key, info in columns_map.items()
        if any(kw in str(key) + str(info.get("comment", "")) for kw in ["客户", "名称", "编号", "省份"])
    ]
    select_cols = preferred_cols if len(preferred_cols) > 0 else list(columns_map.keys())
    sql_query = f"SELECT {', '.join(select_cols)} FROM {table_name} LIMIT 50"
    chart_type = "generate_table"
```

**设计亮点**:

- 当LLM无法理解用户意图时,不直接报错
- 智能识别包含"客户"、"名称"等关键字的业务列
- 自动生成`LIMIT 50`的预览查询,避免返回海量数据

---

### 节点3: sql_executor——DuckDB执行引擎

**agent/excel/excel_excute_sql.py**(完整83行):

```python
import io
import logging
import traceback
import duckdb
import requests
import os
import pandas as pd

from agent.excel.excel_agent_state import ExecutionResult
from common.minio_util import MinioUtils

logger = logging.getLogger(__name__)

minio_util = MinioUtils()


def exe_sql_excel_query(state):
    """
    执行sql语句
    :param state:
    :return:
    """
    file_list_ = state["file_list"]
    try:

        # 获取文件信息
        excel_file: dict = file_list_[0]
        file_key = excel_file.get("source_file_key")

        file_url = minio_util.get_file_url_by_key(object_key=file_key)
        extension = file_key.split(".")[-1].lower()

        # 根据文件类型读取数据
        if extension in ["xlsx", "xls"]:
            if file_url.startswith("http://") or file_url.startswith("https://"):
                response = requests.get(file_url)
                df = pd.read_excel(io.BytesIO(response.content), engine="openpyxl")
            else:
                df = pd.read_excel(file_url, engine="openpyxl")
        elif extension == "csv":
            df = pd.read_csv(file_url)
        else:
            logger.error(f"不支持的文件扩展名: {extension}")

        # 连接到DuckDB (这里使用内存数据库) 并注册DataFrame
        con = duckdb.connect(database=":memory:")

        # 注册DataFrame
        table_name = state["db_info"]["table_name"]
        con.register(table_name, df)
        if table_name != "excel_table":
            con.register("excel_table", df)

        sql = state["generated_sql"].replace("`", "")
        if not sql or sql.upper().strip() == "NULL":
            table_name = state["db_info"].get("table_name", "excel_table")
            columns_map = state["db_info"].get("columns", {})
            preferred_cols = [
                key for key, info in columns_map.items() if any(kw in str(key) + str(info.get("comment", "")) for kw in ["客户", "名称", "编号", "省份"])
            ]
            select_cols = preferred_cols if len(preferred_cols) > 0 else list(columns_map.keys())
            sql = f"SELECT {', '.join(select_cols)} FROM {table_name} LIMIT 50" if len(select_cols) > 0 else f"SELECT * FROM {table_name} LIMIT 50"

        # 执行SQL查询
        cursor = con.execute(sql)

        # 获取列名称和查询结果的数据行
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()

        # 构建结果字典
        result = [dict(zip(columns, row)) for row in rows]

        # 成功情况
        state["execution_result"] = ExecutionResult(success=True, columns=columns, data=result)

    except Exception as e:
        state["execution_result"] = ExecutionResult(success=False, columns=[], data=[], error=str(e))
        traceback.print_exception(e)
        logging.error(f"Error in executing SQL query: {e}")

    return state
```

**核心逻辑拆解**:

1. **多格式支持**(第34-43行):

```python
# 根据文件类型读取数据
if extension in ["xlsx", "xls"]:
    if file_url.startswith("http://") or file_url.startswith("https://"):
        response = requests.get(file_url)
        df = pd.read_excel(io.BytesIO(response.content), engine="openpyxl")
    else:
        df = pd.read_excel(file_url, engine="openpyxl")
elif extension == "csv":
    df = pd.read_csv(file_url)
```

- 支持本地文件路径和HTTP URL
- 自动根据扩展名选择解析器(`openpyxl`用于Excel,`csv`模块用于CSV)

2. **双重注册机制**(第48-52行):

```python
table_name = state["db_info"]["table_name"]
con.register(table_name, df)
if table_name != "excel_table":
    con.register("excel_table", df)
```

**为什么要注册两次?**

- `table_name` 是根据Sheet名称动态生成的(如`手机销售数据`)
- 但有些LLM可能生成通用的`SELECT * FROM excel_table`
- 双重注册确保两种表名都能查询成功

3. **结果封装**(第66-75行):

```python
# 获取列名称和查询结果的数据行
columns = [description[0] for description in cursor.description]
rows = cursor.fetchall()

# 构建结果字典
result = [dict(zip(columns, row)) for row in rows]

# 成功情况
state["execution_result"] = ExecutionResult(success=True, columns=columns, data=result)
```

- `cursor.description` 获取列元信息
- `zip(columns, row)` 将每行数据转为字典格式
- 便于后续节点处理(JSON序列化、图表渲染)

---

## 五、会话记忆机制——避免重复上传

### 1. 痛点场景

**传统方案**:

```
用户: 帮我统计销售额前10的商品
系统: (返回结果)

用户: 再看看销售额后10的商品  ← 需要重新上传文件!
```

### 2. 解决方案

**agent/excel/excel_agent.py**(第52-70行):

```python
# 会话记忆：若未显式传入file_list，则从历史记录中查找最近的文件问答记录
if file_list is None:
    try:
        records = query_user_qa_record(chat_id)
        file_list = []
        if records and len(records) > 0:
            for rec in records:
                if rec.get("qa_type") == DiFyAppEnum.FILEDATA_QA.value[0]:
                    fk = rec.get("file_key")
                    if fk:
                        try:
                            parsed = json.loads(fk)
                            if isinstance(parsed, list) and len(parsed) > 0 and parsed[0].get("source_file_key"):
                                file_list = parsed
                                break
                        except Exception:
                            continue
    except Exception:
        file_list = []
```

**实现原理**:

1. 用户首次上传文件时,`file_key`字段会保存到数据库(`t_user_qa_record`表)
2. 后续提问时,如果未上传新文件(`file_list is None`),自动查询该会话(`chat_id`)的历史记录
3. 提取最近一次文件问答的`file_key`,复用之前的文件

**数据库记录示例**:

```json
{
  "chat_id": "conv-20250118-001",
  "qa_type": "FILEDATA_QA",
  "file_key": "[{\"source_file_key\": \"uploads/销售数据.xlsx\", \"file_name\": \"销售数据.xlsx\"}]",
  "created_at": "2025-01-18 10:30:00"
}
```

---

## 六、文件上传与存储

### 1. 文件上传API

**controllers/file_chat_api.py**(第70-99行):

```python
@bp.post("/upload_file_and_parse")
@async_json_resp
async def upload_file_and_parse(request: Request):
    """
    上传附件并解析内容
    :param request:
    :return:
    """
    file_key_dict = minio_utils.upload_file_and_parse_from_request(request=request)
    try:
        chat_id = request.args.get("chat_id") or (request.json.get("chat_id") if request.json else None)
        uuid_str = request.args.get("uuid") or (request.json.get("uuid") if request.json else None)
        token = request.headers.get("Authorization")
        if token and token.startswith("Bearer "):
            token = token.split(" ", 1)[1]
        # 持久化当前会话的文件记忆，便于后续无需重新上传即可使用
        if chat_id and token:
            await add_user_record(
                uuid_str or "",
                chat_id,
                "文件上传与解析",
                [],
                {},
                DiFyAppEnum.FILEDATA_QA.value[0],
                token,
                [file_key_dict],
            )
    except Exception:
        pass
    return file_key_dict
```

**核心逻辑**:

1. 调用MinIO工具类上传文件(如果配置了MinIO)或保存到本地存储
2. 立即调用`add_user_record`保存文件元信息到数据库
3. 返回`file_key_dict`,包含`source_file_key`和`file_name`

### 2. MinIO配置(可选)

**默认行为**:

- 项目中MinIO默认**未启用**(学习环境优先使用本地存储)
- `common/minio_util.py`会根据环境变量`MINIO_ENDPOINT`判断:
  - 如果配置了MinIO,上传到对象存储
  - 如果未配置,保存到`storage/`目录

**生产环境配置示例**:

```bash
# .env.pro
MINIO_ENDPOINT=minio.example.com
MINIO_PORT=9000
MINIO_ACCESS_KEY=admin
MiNIO_SECRET_KEY=12345678
MINIO_BUCKET=excel-files
```

---

## 七、完整调用链路示例

### 1. 前端请求

```javascript
// POST /dify/get_answer
{
  "query": "统计每个省份的销售额",
  "chat_id": "conv-20250118-001",
  "uuid": "uuid-001",
  "qa_type": "FILEDATA_QA",
  "file_list": [
    {
      "source_file_key": "uploads/销售数据.xlsx",
      "file_name": "销售数据.xlsx"
    }
  ]
}
```

### 2. 后端执行流程

**services/dify_service.py**(第90-95行):

```python
elif qa_type == DiFyAppEnum.FILEDATA_QA.value[0]:
    # 当存在文件列表且包含source_file_key时使用前缀，否则直接使用用户问题
    if file_list and isinstance(file_list, list) and len(file_list) > 0 and file_list[0].get("source_file_key"):
        cleaned_query = f"{file_list[0]['source_file_key']}|{query}"
    await excel_agent.run_excel_agent(cleaned_query, res, chat_id, uuid_str, token, file_list)
    return None
```

**关键拼接逻辑**:

```python
cleaned_query = f"{file_list[0]['source_file_key']}|{query}"
# 结果: "uploads/销售数据.xlsx|统计每个省份的销售额"
```

**为什么要拼接file_key?**

- Excel Agent内部会根据`|`分割符提取文件路径
- 同时保留用户原始问题用于SQL生成
- 这是一个简化的参数传递设计(避免修改所有节点函数签名)

### 3. SSE流式响应示例

```
data:{"data":{"messageType":"continue","content":"<details>...</details>"},"dataType":"t02"}

data:{"data":{"messageType":"continue","content":"共检索1张表: 销售数据"},"dataType":"t02"}

data:{"data":{"messageType":"continue","content":"SELECT 省份, SUM(销售额) as 总销售额 ..."},"dataType":"t02"}

data:{"data":{"messageType":"continue","content":"执行sql语句成功"},"dataType":"t02"}

data:{"data":{"messageType":"continue","content":"根据数据分析,广东省销售额最高..."},"dataType":"t02"}

data:{"data":{"columns":["省份","总销售额"],"rows":[...]},"dataType":"t04"}

data:{"data":"DONE","dataType":"t08"}
```

---

## 八、常见问题与优化建议

### 1. 为什么不直接使用Pandas做分析?

**Pandas方案**:

```python
df = pd.read_excel("sales.xlsx")
result = df.groupby("省份")["销售额"].sum().sort_values(ascending=False).head(5)
```

**缺点**:

- LLM生成Pandas代码成功率低(语法复杂)
- 无法复用SQL Prompt(Text2SQL已有大量优化)
- Pandas执行动态代码有安全风险

**DuckDB方案**:

```python
con.register("sales", df)
con.execute("SELECT 省份, SUM(销售额) FROM sales GROUP BY 省份 ORDER BY 2 DESC LIMIT 5")
```

**优点**:

- SQL语法标准,LLM生成成功率高
- 复用Text2SQL的Prompt工程经验
- SQL注入风险更容易防范

### 2. 大文件性能优化

**当前限制**:

- `pd.read_excel()`会一次性加载整个文件到内存
- 100MB+的Excel文件可能导致OOM

**优化方案**:

1. **分片读取**(适用于CSV):

```python
chunk_size = 10000
for chunk in pd.read_csv("large.csv", chunksize=chunk_size):
    con.register("temp_chunk", chunk)
    # 处理每个chunk
```

2. **预过滤**(适用于Excel):

```python
df = pd.read_excel("large.xlsx", usecols=["省份", "销售额"], nrows=100000)
```

3. **升级到Polars**(下一代DataFrame库):

```python
import polars as pl
df = pl.read_excel("large.xlsx", lazy=True)  # 惰性加载
result = df.group_by("省份").agg(pl.sum("销售额")).collect()
```

### 3. 多Sheet处理

**当前限制**:

- `state["db_info"]`只保存第一个Sheet(第210行:`state["db_info"] = schema_info[0]`)

**改进方案**:

1. **保存所有Sheet**:

```python
state["db_info"] = schema_info  # 列表,包含所有Sheet
```

2. **修改SQL生成Prompt**:

```
提供的信息:
- 表结构(多个Sheet):
  * Sheet1: 销售数据 (列: 省份, 销售额)
  * Sheet2: 客户信息 (列: 客户ID, 省份)
- 用户提问: {user_query}

请生成跨表JOIN查询或选择合适的Sheet...
```

---

## 九、本章小结

### 1. 核心技术栈

```
文件上传 (MinIO/本地存储)
    ↓
Pandas解析 (pd.read_excel/pd.read_csv)
    ↓
DuckDB注册 (con.register)
    ↓
LLM生成SQL (DuckDB方言)
    ↓
内存执行 (零配置)
    ↓
图表渲染 (复用Text2SQL节点)
```

### 2. 代码文件清单

| 文件路径 | 核心功能 | 关键行数 |
|---------|---------|---------|
| `agent/excel/excel_graph.py` | LangGraph工作流定义 | 56行 |
| `agent/excel/excel_mapping_node.py` | Excel→表结构映射 | 217行 |
| `agent/excel/excel_sql_node.py` | SQL生成Prompt | 113行 |
| `agent/excel/excel_excute_sql.py` | DuckDB执行引擎 | 83行 |
| `agent/excel/excel_agent.py` | 主控Agent | 326行 |
| `agent/excel/excel_agent_state.py` | 状态定义 | 31行 |
| `controllers/file_chat_api.py` | 文件上传API | 123行 |

### 3. 与Text2SQL的架构对比

| 维度 | Text2SQL | Excel Agent |
|------|----------|-------------|
| **数据源** | MySQL持久化表 | 临时内存表 |
| **入口节点** | schema_inspector(BM25+向量检索) | excel_parsing(Pandas解析) |
| **SQL方言** | MySQL | DuckDB |
| **表关系** | 需要Neo4j或表注释推断 | 单表场景,无需关系 |
| **会话记忆** | 保存chat_id + 表名 | 保存chat_id + file_key |

### 4. 下一章预告

第10章将深入前端集成与SSE流式响应机制,包括:

1. Sanic的`ResponseStream`如何实现SSE协议
2. 前端EventSource如何解析流式数据
3. 思考过程(`<details>`)的动态渲染
4. 图表数据(`t04`)与文本数据(`t02`)的分离传输
5. 任务取消机制的实现

---

**思考题**:

1. 如果用户上传的Excel包含公式(如`=SUM(A1:A10)`),Pandas会如何处理?
2. DuckDB的`:memory:`数据库是否支持多线程并发查询?
3. 如何实现"对比两个Excel文件的差异"功能?(提示: 注册多个DataFrame)
