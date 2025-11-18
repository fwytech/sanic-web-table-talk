# 第7章 Text2SQL Agent 第一部分:BM25 + 向量混合检索与智能表结构匹配

## 章节目标

1. 理解 Text2SQL 的核心挑战,掌握从自然语言到 SQL 的转换思路
2. 学会 BM25 算法的原理与 Jieba 分词优化,实现精准关键词匹配
3. 掌握 FAISS 向量索引构建,使用 DashScope Embedding API 生成语义向量
4. 实践 RRF(Reciprocal Rank Fusion)融合策略,结合 BM25 与向量检索优势
5. 使用 DashScope Rerank API 进行结果重排序,提升召回准确率

## 一、Text2SQL 的核心挑战

### 1.1 为什么 Text2SQL 很难

**挑战1:自然语言的歧义性**

```
用户:"查询最近一周的订单"

可能的理解:
1. 最近7天的订单(2024-01-01 到 2024-01-07)
2. 最近一个自然周的订单(2024-01-01 周一 到 2024-01-07 周日)
3. 距离现在最近的7条订单记录

对应的SQL:
1. WHERE order_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
2. WHERE WEEK(order_date) = WEEK(CURDATE())
3. ORDER BY order_date DESC LIMIT 7
```

**挑战2:表结构复杂性**

```
数据库有 50 张表,每张表 20 个字段
用户:"查询销售数据"

问题:
- 哪张表是销售表?(t_sales_orders? t_order_details? t_products?)
- 需要关联哪些表?(客户表? 产品表?)
- 字段名是什么?(total_amount? sale_amount? order_amount?)
```

**挑战3:SQL 语法多样性**

```
同一个需求,多种SQL写法:

需求:"统计每个省份的订单数"

写法1(GROUP BY):
SELECT province, COUNT(*) FROM orders GROUP BY province

写法2(子查询):
SELECT province, (SELECT COUNT(*) FROM orders o2 WHERE o2.province = o1.province)
FROM orders o1 GROUP BY province

写法3(窗口函数):
SELECT DISTINCT province, COUNT(*) OVER (PARTITION BY province) FROM orders
```

### 1.2 解决方案架构

```
┌────────────┐
│ 用户查询   │  "统计各省订单数"
└──────┬─────┘
       │
       ▼
┌────────────────────────┐
│ 第1步:表结构检索       │  混合检索(BM25+向量+重排)
│ 目标:找到相关的表      │  → 筛选出 t_sales_orders, t_customers
└──────┬─────────────────┘
       │
       ▼
┌────────────────────────┐
│ 第2步:生成 SQL         │  Prompt Engineering
│ 目标:根据表结构生成SQL │  → SELECT province, COUNT(*) FROM ...
└──────┬─────────────────┘
       │
       ▼
┌────────────────────────┐
│ 第3步:执行 SQL         │  数据库查询
│ 目标:获取查询结果      │  → [{province: "北京", count: 100}, ...]
└──────┬─────────────────┘
       │
       ▼
┌────────────────────────┐
│ 第4步:LLM 总结         │  数据分析
│ 目标:生成人类可读报告  │  → "北京订单最多(100单),其次是上海..."
└──────┬─────────────────┘
       │
       ▼
┌────────────────────────┐
│ 第5步:生成图表         │  数据可视化
│ 目标:直观展示数据      │  → [柱状图/饼图/...]
└────────────────────────┘
```

**本章重点:第1步 - 表结构检索**

---

## 二、BM25 算法:关键词匹配的最佳实践

### 2.1 BM25 原理

**BM25(Best Matching 25):**  基于 TF-IDF 改进的排序算法

**核心思想:**
1. **词频(TF)**: 词在文档中出现的次数越多,越相关
2. **逆文档频率(IDF)**: 词在所有文档中越罕见,越重要
3. **文档长度归一化**: 避免长文档占优势

