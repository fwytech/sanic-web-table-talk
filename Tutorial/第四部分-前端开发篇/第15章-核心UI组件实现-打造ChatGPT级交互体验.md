# 第15章 核心UI组件实现——打造ChatGPT级交互体验

## 本章目标

1. 掌握聊天消息组件(ChatMessage)的左右气泡布局实现
2. 学会使用marked + highlight.js实现Markdown渲染与代码高亮
3. 理解自动滚动到底部的多种实现方案及性能优化
4. 掌握Input输入框的自动高度调整与快捷键绑定
5. 学会ECharts图表组件的动态渲染与数据更新

---

## 一、聊天消息组件(ChatMessage)

### 1. 组件设计

**核心功能**:

- 支持用户/AI双向消息
- 用户消息右对齐,AI消息左对齐
- 支持Markdown渲染
- 支持代码高亮
- 支持流式输出动画

**组件接口设计**:

```typescript
// components/ChatMessage.vue
<script setup lang="ts">
interface Props {
  content: string           // 消息内容
  sender: 'user' | 'ai'     // 发送者
  timestamp?: number        // 时间戳
  streaming?: boolean       // 是否流式输出中
}

const props = withDefaults(defineProps<Props>(), {
  streaming: false
})
</script>
```

### 2. 布局实现

**Template模板**:

```vue
<template>
  <div
    class="message-wrapper"
    :class="[
      props.sender === 'user' ? 'message-user' : 'message-ai'
    ]"
  >
    <!-- 头像 -->
    <div class="avatar">
      <img v-if="props.sender === 'user'" src="@/assets/user-avatar.png" />
      <img v-else src="@/assets/ai-avatar.png" />
    </div>

    <!-- 消息气泡 -->
    <div class="message-bubble">
      <!-- Markdown渲染 -->
      <div
        v-if="props.sender === 'ai'"
        class="markdown-body"
        v-html="renderMarkdown(props.content)"
      ></div>
      <!-- 用户消息纯文本 -->
      <div v-else class="text-content">
        {{ props.content }}
      </div>

      <!-- 流式输出光标 -->
      <span v-if="props.streaming" class="cursor-blink">|</span>
    </div>

    <!-- 时间戳 -->
    <div v-if="props.timestamp" class="timestamp">
      {{ formatTime(props.timestamp) }}
    </div>
  </div>
</template>
```

**样式实现**(SCSS):

```scss
<style scoped lang="scss">
.message-wrapper {
  display: flex;
  margin-bottom: 20px;
  gap: 12px;

  // 用户消息: 右对齐
  &.message-user {
    flex-direction: row-reverse;
    justify-content: flex-start;

    .message-bubble {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border-radius: 18px 18px 4px 18px;
    }
  }

  // AI消息: 左对齐
  &.message-ai {
    flex-direction: row;

    .message-bubble {
      background: #f5f5f5;
      color: #333;
      border-radius: 18px 18px 18px 4px;
    }
  }

  .avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    overflow: hidden;
    flex-shrink: 0;

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
  }

  .message-bubble {
    max-width: 70%;
    padding: 12px 16px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    word-wrap: break-word;
  }

  // 流式输出光标动画
  .cursor-blink {
    display: inline-block;
    width: 2px;
    height: 1em;
    background-color: currentColor;
    animation: blink 1s step-end infinite;
  }

  @keyframes blink {
    50% { opacity: 0; }
  }
}
</style>
```

**工具函数**:

```typescript
<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

// 格式化时间
const formatTime = (timestamp: number) => {
  const date = new Date(timestamp)
  const hours = date.getHours().toString().padStart(2, '0')
  const minutes = date.getMinutes().toString().padStart(2, '0')
  return `${hours}:${minutes}`
}

// Markdown渲染(下一节详解)
const renderMarkdown = (content: string) => {
  return marked.parse(content)
}
</script>
```

---

## 二、Markdown渲染组件

### 1. marked配置

**安装依赖**:

```bash
pnpm add marked highlight.js dompurify
pnpm add -D @types/marked @types/dompurify
```

**配置marked**(utils/markdown.ts):

