# 第10章 前端集成与SSE流式响应——打造ChatGPT级用户体验

## 本章目标

1. 深入理解SSE(Server-Sent Events)协议与WebSocket的技术差异及选型依据
2. 掌握Sanic的ResponseStream实现单向流式推送的核心机制
3. 学会前端TextDecoderStream + TransformStream解析SSE数据流的流水线处理模式
4. 理解数据类型路由设计(t02/t04/t08/t11)如何实现文本与图表的分离传输
5. 实现任务取消机制,避免用户等待时的资源浪费

---

## 一、为什么选择SSE而非WebSocket?

### 1. 技术对比

| 维度 | SSE (Server-Sent Events) | WebSocket |
|------|-------------------------|-----------|
| **通信方向** | 单向(服务器→客户端) | 双向(全双工) |
| **协议** | HTTP/1.1长连接 | 独立协议(ws://) |
| **连接建立** | 普通HTTP请求,自动重连 | 需要握手升级,断线需手动重连 |
| **浏览器兼容** | IE除外全支持 | 现代浏览器全支持 |
| **防火墙友好** | 是(复用80/443端口) | 否(可能被企业防火墙拦截) |
| **实现复杂度** | 低(纯文本格式) | 高(需要二进制帧解析) |
| **适用场景** | 股票行情、AI流式输出、日志推送 | 聊天室、游戏、协同编辑 |

### 2. 本项目选择SSE的三大理由

**理由1: LLM流式输出是单向场景**

```
用户提问 → HTTP POST请求 → Agent开始推理
                          ↓
                     SSE流式返回Token
                          ↓
                      用户阅读内容
```

- 用户提问后,**不需要**在推理过程中再发送数据
- WebSocket的双向能力在这里是过度设计

**理由2: 自动重连机制**

```javascript
const eventSource = new EventSource('/stream');
eventSource.onerror = (e) => {
  // SSE会自动尝试重连,无需手动处理
  console.log('Connection lost, auto-reconnecting...');
};
```

- SSE断线后浏览器会**自动重连**(默认3秒)
- WebSocket断线需要手动实现重连逻辑

**理由3: 部署简单**

- SSE走HTTP协议,无需Nginx额外配置
- WebSocket需要配置`Upgrade`和`Connection`头

**Nginx配置对比**:

```nginx
# SSE配置(几乎无需特殊处理)
location /sanic/ {
    proxy_pass http://backend:8089;
    proxy_buffering off;  # 关键:禁用缓冲
}

# WebSocket配置(需要升级协议)
location /ws/ {
    proxy_pass http://backend:8089;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## 二、Sanic的ResponseStream实现

### 1. 核心API

**controllers/dify_chat_api.py**(第17-31行):

```python
@bp.post("/get_answer")
@check_token
async def get_answer(req):
    """
        调用diFy画布获取数据流式返回
    :param req:
    :return:
    """

    try:
        response = ResponseStream(dify.exec_query, content_type="text/event-stream")
        return response
    except Exception as e:
        logging.error(f"Error Invoke diFy: {e}")
        raise MyException(SysCodeEnum.c_9999)
```

**关键设计**:

1. **ResponseStream第一个参数是回调函数**

```python
ResponseStream(dify.exec_query, content_type="text/event-stream")
```

- `dify.exec_query`是一个`async`函数,接收`response`对象作为参数
- Sanic会自动传入`response`对象,用于后续的`await response.write()`

2. **content_type="text/event-stream"**

```
HTTP/1.1 200 OK
Content-Type: text/event-stream  ← SSE协议标识
Cache-Control: no-cache
Connection: keep-alive

data:{"data":"hello"}\n\n  ← SSE数据格式
```

- 告诉浏览器这是SSE流,不是普通HTTP响应
- 浏览器收到后会自动创建`EventSource`对象(如果使用`new EventSource()`)

### 2. 流式写入实现

**services/dify_service.py**(第84-95行,调用智能体):

```python
# 调用智能体
if qa_type == DiFyAppEnum.COMMON_QA.value[0]:
    await common_agent.run_agent(query, res, chat_id, uuid_str, token, file_list)
    return None
elif qa_type == DiFyAppEnum.DATABASE_QA.value[0]:
    await sql_agent.run_agent(query, res, chat_id, uuid_str, token)
    return None
elif qa_type == DiFyAppEnum.FILEDATA_QA.value[0]:
    # 当存在文件列表且包含source_file_key时使用前缀，否则直接使用用户问题
    if file_list and isinstance(file_list, list) and len(file_list) > 0 and file_list[0].get("source_file_key"):
        cleaned_query = f"{file_list[0]['source_file_key']}|{query}"
    await excel_agent.run_excel_agent(cleaned_query, res, chat_id, uuid_str, token, file_list)
    return None
```

**agent/text2sql/text2_sql_agent.py**(第232-251行,发送SSE数据):

```python
@staticmethod
async def _send_response(
    response, content: str, message_type: str = "continue", data_type: str = DataTypeEnum.ANSWER.value[0]
) -> None:
    """
    发送响应数据
    """
    if response:
        if data_type == DataTypeEnum.ANSWER.value[0]:
            formatted_message = {
                "data": {
                    "messageType": message_type,
                    "content": content,
                },
                "dataType": data_type,
            }
        else:
            # 适配EChart表格
            formatted_message = {"data": content, "dataType": data_type}

        await response.write("data:" + json.dumps(formatted_message, ensure_ascii=False) + "\n\n")
```

**SSE协议格式解析**:

```
data:{"data":{"messageType":"continue","content":"正在查询数据库..."},"dataType":"t02"}\n\n
^     ^                                                                            ^
|     |                                                                            |
|     +-- JSON数据                                                                 |
|                                                                                   |
+-- SSE固定前缀                                                  双换行符(标识消息结束)
```

**关键细节**:

1. 每条消息必须以`data:`开头
2. 必须以`\n\n`(两个换行符)结尾,告诉浏览器这是一条完整消息
3. JSON中不能包含换行符(否则会被误判为多条消息)

---

## 三、前端SSE数据流解析

### 1. Fetch API调用

**web/src/api/index.ts**(第8-51行):

```typescript
/**
 * Event Stream 调用大模型接口 Ollama3 (Fetch 调用)
 */
export async function createOllama3Stylized(text, qa_type, uuid, chat_id, file_list) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/dify/get_answer`)
  const params = {}
  Object.keys(params).forEach((key) => {
    url.searchParams.append(key, params[key])
  })

  // 创建 AbortController 用于超时控制
  const controller = new AbortController()
  const timeoutId = setTimeout(() => {
    controller.abort()
  }, 10 * 60 * 1000) // 10分钟超时 (10 * 60 * 1000 毫秒)

  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      query: text,
      qa_type,
      uuid,
      chat_id,
      file_list,
    }),
    signal: controller.signal, // 添加超时信号
  })

  return fetch(req).finally(() => {
    clearTimeout(timeoutId) // 清除超时定时器
  })
}
```

**设计亮点**:

1. **AbortController超时控制**

```javascript
const controller = new AbortController()
const timeoutId = setTimeout(() => {
  controller.abort()  // 10分钟后自动取消请求
}, 10 * 60 * 1000)
```

- 防止用户忘记关闭页面导致的资源泄漏
- `abort()`会触发`fetch`的reject,可以在`catch`中处理

2. **为什么用Fetch而非EventSource?**

**EventSource方案**(传统SSE):

```javascript
const es = new EventSource('/stream');
es.onmessage = (e) => {
  console.log(e.data);
};
```

**缺点**:

- **无法自定义请求头**(无法传递`Authorization: Bearer xxx`)
- **仅支持GET请求**(无法发送请求体)
- **无法取消请求**(没有`abort()`方法)

**Fetch方案**(现代SSE):

```javascript
const response = await fetch(url, {
  method: 'POST',  // 支持POST
  headers: { 'Authorization': `Bearer ${token}` },  // 支持自定义头
  signal: controller.signal  // 支持取消
});
const reader = response.body.getReader();
```

### 2. Stream流水线处理

**web/src/store/business/index.ts**(第90-144行):

```typescript
const reader = res.body
  .pipeThrough(new TextDecoderStream())
  .pipeThrough(TransformUtils.splitStream('\n'))
  .pipeThrough(
    new TransformStream({
      transform: (chunk, controller) => {
        try {
          const jsonChunk = JSON.parse(
            chunk.split('data:')[1],
          )
          if (jsonChunk.task_id) {
            // 调用已有的更新方法来更新 task_id
            this.update_task_id(
              jsonChunk.task_id,
            )
          }
          switch (jsonChunk.dataType) {
            case 't11':
              controller.enqueue(
                JSON.stringify({
                  content: `问题: ${query_str}`,
                }),
              )
              break
            case 't02':
              if (
                jsonChunk.data
                && jsonChunk.data.content
              ) {
                controller.enqueue(
                  JSON.stringify(
                    jsonChunk.data,
                  ),
                )
              }
              break
            case 't04':
              this.writerList = jsonChunk
              break
            default:
                                    // 可以在这里处理其他类型的 dataType
          }
        } catch (e) {
          console.error(
            'Error processing chunk:',
            e,
          )
        }
      },
      flush: (controller) => {
        controller.terminate()
      },
    }),
  )
  .getReader()
```

**流水线拆解**:

```
ReadableStream (字节流)
    ↓ pipeThrough(TextDecoderStream)
UTF-8字符串流
    ↓ pipeThrough(splitStream('\n'))
按换行符分割的消息流
    ↓ pipeThrough(TransformStream)
解析JSON + 路由dataType
    ↓ getReader()
最终的Reader对象
```

**核心概念**:

1. **TextDecoderStream**: 将字节流解码为UTF-8字符串

```javascript
// 输入: Uint8Array([100, 97, 116, 97, 58])
// 输出: "data:"
```

2. **splitStream('\n')**: 自定义TransformStream,按换行符分割

```javascript
// 输入: "data:{...}\n\ndata:{...}\n\n"
// 输出: ["data:{...}", "data:{...}"]
```

3. **TransformStream的transform方法**: 处理每个chunk

```javascript
transform: (chunk, controller) => {
  const jsonChunk = JSON.parse(chunk.split('data:')[1]);
  // 根据dataType路由到不同处理逻辑
  controller.enqueue(processedData);  // 传递到下游
}
```

---

## 四、数据类型路由设计(t02/t04/t08/t11)

### 1. 数据类型定义

**constants/code_enum.py**(DataTypeEnum枚举):

```python
class DataTypeEnum(Enum):
    ANSWER = ("t02", "回答内容")
    BUS_DATA = ("t04", "业务数据")
    STREAM_END = ("t08", "流结束")
    TASK_ID = ("t11", "任务ID")
```

**设计原理**:

| dataType | 用途 | 前端处理 | 示例数据 |
|----------|------|---------|---------|
| **t02** | 文本回答 | 追加到Markdown渲染区 | `{"messageType":"continue","content":"共检索3张表"}` |
| **t04** | 图表数据 | 渲染ECharts/AntV | `{"columns":["省份","销售额"],"rows":[...]}` |
| **t08** | 流结束标识 | 停止Loading动画 | `"DONE"` |
| **t11** | 任务ID | 保存用于后续取消任务 | `"task-20250118-001"` |

### 2. t02: 文本内容的三种状态

**messageType枚举**:

```python
# agent/text2sql/text2_sql_agent.py
{
  "data": {
    "messageType": "begin",      # 开始输出
    "content": ""
  },
  "dataType": "t02"
}

{
  "data": {
    "messageType": "continue",   # 持续输出
    "content": "正在生成SQL..."
  },
  "dataType": "t02"
}

{
  "data": {
    "messageType": "end",        # 结束输出
    "content": ""
  },
  "dataType": "t02"
}
```

**前端处理逻辑**:

```typescript
case 't02':
  if (jsonChunk.data && jsonChunk.data.content) {
    controller.enqueue(JSON.stringify(jsonChunk.data))
  }
  break
```

- `begin`: 前端开始渲染Markdown容器
- `continue`: 追加内容到容器(支持流式显示每个Token)
- `end`: 停止动画光标

### 3. t04: 图表数据的延迟传输

**为什么要延迟传输?**

```
时间轴:
0s   ─────→ 发送t02: "正在查询数据库..."
1s   ─────→ 发送t02: "执行SQL成功"
2s   ─────→ 发送t02: "正在生成图表..."
3s   ─────→ 发送t04: {图表数据}  ← 最后才发送
```

**设计理由**:

1. 图表数据通常较大(几百KB JSON)
2. 先让用户看到文本进度,避免"卡顿"的错觉
3. 图表需要所有数据准备好才能渲染(无法流式显示)

**发送代码**(agent/text2sql/text2_sql_agent.py第194-196行):

```python
elif step_name in ["data_render", "data_render_apache"] and data_type == DataTypeEnum.BUS_DATA.value[0]:
    t04_answer_data.clear()
    t04_answer_data.update({"data": content, "dataType": data_type})
```

**前端存储到全局State**(web/src/store/business/index.ts第126-128行):

```typescript
case 't04':
  this.writerList = jsonChunk  // 保存到Pinia store
  break
```

- `writerList`会触发Vue组件重新渲染
- 组件监听该State,渲染ECharts图表

### 4. t08: 流结束的优雅收尾

**发送时机**(agent/text2sql/text2_sql_agent.py第124-127行):

```python
# 发送结束标识，通知前端流结束
if response:
    await response.write(
        "data:" + json.dumps({"data": "DONE", "dataType": DataTypeEnum.STREAM_END.value[0]}, ensure_ascii=False) + "\n\n"
    )
```

**为什么需要显式结束标识?**

- SSE协议本身**没有**结束信号(连接一直保持)
- 前端需要知道何时停止Loading动画
- 否则用户会一直看到"思考中..."的提示

---

## 五、思考过程的动态渲染

### 1. HTML details标签设计

**生成代码**(agent/text2sql/text2_sql_agent.py第127-131行):

```python
if new_step not in ["summarize", "data_render", "data_render_apache"]:
    think_html = f"""<details style="color:gray;background-color: #f8f8f8;padding: 2px;border-radius:
    6px;margin-top:5px;">
                 <summary>{new_step}...</summary>"""
    await self._send_response(response, think_html, "continue", "t02")
    t02_answer_data.append(think_html)
```

**渲染效果**:

```html
<details>
  <summary>schema_inspector...</summary>
  共检索3张表: t_customers(客户表)、t_orders(订单表)、t_products(产品表)
</details>

<details>
  <summary>sql_generator...</summary>
  SELECT c.customer_name, SUM(o.amount) FROM t_customers c JOIN t_orders o ...
</details>
```

**用户体验**:

- 默认**折叠**(只显示`<summary>`内容)
- 点击展开可查看详细过程
- 类似ChatGPT的"Show thinking"功能

### 2. 环境变量控制

**配置项**(.env.dev):

```bash
# 是否显示思考过程 true/false
SHOW_THINKING_PROCESS=true
```

**代码实现**(agent/text2sql/text2_sql_agent.py第26行):

```python
self.show_thinking_process = os.getenv("SHOW_THINKING_PROCESS", "true").lower() == "true"
```

**条件渲染**(agent/text2sql/text2_sql_agent.py第187行):

```python
should_send = self.show_thinking_process or step_name in ["summarize", "data_render", "data_render_apache"]
```

**设计意图**:

- 开发环境: `SHOW_THINKING_PROCESS=true`,便于调试
- 生产环境: `SHOW_THINKING_PROCESS=false`,给用户简洁体验
- **关键步骤**(如`summarize`)无论如何都会显示

---

## 六、任务取消机制

### 1. 取消流程

```
用户点击"停止"按钮
    ↓
前端调用 stop_chat API
    ↓
后端设置 running_tasks[task_id]["cancelled"] = True
    ↓
Agent检测到cancelled标志
    ↓
发送"这条消息已停止" + STREAM_END
```

### 2. 后端实现

**Agent初始化**(agent/text2sql/text2_sql_agent.py第23-24行):

```python
def __init__(self):
    # 存储运行中的任务
    self.running_tasks = {}
```

**任务注册**(agent/text2sql/text2_sql_agent.py第49-53行):

```python
# 获取用户信息 标识对话状态
user_dict = await decode_jwt_token(user_token)
task_id = user_dict["id"]
task_context = {"cancelled": False}
self.running_tasks[task_id] = task_context
```

**循环检测**(agent/text2sql/text2_sql_agent.py第57-66行):

```python
async for chunk_dict in graph.astream(initial_state, stream_mode="updates"):

    # 检查是否已取消
    if self.running_tasks[task_id]["cancelled"]:
        if self.show_thinking_process:
            await self._send_response(response, "</details>\n\n", "continue", DataTypeEnum.ANSWER.value[0])
        await response.write(
            self._create_response("\n> 这条消息已停止", "info", DataTypeEnum.ANSWER.value[0])
        )
        # 发送最终停止确认消息
        await response.write(self._create_response("", "end", DataTypeEnum.STREAM_END.value[0]))
        break
```

**取消API**(agent/text2sql/text2_sql_agent.py第266-275行):

```python
async def cancel_task(self, task_id: str) -> bool:
    """
    取消指定的任务
    :param task_id: 任务ID
    :return: 是否成功取消
    """
    if task_id in self.running_tasks:
        self.running_tasks[task_id]["cancelled"] = True
        return True
    return False
```

**服务层调用**(services/dify_service.py第506-510行):

```python
elif qa_type == DiFyAppEnum.DATABASE_QA.value[0]:
    user_dict = await decode_jwt_token(token)
    task_id = user_dict["id"]
    success = await sql_agent.cancel_task(task_id)
    return {"success": success, "message": "任务已停止" if success else "未找到任务"}
```

### 3. 前端实现

**调用API**(web/src/api/index.ts第299-316行):

```typescript
/**
 * 停止对话
 * @param task_id
 * @param qa_type
 * @param rating
 * @returns
 */
export async function stop_chat(task_id, qa_type) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/dify/stop_chat`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`, // 添加 token 到头部
    },
    body: JSON.stringify({
      task_id,
      qa_type,
    }),
  })
  return fetch(req)
}
```

**为什么用user_id作为task_id?**

```python
task_id = user_dict["id"]  # 使用用户ID
```

**设计理由**:

1. 每个用户同一时间**只能运行一个任务**(单线程问答)
2. 避免生成UUID的开销
3. 简化task_id的管理(无需额外存储)

**潜在问题**:

- 如果支持多标签页同时提问,会导致冲突
- 生产环境应改为`task_id = f"{user_id}_{chat_id}"`

---

## 七、完整数据流示例

### 1. 后端SSE输出

```python
# Step 1: schema_inspector
await response.write("data:" + json.dumps({
  "data": {"messageType": "continue", "content": "<details><summary>schema_inspector...</summary>"},
  "dataType": "t02"
}, ensure_ascii=False) + "\n\n")

await response.write("data:" + json.dumps({
  "data": {"messageType": "continue", "content": "共检索3张表: t_customers, t_orders, t_products"},
  "dataType": "t02"
}, ensure_ascii=False) + "\n\n")

await response.write("data:" + json.dumps({
  "data": {"messageType": "continue", "content": "</details>\n\n"},
  "dataType": "t02"
}, ensure_ascii=False) + "\n\n")

# Step 2: sql_generator
await response.write("data:" + json.dumps({
  "data": {"messageType": "continue", "content": "<details><summary>sql_generator...</summary>"},
  "dataType": "t02"
}, ensure_ascii=False) + "\n\n")

await response.write("data:" + json.dumps({
  "data": {"messageType": "continue", "content": "SELECT c.customer_name, SUM(o.amount) ..."},
  "dataType": "t02"
}, ensure_ascii=False) + "\n\n")

await response.write("data:" + json.dumps({
  "data": {"messageType": "continue", "content": "</details>\n\n"},
  "dataType": "t02"
}, ensure_ascii=False) + "\n\n")

# Step 3: summarize (最终答案)
await response.write("data:" + json.dumps({
  "data": {"messageType": "continue", "content": "根据数据分析,销售额最高的客户是..."},
  "dataType": "t02"
}, ensure_ascii=False) + "\n\n")

# Step 4: 图表数据
await response.write("data:" + json.dumps({
  "data": {"columns": ["客户名称", "销售额"], "rows": [{"客户名称": "张三", "销售额": 10000}, ...]},
  "dataType": "t04"
}, ensure_ascii=False) + "\n\n")

# Step 5: 流结束
await response.write("data:" + json.dumps({
  "data": "DONE",
  "dataType": "t08"
}, ensure_ascii=False) + "\n\n")
```

### 2. 前端解析流程

```typescript
// TextDecoderStream解码后的字符串流:
"data:{...}\n\ndata:{...}\n\ndata:{...}\n\n"

↓ splitStream('\n')

["data:{...}", "data:{...}", "data:{...}"]

↓ TransformStream

switch (jsonChunk.dataType) {
  case 't02':
    // 追加到Markdown渲染区
    markdownContent += jsonChunk.data.content
    break
  case 't04':
    // 渲染ECharts图表
    renderChart(jsonChunk.data)
    break
  case 't08':
    // 停止Loading动画
    isLoading = false
    break
}
```

---

## 八、常见问题与优化建议

### 1. SSE连接数限制

**浏览器限制**:

- Chrome/Edge: 同一域名最多**6个**并发SSE连接
- Firefox: 最多**6个**
- Safari: 最多**6个**

**问题场景**:

```
用户打开6个标签页,每个都在进行数据问答
第7个标签页的SSE连接会被阻塞,直到前6个有一个结束
```

**解决方案**:

1. **限制用户同时提问数**

```typescript
const MAX_CONCURRENT_CHATS = 3
if (activeChatCount >= MAX_CONCURRENT_CHATS) {
  alert('最多同时进行3个对话')
  return
}
```

2. **使用HTTP/2**

- HTTP/2支持多路复用,无6连接限制
- 需要配置HTTPS(HTTP/2强制TLS)

### 2. 大数据量传输优化

**问题**:

- 图表数据包含10万行时,JSON序列化+传输耗时长
- 前端解析大JSON会阻塞主线程

**优化方案**:

1. **后端分页返回**

```python
# 仅返回前1000行数据
data = execution_result["data"][:1000]
await response.write("data:" + json.dumps({"data": data, "dataType": "t04"}, ensure_ascii=False) + "\n\n")
```

2. **前端使用Web Worker解析**

```typescript
const worker = new Worker('json-parser-worker.js')
worker.postMessage(largeJsonString)
worker.onmessage = (e) => {
  const parsedData = e.data
  renderChart(parsedData)
}
```

3. **压缩传输**(gzip)

```python
# Sanic自动启用gzip压缩
app.config.RESPONSE_TIMEOUT = 600
app.config.REQUEST_MAX_SIZE = 100_000_000  # 100MB
```

### 3. 内存泄漏风险

**问题代码**:

```python
class Text2SqlAgent:
    def __init__(self):
        self.running_tasks = {}  # ← 只添加,从不删除!
```

**隐患**:

- 每次查询都会添加`running_tasks[task_id]`
- 但查询结束后**没有删除**
- 长时间运行会导致字典无限增长

**修复方案**:

```python
# 查询结束后清理
finally:
    if task_id in self.running_tasks:
        del self.running_tasks[task_id]
```

---

## 九、本章小结

### 1. SSE核心技术栈

```
后端:
Sanic ResponseStream → async response.write() → SSE格式输出

前端:
Fetch API → TextDecoderStream → splitStream → TransformStream → getReader()
```

### 2. 数据类型路由

| dataType | 后端发送 | 前端处理 |
|----------|---------|---------|
| t02 | Agent每个步骤的文本输出 | 追加到Markdown渲染区 |
| t04 | 图表数据(JSON) | 渲染ECharts/AntV |
| t08 | 流结束标识 | 停止Loading动画 |
| t11 | 任务ID | 保存用于取消任务 |

### 3. 用户体验优化

1. **流式显示**: 用户无需等待完整响应,实时看到进度
2. **思考过程**: `<details>`标签折叠中间步骤,突出最终答案
3. **任务取消**: 用户可随时停止不需要的查询,节省资源
4. **超时保护**: 10分钟自动断开,防止资源泄漏

### 4. 代码文件清单

| 文件路径 | 核心功能 | 关键行数 |
|---------|---------|---------|
| `controllers/dify_chat_api.py` | SSE路由定义 | 59行 |
| `services/dify_service.py` | Agent调用 + 流式输出 | 541行 |
| `agent/text2sql/text2_sql_agent.py` | SSE数据发送 | 276行 |
| `web/src/api/index.ts` | 前端SSE调用 | 316行 |
| `web/src/store/business/index.ts` | 流式数据解析 | 174行 |

### 5. 下一章预告

第11章将介绍可选集成组件(Neo4j与MinIO):

1. Neo4j图数据库如何存储表关系,提升复杂SQL生成准确率
2. MinIO对象存储如何替代本地文件系统,实现分布式部署
3. 这两个组件为何设计为**可选**(默认禁用),以及如何在需要时快速启用
4. Docker Compose一键启动完整技术栈

---

**思考题**:

1. 如果用户网络不稳定,SSE连接频繁断开重连,如何实现"断点续传"?(提示: SSE的`Last-Event-ID`头)
2. 为什么前端不能用`async/await`配合`for await (const chunk of response.body)`,而必须用`pipeThrough`?
3. 如何实现"思考过程"的实时Token流式显示(类似ChatGPT打字机效果)?(提示: 修改`<details>`的渲染逻辑)