**公式(简化版):**
```
BM25(q, d) = Σ IDF(qi) × TF(qi, d) × (k1 + 1)
                         ──────────────────────────
                         TF(qi, d) + k1 × (1 - b + b × |d| / avgdl)

其中:
- q: 查询词列表
- d: 文档
- TF(qi, d): qi 在文档 d 中的词频
- IDF(qi): qi 的逆文档频率
- |d|: 文档长度
- avgdl: 平均文档长度
- k1, b: 调优参数(通常 k1=1.5, b=0.75)
```

**直观理解:**

```
查询:"统计订单数据"
分词:["统计", "订单", "数据"]

文档1(t_sales_orders表):
"订单表 包含订单编号 订单日期 订单金额等字段"
匹配词:["订单"出现3次]
BM25 = 高分 ✅

文档2(t_products表):
"产品表 包含产品名称 产品类别 产品价格等字段"
匹配词:[]
BM25 = 0分 ❌

文档3(t_order_details表):
"订单明细表 记录每个订单的产品明细数据"
匹配词:["订单"出现1次, "数据"出现1次]
BM25 = 中等分数
```

### 2.2 Jieba 分词优化

**为什么需要分词?**

```
查询:"统计订单数据"

不分词:
["统计订单数据"]  # 无法匹配 "订单" 或 "数据"

分词:
["统计", "订单", "数据"]  # 可以匹配任意一个词
```

**项目实战(`agent/text2sql/database/db_service.py:87`):**

```python
import jieba
import re

@staticmethod
def _tokenize_text(text_str: str) -> List[str]:
    """
    对中文/英文文本进行分词,过滤标点符号。

    Args:
        text_str (str): 输入文本

    Returns:
        List[str]: 分词后的 token 列表
    """
    # 1. 过滤标点符号和特殊字符
    filtered_text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", " ", text_str)

    # 2. Jieba 分词
    tokens = jieba.lcut(filtered_text, cut_all=False)

    # 3. 过滤空字符串
    return [token.strip() for token in tokens if token.strip()]
```

**分词示例:**

```python
text = "查询t_sales_orders表中的订单数据"
tokens = _tokenize_text(text)
print(tokens)
# 输出: ['查询', 't_sales_orders', '表', '中', '的', '订单', '数据']
```

**优化点:**
1. **去除标点**: `[^\u4e00-\u9fa5a-zA-Z0-9]` 只保留中英文和数字
2. **精确模式**: `cut_all=False` 避免过度分词
3. **去除空格**: 确保分词结果干净

### 2.3 构建检索文档

**文档内容设计:**

```python
@staticmethod
def _build_document(table_name: str, table_info: dict) -> str:
    """
    构建用于检索的文档文本(表名 + 注释 + 字段名 + 字段注释)。

    Args:
        table_name (str): 表名
        table_info (dict): 包含列、外键、注释等信息的字典

    Returns:
        str: 拼接后的文档文本
    """
    parts = [table_name]

    # 添加表注释
    if table_info.get("table_comment"):
        parts.append(table_info["table_comment"])

    # 添加所有字段名和注释
    for col_name, col_info in table_info.get("columns", {}).items():
        parts.append(col_name)
        if col_info.get("comment"):
            parts.append(col_info["comment"])

    return " ".join(parts)
```

**示例:**

```python
table_name = "t_sales_orders"
table_info = {
    "table_comment": "销售订单主表",
    "columns": {
        "order_id": {"type": "INT", "comment": "订单ID"},
        "customer_id": {"type": "INT", "comment": "客户ID"},
        "order_date": {"type": "DATE", "comment": "订单日期"},
        "total_amount": {"type": "DECIMAL", "comment": "订单总金额"}
    }
}

doc = _build_document(table_name, table_info)
print(doc)
# 输出: "t_sales_orders 销售订单主表 order_id 订单ID customer_id 客户ID order_date 订单日期 total_amount 订单总金额"
```

**为什么这样设计:**
1. **表名权重最高**: 用户通常会提到表名
2. **表注释增强语义**: "销售订单主表" 比 "t_sales_orders" 更易理解
3. **字段注释覆盖细节**: "订单日期" 可以匹配 "最近订单"

### 2.4 BM25 检索实现

**完整代码(`agent/text2sql/database/db_service.py:369`):**