```typescript
import { marked } from 'marked'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'

// 配置marked
marked.setOptions({
  // 代码高亮
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch (err) {
        console.error(err)
      }
    }
    return hljs.highlightAuto(code).value
  },
  // 启用GFM(GitHub Flavored Markdown)
  gfm: true,
  // 支持表格
  tables: true,
  // 支持换行
  breaks: true,
  // 不转义HTML(需配合DOMPurify使用)
  pedantic: false,
  sanitize: false,
})

// 安全渲染Markdown
export const renderMarkdown = (content: string): string => {
  const rawHtml = marked.parse(content) as string
  return DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: [
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'p', 'br', 'strong', 'em', 'code', 'pre',
      'a', 'img', 'ul', 'ol', 'li', 'table',
      'thead', 'tbody', 'tr', 'th', 'td',
      'blockquote', 'hr', 'details', 'summary'
    ],
    ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class', 'style'],
  })
}
```

**为什么需要DOMPurify?**

```typescript
// 恶意输入
const malicious = '<img src=x onerror="alert(1)">'

// 直接渲染: XSS攻击! ✗
const html = marked.parse(malicious)

// DOMPurify清理: 安全 ✓
const safeHtml = DOMPurify.sanitize(html)
// 结果: <img src="x">  (删除onerror)
```

### 2. 代码块组件(CodeBlock)

**需求**:

- 显示语言标签(Python、JavaScript等)
- 代码高亮
- 复制按钮
- 行号显示(可选)

**组件实现**:

```vue
<!-- components/CodeBlock.vue -->
<template>
  <div class="code-block">
    <!-- 头部工具栏 -->
    <div class="code-header">
      <span class="language-label">{{ props.language }}</span>
      <button class="copy-btn" @click="copyCode">
        <span v-if="!copied">复制</span>
        <span v-else class="copied">已复制 ✓</span>
      </button>
    </div>

    <!-- 代码内容 -->
    <pre><code
      :class="`language-${props.language}`"
      v-html="highlightedCode"
    ></code></pre>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import hljs from 'highlight.js'
import { useClipboard } from '@vueuse/core'

interface Props {
  code: string
  language: string
}

const props = defineProps<Props>()

// 代码高亮
const highlightedCode = computed(() => {
  if (hljs.getLanguage(props.language)) {
    return hljs.highlight(props.code, { language: props.language }).value
  }
  return hljs.highlightAuto(props.code).value
})

// 复制功能
const { copy, copied } = useClipboard()
const copyCode = () => {
  copy(props.code)
}
</script>

<style scoped lang="scss">
.code-block {
  margin: 16px 0;
  border-radius: 8px;
  overflow: hidden;
  background: #282c34;

  .code-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    background: #21252b;
    border-bottom: 1px solid #181a1f;

    .language-label {
      color: #abb2bf;
      font-size: 12px;
      text-transform: uppercase;
    }

    .copy-btn {
      padding: 4px 12px;
      background: transparent;
      border: 1px solid #4b5263;
      color: #abb2bf;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.2s;

      &:hover {
        background: #4b5263;
      }

      .copied {
        color: #98c379;
      }
    }
  }

  pre {
    margin: 0;
    padding: 16px;
    overflow-x: auto;

    code {
      font-family: 'Fira Code', 'Consolas', monospace;
      font-size: 14px;
      line-height: 1.6;
    }
  }
}
</style>
```

**使用示例**:

```vue
<template>
  <CodeBlock
    language="python"
    :code="`def hello():\n    print('Hello World')`"
  />
</template>
```

### 3. highlight.js主题

**导入主题CSS**:

```typescript
// main.ts
import 'highlight.js/styles/atom-one-dark.css'  // 暗色主题
// 或
import 'highlight.js/styles/github.css'         // 亮色主题
```

**支持的语言**:

```typescript
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import sql from 'highlight.js/lib/languages/sql'

hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('sql', sql)
```

---

## 三、自动滚动到底部

### 1. 基础实现

**需求**: 新消息到达时,自动滚动到底部

**方案1: scrollTop手动控制**:

```typescript
<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

const messageListRef = ref<HTMLElement>()
const messages = ref([])

// 滚动到底部
const scrollToBottom = async () => {
  await nextTick()  // 等待DOM更新
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

// 监听消息变化
watch(messages, () => {
  scrollToBottom()
}, { deep: true })
</script>

<template>
  <div ref="messageListRef" class="message-list">
    <ChatMessage
      v-for="msg in messages"
      :key="msg.id"
      :content="msg.content"
      :sender="msg.sender"
    />
  </div>
</template>
```

**方案2: scrollIntoView API**:

```typescript
const scrollToBottom = async () => {
  await nextTick()
  const lastMessage = document.querySelector('.message-wrapper:last-child')
  lastMessage?.scrollIntoView({ behavior: 'smooth', block: 'end' })
}
```

### 2. 性能优化

**问题**: 流式输出时,每秒可能触发数十次滚动

**优化方案: 防抖**:

```typescript
import { debounce } from 'lodash-es'

// 300ms内最多执行一次
const scrollToBottom = debounce(async () => {
  await nextTick()
  messageListRef.value.scrollTop = messageListRef.value.scrollHeight
}, 300)
```

**优化方案: requestAnimationFrame**:

```typescript
let rafId: number | null = null

const scrollToBottom = async () => {
  if (rafId) cancelAnimationFrame(rafId)

  rafId = requestAnimationFrame(async () => {
    await nextTick()
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    rafId = null
  })
}
```

### 3. 用户主动滚动检测

**需求**: 用户向上查看历史记录时,不要自动滚动

```typescript
const isUserScrolling = ref(false)
const messageListRef = ref<HTMLElement>()

// 检测用户是否在底部
const checkIfAtBottom = () => {
  if (!messageListRef.value) return true
  const { scrollTop, scrollHeight, clientHeight } = messageListRef.value
  // 距离底部小于100px视为在底部
  return scrollHeight - scrollTop - clientHeight < 100
}

// 监听滚动事件
const onScroll = () => {
  isUserScrolling.value = !checkIfAtBottom()
}

// 仅在底部时自动滚动
watch(messages, () => {
  if (!isUserScrolling.value) {
    scrollToBottom()
  }
}, { deep: true })
```

---

## 四、输入框组件(InputArea)

### 1. 自动高度调整

**需求**: 输入框高度随内容自动增长,最大5行

```vue
<template>
  <div class="input-area">
    <textarea
      ref="textareaRef"
      v-model="inputText"
      placeholder="输入消息... (Shift+Enter换行, Enter发送)"
      @input="autoResize"
      @keydown.enter.exact.prevent="send Message"
      @keydown.enter.shift.exact="insertNewLine"
    ></textarea>
    <button @click="sendMessage">发送</button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const textareaRef = ref<HTMLTextAreaElement>()
const inputText = ref('')

// 自动调整高度
const autoResize = () => {
  if (!textareaRef.value) return

  // 重置高度以获取正确的scrollHeight
  textareaRef.value.style.height = 'auto'

  // 计算新高度(最大5行)
  const lineHeight = 24  // 单行高度
  const maxHeight = lineHeight * 5
  const newHeight = Math.min(textareaRef.value.scrollHeight, maxHeight)

  textareaRef.value.style.height = `${newHeight}px`
}

// 发送消息
const sendMessage = () => {
  if (!inputText.value.trim()) return
  emit('send', inputText.value)
  inputText.value = ''
  autoResize()  // 重置高度
}

// 插入换行
const insertNewLine = (e: KeyboardEvent) => {
  const start = textareaRef.value!.selectionStart
  const end = textareaRef.value!.selectionEnd
  inputText.value =
    inputText.value.substring(0, start) + '\n' +
    inputText.value.substring(end)
}
</script>

<style scoped lang="scss">
.input-area {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: white;
  border-top: 1px solid #e5e5e5;

  textarea {
    flex: 1;
    min-height: 48px;
    max-height: 120px;  // 5行
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 8px;
    resize: none;
    font-size: 14px;
    line-height: 24px;
    outline: none;

    &:focus {
      border-color: #667eea;
    }
  }

  button {
    padding: 0 24px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    transition: opacity 0.2s;

    &:hover {
      opacity: 0.9;
    }

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }
}
</style>
```