```python
from rank_bm25 import BM25Okapi

def _retrieve_by_bm25(self, table_info: Dict[str, Dict], user_query: str) -> List[int]:
    """
    使用 BM25 算法进行关键词匹配检索。

    Args:
        table_info (Dict[str, Dict]): 表结构
        user_query (str): 用户查询

    Returns:
        List[int]: 按相关性排序的索引列表
    """
    if not user_query or not table_info:
        return list(range(len(table_info)))

    logger.info("🔄 执行 BM25 检索...")

    # 1. 构建文档列表
    self._corpus = [self._build_document(name, info) for name, info in table_info.items()]

    # 2. 分词
    self._tokenized_corpus = [self._tokenize_text(doc) for doc in self._corpus]
    query_tokens = self._tokenize_text(user_query)

    # 3. 初始化 BM25
    bm25 = BM25Okapi(self._tokenized_corpus)

    # 4. 计算得分
    doc_scores = bm25.get_scores(query_tokens)

    # 5. 增强:若查询词出现在表注释中,则提升分数
    enhanced_scores = doc_scores.copy()
    table_comments = [info.get("table_comment", "") for info in table_info.values()]

    for i, (comment, score) in enumerate(zip(table_comments, doc_scores)):
        if score <= 0:
            continue

        # 计算查询词与表注释的重叠度
        comment_tokens = self._tokenize_text(comment)
        overlap = set(query_tokens) & set(comment_tokens)

        if overlap:
            overlap_ratio = len(overlap) / len(set(query_tokens))
            enhanced_scores[i] += score * overlap_ratio * 1.5  # 提升50%

    # 6. 排序
    scored_indices = sorted(enumerate(enhanced_scores), key=lambda x: x[1], reverse=True)

    return [idx for idx, _ in scored_indices]
```

**增强策略解释:**

```
用户查询:"统计销售订单"
查询分词:["统计", "销售", "订单"]

表1: t_sales_orders (销售订单主表)
- 表注释分词:["销售", "订单", "主表"]
- 重叠词:{"销售", "订单"}
- 重叠率: 2/3 = 0.67
- 原始分数: 10.5
- 增强分数: 10.5 + 10.5 × 0.67 × 1.5 = 21.0 ✅ 大幅提升

表2: t_products (产品信息表)
- 表注释分词:["产品", "信息", "表"]
- 重叠词:{}
- 增强分数: 0 ❌ 不变
```

---

## 三、FAISS 向量检索:语义理解的利器

### 3.1 为什么需要向量检索

**BM25 的局限性:**

```
用户查询:"查询客户购买记录"

BM25 分词:["查询", "客户", "购买", "记录"]

表1: t_sales_orders (销售订单主表)
- 文档:"销售 订单 主表 order_id customer_id ..."
- 匹配词:["客户"(customer_id)]
- BM25分数:低 ❌ (没有"购买"关键词)

但实际上:"销售订单" 和 "购买记录" 是同义词!
```

**向量检索的优势:**

```
"销售订单" → 向量 [0.2, 0.5, 0.8, ...]
"购买记录" → 向量 [0.3, 0.4, 0.7, ...]
余弦相似度: 0.85 ✅ (高度相似)

"销售订单" → 向量 [0.2, 0.5, 0.8, ...]
"产品信息" → 向量 [0.9, 0.1, 0.2, ...]
余弦相似度: 0.12 ❌ (不相似)
```

### 3.2 FAISS 向量索引原理

**FAISS(Facebook AI Similarity Search):**  Meta 开发的高效相似性搜索库

**核心流程:**

```
1. 文本 → Embedding API → 向量
   "销售订单主表" → [0.2, 0.5, 0.8, ..., 0.3]  # 1024 维向量

2. 向量 → FAISS 索引
   IndexFlatIP(dimension=1024)  # 内积索引(余弦相似度)

3. 查询向量 → 搜索最相似的 K 个向量
   "查询订单" → [0.25, 0.48, 0.75, ..., 0.32]
   search(query_vec, k=10) → [索引0, 索引5, 索引12, ...]
```

**索引类型选择:**