### 2. 快捷键支持

**常见快捷键**:

| 按键 | 功能 |
|------|------|
| `Enter` | 发送消息 |
| `Shift + Enter` | 换行 |
| `Ctrl/Cmd + K` | 清空输入框 |
| `Esc` | 取消编辑 |

**实现**:

```typescript
import { onMounted, onUnmounted } from 'vue'

const handleKeydown = (e: KeyboardEvent) => {
  // Ctrl/Cmd + K: 清空
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    inputText.value = ''
  }

  // Esc: 取消
  if (e.key === 'Escape') {
    inputText.value = ''
    emit('cancel')
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
```

---

## 五、ECharts图表组件

### 1. 图表组件封装

**需求**: 根据后端返回的t04数据渲染图表

```vue
<!-- components/ChartRenderer.vue -->
<template>
  <div ref="chartRef" class="chart-container"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'

interface Props {
  data: {
    columns: string[]
    rows: Record<string, any>[]
  }
  type?: 'bar' | 'line' | 'pie'
}

const props = withDefaults(defineProps<Props>(), {
  type: 'bar'
})

const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

// 初始化图表
onMounted(() => {
  if (!chartRef.value) return
  chartInstance = echarts.init(chartRef.value)
  renderChart()
})

// 监听数据变化
watch(() => props.data, () => {
  renderChart()
}, { deep: true })

// 渲染图表
const renderChart = () => {
  if (!chartInstance) return

  const option = generateOption()
  chartInstance.setOption(option, true)  // 第二个参数true表示不合并
}

// 生成ECharts配置
const generateOption = () => {
  if (props.type === 'bar') {
    return {
      title: { text: '数据分析' },
      tooltip: {},
      xAxis: {
        type: 'category',
        data: props.data.rows.map(row => row[props.data.columns[0]])
      },
      yAxis: { type: 'value' },
      series: [{
        type: 'bar',
        data: props.data.rows.map(row => row[props.data.columns[1]])
      }]
    }
  }
  // 其他类型...
}

// 响应式调整
const resize = () => chartInstance?.resize()
window.addEventListener('resize', resize)
</script>

<style scoped>
.chart-container {
  width: 100%;
  height: 400px;
}
</style>
```

### 2. 动态图表类型

**根据数据智能选择图表**:

```typescript
const autoDetectChartType = (data: any) => {
  const { columns, rows } = data

  // 仅1列数据 → 饼图
  if (columns.length === 1) {
    return 'pie'
  }

  // 2列且第一列是时间 → 折线图
  if (columns.length === 2 && /日期|时间/.test(columns[0])) {
    return 'line'
  }

  // 默认柱状图
  return 'bar'
}
```

---

## 六、本章小结

### 1. 核心组件清单

```
ChatMessage      → 消息气泡(左/右布局)
MarkdownRenderer → Markdown渲染
CodeBlock        → 代码高亮 + 复制
InputArea        → 自动高度输入框
ChartRenderer    → ECharts图表
```

### 2. 技术要点

| 组件 | 关键技术 |
|------|---------|
| ChatMessage | Flexbox布局、CSS动画 |
| Markdown | marked + highlight.js + DOMPurify |
| CodeBlock | useClipboard复制、语法高亮 |
| InputArea | 自动高度、快捷键绑定 |
| Chart | ECharts响应式、动态数据 |

### 3. 性能优化

- 防抖滚动(debounce 300ms)
- requestAnimationFrame优化
- 按需导入highlight.js语言
- ECharts懒加载

### 4. 下一章预告

第16章将深入前后端集成:

1. Fetch API封装与错误处理
2. SSE流式数据解析(TextDecoderStream)
3. Pinia状态管理实战
4. 文件上传组件实现
5. 登录鉴权与Token管理

---

**思考题**:

1. 为什么需要DOMPurify清理HTML而不是直接使用marked输出?
2. 自动滚动的防抖优化为什么选择300ms而非100ms或500ms?
3. 如何实现"向上滚动自动加载更多历史记录"功能?