| 索引类型 | 原理 | 速度 | 精度 | 适用场景 |
|---------|------|------|------|----------|
| IndexFlatIP | 暴力搜索(内积) | 慢 | 100% | 数据量 < 10万 |
| IndexFlatL2 | 暴力搜索(欧氏距离) | 慢 | 100% | 数据量 < 10万 |
| IndexIVFFlat | 倒排索引 | 快 | 95% | 数据量 > 10万 |
| IndexHNSW | 分层图 | 最快 | 98% | 数据量 > 百万 |

**项目选择:** `IndexFlatIP`(内积 = 余弦相似度,因为向量已归一化)

### 3.3 DashScope Embedding API

**调用示例(`agent/text2sql/database/db_service.py:271`):**

```python
from openai import OpenAI
import numpy as np
import faiss

# 初始化客户端
MODEL_API_KEY = os.getenv("MODEL_API_KEY")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")  # text-embedding-v3

client = OpenAI(api_key=MODEL_API_KEY, base_url=MODEL_BASE_URL)

@staticmethod
def _create_embeddings_with_dashscope(texts: List[str]) -> np.ndarray:
    """
    使用 DashScope API 生成文本嵌入向量。

    Args:
        texts (List[str]): 输入文本列表

    Returns:
        np.ndarray: 嵌入向量数组
    """
    logger.info("🌐 调用 DashScope 文本嵌入 API...")
    start_time = time.time()

    embeddings = []
    for doc in texts:
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL_NAME,
                input=doc
            )
            embeddings.append(response.data[0].embedding)
        except Exception as e:
            logger.error(f"❌ 嵌入生成失败 ({doc[:30]}...): {e}")
            embeddings.append(np.zeros(1024))  # 占位符

    # 转换为 numpy 数组并归一化
    embeddings = np.array(embeddings).astype("float32")
    faiss.normalize_L2(embeddings)  # L2 归一化(使内积 = 余弦相似度)

    logger.info(f"✅ 嵌入生成完成,耗时 {time.time() - start_time:.2f}s")
    return embeddings
```

**归一化的重要性:**

```
向量A = [3, 4]
向量B = [6, 8]

未归一化:
- 内积 = 3×6 + 4×8 = 50
- 余弦相似度 = 50 / (√(9+16) × √(36+64)) = 50 / 50 = 1.0

归一化后:
- A' = [0.6, 0.8]  (除以模长5)
- B' = [0.6, 0.8]  (除以模长10)
- 内积 = 0.6×0.6 + 0.8×0.8 = 1.0  (等于余弦相似度)
```

### 3.4 向量索引持久化

**为什么需要持久化:**

```
问题:每次启动服务都重新调用 Embedding API
- 100 张表 × 0.1 秒/表 = 10 秒启动时间
- 100 张表 × ¥0.0007/次 = ¥0.07/次启动

解决方案:首次构建后保存到磁盘
- 启动时间: 0.5 秒(加载索引)
- 成本: ¥0(无API调用)
```

**持久化实现(`agent/text2sql/database/db_service.py:213`):**

```python
VECTOR_INDEX_DIR = "./vector_index"
INDEX_FILE = os.path.join(VECTOR_INDEX_DIR, "schema.index")
METADATA_FILE = os.path.join(VECTOR_INDEX_DIR, "metadata.json")

def _save_vector_index(self, table_info: Dict[str, Dict]):
    """
    将 FAISS 索引和元数据保存到磁盘。
    """
    if self._faiss_index is None:
        return

    # 保存 FAISS 索引
    faiss.write_index(self._faiss_index, INDEX_FILE)

    # 保存元数据
    metadata = {
        "table_names": self._table_names,
        "corpus": self._corpus,
        "fingerprint": self._generate_schema_fingerprint(table_info),
        "updated_at": pd.Timestamp.now().isoformat(),
    }
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ 向量索引已保存至: {INDEX_FILE}")
```

**Schema 指纹(检测变更):**

```python
@staticmethod
def _generate_schema_fingerprint(table_info: Dict[str, Dict]) -> str:
    """
    生成 schema 的指纹(MD5 哈希),用于检测变更。
    """
    fingerprint_data = {}
    for table_name, info in table_info.items():
        fingerprint_data[table_name] = {
            "comment": info.get("table_comment", ""),
            "columns": sorted([
                f"{col_name}:{col_info.get('comment', '')}"
                for col_name, col_info in info["columns"].items()
            ])
        }
    json_str = json.dumps(fingerprint_data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_str.encode("utf-8")).hexdigest()
```

**加载逻辑:**

```python
def _load_vector_index(self, table_info: Dict[str, Dict]) -> bool:
    """
    从磁盘加载 FAISS 向量索引和元数据。

    Returns:
        bool: 是否加载成功
    """
    if not (os.path.exists(INDEX_FILE) and os.path.exists(METADATA_FILE)):
        logger.info("❌ 向量索引文件不存在,将重建")
        return False

    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # 检查 schema 是否变更
        current_fingerprint = self._generate_schema_fingerprint(table_info)
        if metadata.get("fingerprint") != current_fingerprint:
            logger.info("🔄 数据库 schema 已变更,需重建向量索引")
            return False

        # 加载索引
        self._faiss_index = faiss.read_index(INDEX_FILE)
        self._table_names = metadata["table_names"]
        self._corpus = metadata["corpus"]

        logger.info(f"🎉 成功加载向量索引,包含 {len(self._table_names)} 张表")
        return True

    except Exception as e:
        logger.warning(f"⚠️ 加载向量索引失败: {e},将重建")
        return False
```

### 3.5 向量检索实现

**完整代码(`agent/text2sql/database/db_service.py:335`):**

```python
def _retrieve_by_vector(self, query: str, top_k: int = 10) -> List[int]:
    """
    使用向量相似度检索最相关的表。

    Args:
        query (str): 用户输入的自然语言查询
        top_k (int): 需要返回的最相似表的数量

    Returns:
        List[int]: 与用户查询最相似的表在 corpus 中的索引列表
    """
    try:
        # 1. 生成查询向量
        response = client.embeddings.create(
            model=EMBEDDING_MODEL_NAME,
            input=query
        )
        query_vec = np.array([response.data[0].embedding]).astype("float32")

        # 2. L2 归一化
        faiss.normalize_L2(query_vec)

        # 3. 搜索
        _, indices = self._faiss_index.search(query_vec, top_k)

        return indices[0].tolist()

    except Exception as e:
        logger.error(f"❌ 向量检索失败: {e}")
        return []
```

**使用示例:**

```python
user_query = "统计各省销售额"

# 生成查询向量
query_embedding = client.embeddings.create(
    model="text-embedding-v3",
    input=user_query
).data[0].embedding  # [0.23, 0.45, 0.78, ..., 0.12]

# FAISS 搜索
faiss_index.search(query_vec, k=10)
# 返回: ([0.85, 0.73, 0.62, ...], [2, 5, 8, ...])
#        ↑ 相似度分数            ↑ 表索引

# 索引2 → t_sales_orders
# 索引5 → t_customers
# 索引8 → t_order_details
```

---

## 四、RRF 融合:结合 BM25 与向量检索的优势

### 4.1 为什么需要融合

**BM25 优势:**
- 精确匹配关键词
- 对表名/字段名敏感

**向量检索优势:**
- 理解语义相似性
- 处理同义词

**单一方法的局限:**

```
用户查询:"查询客户购买记录"

BM25 Top 3:
1. t_customers (客户信息表) ✅ 匹配"客户"
2. t_user_qa_record (问答记录表) ❌ 匹配"记录"
3. t_report_info (报告记录表) ❌ 匹配"记录"

向量检索 Top 3:
1. t_sales_orders (销售订单主表) ✅ 语义相似"购买"
2. t_order_details (订单明细表) ✅ 语义相似
3. t_customers (客户信息表) ✅ 相关表

融合后:
1. t_customers (两者都高分)
2. t_sales_orders (向量高分)
3. t_order_details (向量高分)
```

### 4.2 RRF(Reciprocal Rank Fusion) 算法

**公式:**

```
RRF(d) = Σ  1 / (k + rank_i(d))
       i∈methods

其中:
- d: 文档
- rank_i(d): 文档 d 在方法 i 中的排名(从0开始)
- k: 常数(通常取60)
```

**直观理解:**

```
文档A:
- BM25 排名: 第1名(rank=0) → 1/(60+0) = 0.0167
- 向量 排名: 第3名(rank=2) → 1/(60+2) = 0.0161
- RRF 得分: 0.0167 + 0.0161 = 0.0328

文档B:
- BM25 排名: 第5名(rank=4) → 1/(60+4) = 0.0156
- 向量 排名: 未出现(rank=∞) → 0
- RRF 得分: 0.0156

文档C:
- BM25 排名: 第2名(rank=1) → 1/(60+1) = 0.0164
- 向量 排名: 第1名(rank=0) → 1/(60+0) = 0.0167
- RRF 得分: 0.0164 + 0.0167 = 0.0331 ✅ 最高分
```

**项目实战(`agent/text2sql/database/db_service.py:407`):**

```python
@staticmethod
def _rrf_fusion(bm25_indices: List[int], vector_indices: List[int], k: int = 60) -> List[int]:
    """
    使用 RRF(Reciprocal Rank Fusion)融合两种检索结果。

    Args:
        bm25_indices (List[int]): BM25 排序索引
        vector_indices (List[int]): 向量检索排序索引
        k (int): RRF 常数

    Returns:
        List[int]: 融合后排序的索引列表
    """
    scores = {}

    # BM25 贡献
    for rank, idx in enumerate(bm25_indices):
        scores[idx] = scores.get(idx, 0) + 1 / (k + rank + 1)

    # 向量检索贡献
    for rank, idx in enumerate(vector_indices):
        scores[idx] = scores.get(idx, 0) + 1 / (k + rank + 1)

    # 按分数降序排列
    sorted_indices = sorted(scores.items(), key=lambda x: -x[1])

    return [idx for idx, _ in sorted_indices]
```

### 4.3 二次过滤:只保留双重验证的候选表

**策略:交集 + RRF 融合**

```python
# 混合检索
bm25_top_indices = self._retrieve_by_bm25(all_table_info, user_query)
# [5, 2, 8, 12, 3, 7, ...]

vector_top_indices = self._retrieve_by_vector(user_query, top_k=20)
# [2, 8, 5, 15, 3, ...]

# 过滤:仅保留同时在 BM25 前 50 和向量结果中的表
valid_bm25_set = set(bm25_top_indices[:50])
# {5, 2, 8, 12, 3, 7, ...}

candidate_indices = [idx for idx in vector_top_indices if idx in valid_bm25_set]
# [2, 8, 5, 3]  # 15 被过滤(不在 BM25 前50)

if not candidate_indices:
    # 降级:如果过滤后为空,使用 BM25 前4个
    candidate_indices = bm25_top_indices[:4]

# RRF 融合
fused_indices = self._rrf_fusion(bm25_top_indices, candidate_indices, k=60)
```

**为什么这样设计:**
1. **提高精度**: 双重验证避免单一方法的偏差
2. **降级保护**: 确保总有候选表返回
3. **减少噪音**: 过滤掉仅在一种方法中高分的误匹配表

---

## 五、DashScope Rerank:最后的精排

### 5.1 为什么需要 Rerank

**问题:RRF 融合仍然是基于排名,没有考虑语义深度**

```
用户查询:"统计各省份的电诈案件数量"

RRF 融合后 Top 3:
1. t_alarm_info (诈骗数据表) ✅ 正确
2. t_customers (客户信息表) ❌ BM25高分,但不相关
3. t_sales_orders (销售订单表) ❌ 向量相似,但业务无关

Rerank 模型(深度语义理解):
1. t_alarm_info (0.95) ✅ 与"电诈案件"高度相关
2. t_customers (0.12) ❌ 相关性低
3. t_sales_orders (0.08) ❌ 相关性低
```

### 5.2 DashScope GTE-Rerank-V2 API

**特点:**
- 基于 BERT 的深度模型
- 输入:查询 + 文档列表
- 输出:每个文档的相关性分数(0-1)

**调用示例(`agent/text2sql/database/db_service.py:427`):**

```python
import dashscope
from http import HTTPStatus

def _rerank_with_dashscope(self, query: str, candidate_tables: Dict[str, Dict]) -> List[Tuple[str, float]]:
    """
    使用 DashScope GTE-Rerank-V2 对候选表进行重排序。

    Args:
        query (str): 用户查询
        candidate_tables (Dict[str, Dict]): 候选表及其信息

    Returns:
        List[Tuple[str, float]]: (表名, 相关性分数) 列表,按分数降序
    """
    if not self.USE_RERANKER:
        logger.debug("⏭️ Reranker 已禁用,跳过重排序")
        return [(name, 1.0) for name in candidate_tables.keys()]

    try:
        # 1. 构建文档列表
        documents = []
        name_to_text = {}
        for table_name, info in candidate_tables.items():
            doc_text = self._build_document(table_name, info)
            documents.append(doc_text)
            name_to_text[table_name] = doc_text

        if not documents:
            return []

        # 2. 调用 Rerank API
        logger.info("🔁 调用 GTE-Rerank-V2 进行重排序...")
        response = dashscope.TextReRank.call(
            api_key=MODEL_API_KEY,
            model=RERANK_MODEL_NAME,  # gte-rerank-v2
            query=query,
            documents=documents,
            top_n=len(documents),  # 返回所有结果
            return_documents=False,  # 只返回索引和分数
        )

        # 3. 解析结果
        if response.status_code == HTTPStatus.OK:
            results = []
            for item in response.output.results:
                # 根据索引找到对应的表名
                table_name = next(
                    name for name, text in name_to_text.items()
                    if text == documents[item.index]
                )
                results.append((table_name, item.relevance_score))

            # 按分数降序排列
            results.sort(key=lambda x: x[1], reverse=True)
            logger.info("✅ Rerank 完成")
            return results
        else:
            logger.warning(f"⚠️ Rerank API 调用失败: {response.message}")
            return [(name, 1.0) for name in candidate_tables.keys()]

    except Exception as e:
        logger.error(f"❌ Rerank 过程出错: {e}")
        return [(name, 1.0) for name in candidate_tables.keys()]
```

**API 返回示例:**

```json
{
    "status_code": 200,
    "output": {
        "results": [
            {"index": 0, "relevance_score": 0.95},  // t_alarm_info
            {"index": 2, "relevance_score": 0.12},  // t_customers
            {"index": 1, "relevance_score": 0.08}   // t_sales_orders
        ]
    }
}
```

---

## 六、完整检索流程

### 6.1 get_table_schema 节点完整实现

**源码(`agent/text2sql/database/db_service.py:479`,精简版):**

```python
def get_table_schema(self, state: AgentState) -> AgentState:
    """
    根据用户查询,通过混合检索筛选出最相关的数据库表结构。
    """
    try:
        logger.info("🔍 开始获取数据库表 schema 信息")

        # 1. 获取所有表结构
        all_table_info = self._fetch_all_table_info()

        user_query = state.get("user_query", "").strip()
        if not user_query:
            state["db_info"] = all_table_info
            return state

        # 2. 初始化向量索引(加载或重建)
        self._initialize_vector_index(all_table_info)

        # 3. 混合检索:BM25 + 向量检索
        logger.info("🔍 开始混合检索:BM25 + 向量检索")
        bm25_top_indices = self._retrieve_by_bm25(all_table_info, user_query)
        vector_top_indices = self._retrieve_by_vector(user_query, top_k=20)

        # 4. 过滤:仅保留同时在 BM25 前 50 和向量结果中的表
        valid_bm25_set = set(bm25_top_indices[:50])
        candidate_indices = [idx for idx in vector_top_indices if idx in valid_bm25_set]

        if not candidate_indices:
            candidate_indices = bm25_top_indices[:4]  # 降级

        # 5. RRF 融合
        fused_indices = self._rrf_fusion(bm25_top_indices, candidate_indices, k=60)

        # 6. 评分筛选(取分数 >= 0.01 且最多10个)
        selected_indices = []
        for idx in fused_indices:
            bm25_rank = bm25_top_indices.index(idx) + 1 if idx in bm25_top_indices else len(all_table_info) + 1
            vector_rank = vector_top_indices.index(idx) + 1 if idx in vector_top_indices else len(all_table_info) + 1
            score = 1 / (60 + bm25_rank) + 1 / (60 + vector_rank)
            if score >= 0.01 and len(selected_indices) < 10:
                selected_indices.append(idx)

        # 7. 构建候选表字典
        candidate_table_names = [self._table_names[i] for i in selected_indices]
        candidate_table_info = {name: all_table_info[name] for name in candidate_table_names}

        # 8. Rerank 重排序
        reranked_results = self._rerank_with_dashscope(user_query, candidate_table_info)
        final_table_names = [name for name, _ in reranked_results][:4]  # 取 top 4

        # 9. 构建输出
        filtered_info = {name: all_table_info[name] for name in final_table_names}

        # 10. 打印结果摘要
        print(f"\n🔍 用户查询: {user_query}")
        print("📊 检索与排序结果:")
        for i, (table_name, score) in enumerate(reranked_results):
            print(f"  {i + 1}. {table_name:<15} | Rerank: {score:.3f}")

        state["db_info"] = filtered_info
        logger.info(f"✅ 最终筛选出 {len(filtered_info)} 个相关表: {list(filtered_info.keys())}")

    except Exception as e:
        logger.error(f"❌ 获取数据库表信息失败: {e}")
        state["db_info"] = {}

    return state
```

### 6.2 执行流程可视化

```
用户查询:"统计各省电诈案件数"
       │
       ▼
┌──────────────────┐
│ 1. 获取所有表    │  50张表
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 2. BM25 检索     │  → [5, 2, 8, 12, 3, ...]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 3. 向量检索      │  → [2, 8, 5, 15, 3, ...]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 4. 交集过滤      │  → [2, 8, 5, 3]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 5. RRF 融合      │  → [2, 5, 8, 3]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 6. 评分筛选      │  → [2, 5, 8, 3, 12, 7]  (10个)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 7. Rerank 重排   │  → [(2, 0.95), (5, 0.78), (8, 0.45), (3, 0.12)]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 8. Top K 截断    │  → [2, 5, 8, 3]  (4个)
└────────┬─────────┘
         │
         ▼
      输出到 state["db_info"]
```

---

## 七、本章总结

### 7.1 核心要点回顾

1. **BM25 算法**: 基于关键词匹配,使用 Jieba 分词和表注释增强
2. **FAISS 向量索引**: 语义检索,使用 DashScope Embedding API
3. **索引持久化**: MD5 指纹检测 schema 变更,避免重复构建
4. **RRF 融合**: 结合 BM25 与向量检索优势,双重验证
5. **Rerank 重排**: DashScope GTE-Rerank-V2 深度语义理解

### 7.2 检索准确率优化技巧

1. **表注释权重提升**: 重叠词提升 1.5 倍分数
2. **交集过滤**: 只保留同时在两种方法中高分的表
3. **降级保护**: 过滤后为空时使用 BM25 前4个
4. **Top K 截断**: 最终只取 4 张表,避免上下文过长

### 7.3 成本与性能优化

| 优化点 | 优化前 | 优化后 | 提升 |
|-------|--------|--------|------|
| 向量索引构建 | 每次启动调用API | 首次构建后持久化 | 启动快 10倍 |
| Rerank 候选表数 | 50张表 | 10张表 | 成本降低 80% |
| 最终返回表数 | 10张表 | 4张表 | Prompt 缩短 60% |

### 7.4 下一章预告

下一章我们将学习 **Text2SQL Agent 第二部分:LangGraph 工作流与 SQL 生成**,包括:
- Prompt Engineering 设计 SQL 生成模板
- LangGraph 状态图完整构建
- 条件路由(Neo4j 表关系查询)
- 图表类型推荐与数据渲染

---

**完整文件清单:**
- `agent/text2sql/database/db_service.py` (635 行) - 数据库服务与混合检索
- `agent/text2sql/state/agent_state.py` (68 行) - 状态定义
- `vector_index/schema.index` - FAISS 索引文件(自动生成)
- `vector_index/metadata.json` - 元数据文件(自动生成)
