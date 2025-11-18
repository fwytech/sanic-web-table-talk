# 第3章 SQLAlchemy 2.0 + MySQL 双引擎数据层设计哲学

## 章节目标

1. 理解 SQLAlchemy 2.0 的 Mapped 类型注解带来的类型安全优势
2. 掌握单例模式连接池设计,避免数据库连接泄漏和性能瓶颈
3. 学会 ORM 与原生 SQL 并存的双引擎策略,在复杂查询场景下灵活切换
4. 实践数据库初始化脚本设计,支持一键部署和测试数据准备

## 一、为什么需要双引擎数据层

在实际项目中,你会遇到两类数据库操作场景:

**场景1:简单 CRUD(ORM 更优)**
```python
# 查询单个用户 - 代码清晰,类型安全
user = session.query(TUser).filter(TUser.userName == "admin").first()
```

**场景2:复杂统计查询(原生 SQL 更优)**
```python
# 多表关联 + 分组 + 子查询 - ORM 会生成复杂的 SQL,不如直接写
sql = """
    SELECT division_name, COUNT(1) as count, AVG(fraud_money) as avg_amount
    FROM t_alarm_info
    WHERE is_fraud = '是'
    GROUP BY division_name
    HAVING count > 5
"""
```

**核心矛盾:**
ORM 提供类型安全和对象映射,但在复杂查询时不如原生 SQL 灵活。

**解决方案:**
双引擎设计 - `SQLAlchemy ORM` 处理 CRUD + `PyMySQL` 处理复杂查询

---

## 二、SQLAlchemy 2.0 新特性:Mapped 类型注解

### 2.1 从 SQLAlchemy 1.x 到 2.0 的革命

**1.x 旧写法(无类型提示):**
```python
class TUser(Base):
    __tablename__ = "t_user"
    id = Column(Integer, primary_key=True)
    userName = Column(String(200), comment="用户名称")  # IDE 不知道这是 str 类型
```

**2.0 新写法(Mapped 类型注解):**
```python
from sqlalchemy.orm import Mapped, mapped_column

class TUser(Base):
    __tablename__ = "t_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    userName: Mapped[Optional[str]] = mapped_column(VARCHAR(200), comment="用户名称")
    # IDE 现在知道 user.userName 是 Optional[str] 类型
```

**三大优势:**
1. **IDE 自动补全**: 输入 `user.` 后 IDE 能提示所有字段
2. **类型检查**: 如果写 `user.userName = 123`,IDE 会提示类型错误
3. **可空性明确**: `Optional[str]` 表示字段可为 NULL,避免运行时错误

### 2.2 完整模型定义解析

让我们看项目中的实际模型定义(`model/db_models.py`,共 201 行):

```python
import datetime
import decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Column,
    DECIMAL,
    Date,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    TIMESTAMP,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import LONGTEXT, TEXT, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from model.db_connection_pool import Base

"""
读取数据生成ORM数据库实体Bean
sqlacodegen mysql+pymysql://root:1@127.0.0.1:3306/chat_db --outfile=models.py
sqlacodegen mysql+pymysql://root:1@127.0.0.1:3306/chat_db --outfile=models.py --tables t_alarm_info --noviews
"""


class TAlarmInfo(Base):
    __tablename__ = "t_alarm_info"
    __table_args__ = {"comment": "诈骗数据"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    Incident_addr: Mapped[Optional[str]] = mapped_column(VARCHAR(1000), comment="案发地点")
    division_name: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="所属分局")
    call_in_type: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="来电类别")
    caller_name: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="报警人姓名")
    caller_sex: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="性别")
    caller_age: Mapped[Optional[int]] = mapped_column(Integer, comment="性别")
    caller_education: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="文化程度")
    caller_job: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="受害人职业")
    caller_phone_type: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="手机品牌")
    fraud_money: Mapped[Optional[float]] = mapped_column(Float, comment="涉案资金")
    is_fraud: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="是否电诈(是,否)")
    fraud_general_class: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="诈骗大类")
    drainage_type: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="引流方式")
    drainage_addr_account: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="引流地址、账号")
    drainage_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="引流联系时间")
    fraud_publicity: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="是否看(听)过反诈宣传(是,否)")
    registration_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="登记时间")


class TCustomers(Base):
    __tablename__ = "t_customers"
    __table_args__ = (Index("email", "email", unique=True), {"comment": "客户信息表"})

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="客户ID")
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="客户姓名")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="联系电话")
    email: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="电子邮箱")
    address: Mapped[Optional[str]] = mapped_column(Text, comment="地址")
    city: Mapped[Optional[str]] = mapped_column(String(50), comment="城市")
    country: Mapped[Optional[str]] = mapped_column(String(50), server_default=text("'中国'"), comment="国家")
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"
    )


class TOrderDetails(Base):
    __tablename__ = "t_order_details"
    __table_args__ = (
        Index("product_id", "product_id"),
        Index("uk_order_product", "order_id", "product_id", unique=True),
        {"comment": "销售订单明细表"},
    )

    detail_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="明细ID")
    order_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="订单ID")
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="产品ID")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="销售数量")
    unit_price: Mapped[decimal.Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, comment="销售时的单价")
    line_total: Mapped[decimal.Decimal] = mapped_column(
        DECIMAL(12, 2), nullable=False, comment="行小计(quantity * unit_price)"
    )
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class TProducts(Base):
    __tablename__ = "t_products"
    __table_args__ = {"comment": "产品信息表"}

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="产品ID")
    product_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="产品名称")
    category: Mapped[str] = mapped_column(VARCHAR(50), nullable=False, comment="产品类别")
    unit_price: Mapped[decimal.Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, comment="单价")
    stock_quantity: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"), comment="库存数量")
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"
    )


class TReportInfo(Base):
    __tablename__ = "t_report_info"
    __table_args__ = {"comment": "报告记录表"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="报告名称")
    markdown: Mapped[Optional[str]] = mapped_column(LONGTEXT, comment="报告内容")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="创建时间")


class TSalesOrders(Base):
    __tablename__ = "t_sales_orders"
    __table_args__ = (
        Index("customer_id", "customer_id"),
        Index("order_number", "order_number", unique=True),
        {"comment": "销售订单主表"},
    )

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="订单ID")
    order_number: Mapped[str] = mapped_column(VARCHAR(50), nullable=False, comment="订单编号")
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="客户ID")
    order_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment="订单日期")
    total_amount: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, comment="订单总金额")
    status: Mapped[Optional[str]] = mapped_column(
        Enum("Pending", "Shipped", "Delivered", "Cancelled"), server_default=text("'Pending'"), comment="订单状态"
    )
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"
    )


class TUser(Base):
    __tablename__ = "t_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    userName: Mapped[Optional[str]] = mapped_column(VARCHAR(200), comment="用户名称")
    password: Mapped[Optional[str]] = mapped_column(VARCHAR(300), comment="密码")
    mobile: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="手机号")
    createTime: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="创建时间")
    updateTime: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="修改时间")


class TUserQaRecord(Base):
    __tablename__ = "t_user_qa_record"
    __table_args__ = {"comment": "问答记录表"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, comment="用户id")
    uuid: Mapped[Optional[str]] = mapped_column(VARCHAR(200), comment="自定义id")
    conversation_id: Mapped[Optional[str]] = mapped_column(String(100), comment="diy/对话id")
    message_id: Mapped[Optional[str]] = mapped_column(String(100), comment="dify/消息id")
    task_id: Mapped[Optional[str]] = mapped_column(String(100), comment="dify/任务id")
    chat_id: Mapped[Optional[str]] = mapped_column(String(100), comment="对话id")
    question: Mapped[Optional[str]] = mapped_column(TEXT, comment="用户问题")
    to2_answer: Mapped[Optional[str]] = mapped_column(LONGTEXT, comment="大模型答案")
    to4_answer: Mapped[Optional[str]] = mapped_column(LONGTEXT, comment="业务数据")
    qa_type: Mapped[Optional[str]] = mapped_column(String(100), comment="问答类型")
    file_key: Mapped[Optional[str]] = mapped_column(String(100), comment="文件minio/key")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


t_view_alarm_detail = Table(
    "view_alarm_detail",
    Base.metadata,
    Column("案发地点", String(1000)),
    Column("所属分局", String(100)),
    Column("来电类别", String(100)),
    Column("报警人姓名", String(100)),
    Column("性别", String(100)),
    Column("年龄", Integer),
    Column("文化程度", String(100)),
    Column("受害人职业", String(100)),
    Column("手机品牌", String(100)),
    Column("涉案资金", Float),
    Column("是否电诈", String(100)),
    Column("诈骗类型", String(100)),
    Column("引流方式", String(100)),
    Column("引流地址", String(100)),
    Column("引流联系时间", DateTime),
    Column("是否看过反诈宣传", String(100)),
    Column("登记时间", DateTime),
)
```

**设计亮点:**

1. **类型注解完整**: 每个字段都标注了 `Mapped[类型]`,IDE 可实时检查
2. **可空性明确**: `Optional[str]` 表示 NULL 值,避免访问空值导致崩溃
3. **索引定义**: `__table_args__` 中定义唯一索引(email)和复合索引
4. **默认值设计**: `server_default=text("'中国'")` 由数据库生成默认值,减少应用层判断
5. **自动时间戳**: `ON UPDATE CURRENT_TIMESTAMP` 实现自动更新时间

**生成模型的工具提示:**
```bash
# 从现有数据库反向生成 ORM 模型
sqlacodegen mysql+pymysql://root:1@127.0.0.1:3306/chat_db --outfile=models.py
# 只生成指定表
sqlacodegen mysql+pymysql://root:1@127.0.0.1:3306/chat_db --outfile=models.py --tables t_alarm_info --noviews
```

---

## 三、连接池设计:单例模式的最佳实践

### 3.1 连接池的三大核心价值

**为什么需要连接池?**

不使用连接池的悲剧代码:
```python
# 每次请求都创建新连接 - 性能灾难
def get_user(user_id):
    conn = pymysql.connect(host="localhost", user="root", password="1", database="chat_db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM t_user WHERE id={user_id}")
    result = cursor.fetchone()
    cursor.close()
    conn.close()  # 如果代码异常,连接永远不会关闭!
    return result
```

**三大问题:**
1. **性能瓶颈**: 每次创建连接需要 TCP 三次握手 + MySQL 认证(约 50-100ms)
2. **连接泄漏**: 异常时 `conn.close()` 不执行,数据库连接数耗尽
3. **并发限制**: MySQL 默认最大连接数 151,高并发时直接拒绝服务

**连接池解决方案:**
- 预创建 10 个连接(pool_size=10)
- 复用连接,用完归还池中
- 自动检测失效连接(pool_pre_ping=True)

### 3.2 单例模式连接池实现

完整源码分析(`model/db_connection_pool.py`,共 101 行):

```python
"""
基于sqlalchemy ORM框架数据库连接池
"""

import logging
import os
import traceback
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class DBConnectionPool:
    """
    数据库连接池 (单例模式)
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBConnectionPool, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        try:
            # 防止重复初始化
            if DBConnectionPool._initialized:
                return

            # 获取数据库连接URI,如果环境变量不存在则使用默认值
            database_uri = os.getenv("SQLALCHEMY_DATABASE_URI", "mysql+pymysql://root:1@127.0.0.1:3306/chat_db")

            self.engine = create_engine(
                database_uri,
                pool_size=10,  # 连接池大小
                max_overflow=20,  # 连接池最大溢出大小
                pool_recycle=3600,  # 连接回收时间(秒),避免长时间连接失效
                pool_timeout=30,  # 连接池等待超时时间(秒)
                pool_pre_ping=True,  # 启用连接预检测,确保连接有效性
                echo=True,  # 是否打印SQL语句,用于调试
            )
            self.SessionLocal = sessionmaker(bind=self.engine)
            self.Base = Base
            DBConnectionPool._initialized = True

            logger.info("Database connection pool initialized.")
        except Exception as e:
            traceback.print_exception(e)
            logger.error(f"Error initializing database connection pool: {e}")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        获取数据库会话的上下文管理器
        用法:
        with db_pool.get_session() as session:
            # 使用session进行数据库操作
        """
        session: Session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            traceback.print_exception(e)
            session.rollback()
            raise
        finally:
            session.close()

    def get_engine(self):
        """
        获取数据库引擎
        :return: Engine
        """
        return self.engine

    def create_tables(self):
        """
        创建所有表
        """
        self.Base.metadata.create_all(self.engine)


# 提供全局访问点
def get_db_pool() -> DBConnectionPool:
    """
    获取数据库连接池实例
    :return: DBConnectionPool
    """
    return DBConnectionPool()
```

**核心设计解析:**

**1. 单例模式实现(防止多次初始化)**
```python
def __new__(cls):
    if cls._instance is None:
        cls._instance = super(DBConnectionPool, cls).__new__(cls)
    return cls._instance
```
- 无论调用多少次 `DBConnectionPool()`,都返回同一个实例
- 避免创建多个连接池导致连接数翻倍

**2. 连接池参数优化**
```python
self.engine = create_engine(
    database_uri,
    pool_size=10,          # 常驻连接10个
    max_overflow=20,       # 高峰时可临时增加20个(总共30个)
    pool_recycle=3600,     # 1小时回收连接(避免MySQL 8小时超时断开)
    pool_timeout=30,       # 获取连接超时时间
    pool_pre_ping=True,    # 使用前先 SELECT 1 测试连接是否有效
)
```

**参数选择依据:**
- `pool_size=10`: 单进程够用,Sanic 多进程模式下每进程独立池
- `max_overflow=20`: 应对突发流量,避免请求等待
- `pool_recycle=3600`: MySQL 默认 `wait_timeout=28800`(8小时),提前回收避免连接失效
- `pool_pre_ping=True`: 生产环境必开,防止使用已断开的连接

**3. 上下文管理器(自动提交/回滚)**
```python
@contextmanager
def get_session(self) -> Generator[Session, None, None]:
    session: Session = self.SessionLocal()
    try:
        yield session
        session.commit()  # 正常执行完自动提交
    except Exception as e:
        session.rollback()  # 异常时回滚
        raise
    finally:
        session.close()  # 无论如何都归还连接
```

**使用示例:**
```python
from model.db_connection_pool import get_db_pool

pool = get_db_pool()

# 方式1: 查询用户
with pool.get_session() as session:
    user = session.query(TUser).filter(TUser.userName == "admin").first()
    print(user.mobile)  # 自动提交

# 方式2: 插入数据(异常自动回滚)
with pool.get_session() as session:
    new_user = TUser(userName="test", password="123456")
    session.add(new_user)
    # with 结束时自动 commit
```

---

## 四、原生 SQL 工具:复杂查询的救星

### 4.1 为什么需要 MysqlUtil

ORM 在复杂查询时的局限性示例:

```python
# 需求:查询每个分局的诈骗案件数,筛选案件数>5的分局,按金额降序
# 使用 ORM 实现:代码冗长,难以理解
from sqlalchemy import func
result = (
    session.query(
        TAlarmInfo.division_name,
        func.count(TAlarmInfo.id).label("count"),
        func.avg(TAlarmInfo.fraud_money).label("avg_amount")
    )
    .filter(TAlarmInfo.is_fraud == "是")
    .group_by(TAlarmInfo.division_name)
    .having(func.count(TAlarmInfo.id) > 5)
    .order_by(func.avg(TAlarmInfo.fraud_money).desc())
    .all()
)

# 使用原生 SQL:清晰直观
sql = """
    SELECT division_name, COUNT(id) as count, AVG(fraud_money) as avg_amount
    FROM t_alarm_info
    WHERE is_fraud = '是'
    GROUP BY division_name
    HAVING count > 5
    ORDER BY avg_amount DESC
"""
result = mysql_util.query_mysql_dict(sql)
```

**结论:** 复杂查询直接写 SQL 更高效

### 4.2 MysqlUtil 工具类实现

完整源码(`common/mysql_util.py`,共 347 行,关键部分):

```python
import datetime
import json
import logging
import os

import pymysql

logger = logging.getLogger(__name__)


class MysqlUtil:
    """
    mysql工具类
    """

    def _get_connect(self):
        """
        获取mysql链接
        :return:
        """
        host = os.getenv("MYSQL_HOST")
        port = int(os.getenv("MYSQL_PORT"))
        user = os.getenv("MYSQL_USER")
        password = os.getenv("MYSQL_PASSWORD")
        database = os.getenv("MYSQL_DATABASE")

        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        return conn

    def query_mysql_dict(self, sql_query):
        """
        @param: sql_query 查询的sql语句
        @return 查询结果
        """
        # 获得链接
        conn = self._get_connect()
        # 获得游标
        cursor = conn.cursor()
        # 执行 SQL 查询语句
        cursor.execute(sql_query)
        # 获取查询结果
        rows = cursor.fetchall()
        index = cursor.description
        result = []
        for res in rows:
            row = {}
            for i in range(len(index)):
                if isinstance(res[i], datetime.datetime):
                    value = res[i].strftime("%Y-%m-%d %H:%M:%S")
                    row[index[i][0]] = value
                else:
                    row[index[i][0]] = res[i]

            result.append(row)

        # 关闭游标和数据库连接
        cursor.close()
        conn.close()
        return result

    def query_mysql_dict_params(self, sql_query, params=None):
        """
        执行带参数的SQL查询并返回结果字典列表。

        :param sql_query: 查询的SQL语句,可以包含占位符(%s)
        :param params: SQL语句中的参数列表或元组,默认为None
        :return: 查询结果的字典列表
        """
        conn = None
        cursor = None
        try:
            # 获得链接
            conn = self._get_connect()
            # 获得游标
            cursor = conn.cursor()
            # 执行 SQL 查询语句
            cursor.execute(sql_query, params or ())
            # 获取查询结果
            rows = cursor.fetchall()
            index = cursor.description

            result = []
            for res in rows:
                row = {}
                for i in range(len(index)):
                    if isinstance(res[i], datetime.datetime):
                        value = res[i].strftime("%Y-%m-%d %H:%M:%S")
                        row[index[i][0]] = value
                    else:
                        row[index[i][0]] = res[i]

                result.append(row)

            return result
        finally:
            cursor.close()
            conn.close()

    def insert(self, sql: str, params: tuple):
        """
        插入数据并返回插入记录的ID
        :param sql:
        :param params:
        :return:
        """
        conn = self._get_connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                inserted_id = cursor.lastrowid  # 获取插入记录的 ID
            conn.commit()
        finally:
            conn.close()
        return inserted_id

    def update_params(self, sql: str, params: []):
        """
        更新数据
        :param sql:
        :param params:
        :return:
        """
        # 获得链接
        conn = self._get_connect()
        # 获得游标
        cursor = conn.cursor()
        # 执行 SQL 查询语句
        cursor.execute(sql, params)
        # 获取查询结果
        result = cursor.fetchall()
        conn.commit()
        # 关闭游标和数据库连接
        cursor.close()
        conn.close()
        return result

    def batch_insert(self, sql: str, data_list: list):
        """
        执行批量插入操作。

        :param sql: 插入语句模板,其中应包含占位符(%s),用于后续的数据填充。
        :param data_list: 包含要插入数据的列表,每个元素都是一个元组或列表,
                          对应于单次插入操作中的所有字段值。
        :return: 成功时返回True,失败时抛出异常。
        """
        conn = None
        try:
            # 获得链接
            conn = self._get_connect()
            # 获得游标
            with conn.cursor() as cursor:
                # 使用 executemany 方法进行批量插入
                cursor.executemany(sql, data_list)
            # 提交事务
            conn.commit()
            return True
        except pymysql.MySQLError as e:
            logger.error(f"batch_insert error {e}")
            conn.rollback()  # 发生错误时回滚事务
            raise  # 抛出异常给调用者处理
        finally:
            if conn:
                conn.close()

    def query_ex(self, query: str):
        """
        Execute SQL and return column desc and result

        Args:
            query SQL query to run

        Returns:
            Json: {"column":[],result:[]}
        """
        logger.info(f"query_sql: {query}")
        if not query:
            return json.dumps({"column": [], "result": []})

        connection = None
        try:
            connection = self._get_connect()
            with connection.cursor() as cursor:
                # 执行SQL查询
                cursor.execute(query)
                # 获取查询结果的字段名称
                column_names = [desc[0] for desc in cursor.description]
                # 获取查询结果
                rows = cursor.fetchall()

                # 将查询结果转换为指定格式
                result = []
                index = cursor.description
                for res in rows:
                    row = {}
                    for i in range(len(index)):
                        if isinstance(res[i], datetime.datetime):
                            value = res[i].strftime("%Y-%m-%d %H:%M:%S")
                            row[index[i][0]] = value
                        else:
                            row[index[i][0]] = res[i]
                    result.append(row)

                return {"column": column_names, "result": result}
        except pymysql.MySQLError as e:
            logger.error(f"query_ex error query_sql: {query},{e}")
            return None
        finally:
            if connection:
                connection.close()
```

**核心方法解析:**

**1. 查询返回字典(自动处理日期类型)**
```python
def query_mysql_dict(self, sql_query):
    # 执行查询
    cursor.execute(sql_query)
    rows = cursor.fetchall()
    index = cursor.description  # 获取列名

    result = []
    for res in rows:
        row = {}
        for i in range(len(index)):
            if isinstance(res[i], datetime.datetime):
                value = res[i].strftime("%Y-%m-%d %H:%M:%S")  # 日期转字符串
                row[index[i][0]] = value
            else:
                row[index[i][0]] = res[i]
        result.append(row)
    return result
```

**2. 参数化查询(防止 SQL 注入)**
```python
def query_mysql_dict_params(self, sql_query, params=None):
    cursor.execute(sql_query, params or ())  # 使用占位符 %s
```

**使用示例:**
```python
# 危险写法 - SQL 注入风险
user_name = "admin' OR '1'='1"
sql = f"SELECT * FROM t_user WHERE userName='{user_name}'"  # 会查出所有用户!

# 安全写法 - 参数化查询
sql = "SELECT * FROM t_user WHERE userName=%s"
result = mysql_util.query_mysql_dict_params(sql, (user_name,))
```

**3. 批量插入(executemany 比循环快 10 倍)**
```python
def batch_insert(self, sql: str, data_list: list):
    with conn.cursor() as cursor:
        cursor.executemany(sql, data_list)  # 一次性提交多条
    conn.commit()
```

**使用示例:**
```python
sql = "INSERT INTO t_user (userName, password) VALUES (%s, %s)"
data_list = [
    ("user1", "pass1"),
    ("user2", "pass2"),
    ("user3", "pass3"),
]
mysql_util.batch_insert(sql, data_list)  # 比循环 insert 快 10 倍
```

---

## 五、数据库初始化脚本

### 5.1 一键初始化的必要性

**开发场景:**
- 新同事加入项目,需要快速搭建本地数据库
- 测试环境需要初始化示例数据
- CI/CD 流水线需要自动化部署数据库

**解决方案:** 提供 `initialize_mysql.py` 脚本

### 5.2 初始化脚本实现

完整源码(`common/initialize_mysql.py`,共 143 行):

```python
import pymysql
import os

from pymysql import MySQLError

"""
Mysql 初始化脚本工具类
"""

# 配置信息
MYSQL_ROOT_PASSWORD = "1"  # MySQL root 用户的密码
SQL_FILE = "../docker/init_sql.sql"  # SQL 文件路径
HOST = "localhost"  # MySQL 服务器地址
PORT = 3306  # MySQL 服务器端口


def check_sql_file(file_path):
    """
    检查 SQL 文件是否存在
    :param file_path:
    :return:
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Error: SQL file {file_path} not found.")


def execute_sql_file(file_path):
    """
    执行 SQL 文件
    :param file_path:
    :return:
    """
    try:
        # 创建数据库连接
        connection = pymysql.connect(
            host=HOST,
            user="root",
            password=MYSQL_ROOT_PASSWORD,
            port=PORT,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        with connection.cursor() as cursor:
            print(f"Initializing MySQL with {file_path} on port {PORT}...")

            # 读取 SQL 文件
            with open(file_path, "r", encoding="utf-8") as file:
                sql_script = file.read()

            # 分割 SQL 命令并执行
            commands = sql_script.split(";")
            for command in commands:
                if command.strip():  # 忽略空命令
                    cursor.execute(command)

            # 提交事务
            connection.commit()
            print("MySQL initialization completed successfully.")
    except pymysql.MySQLError as e:
        print(f"Error: {e}")
    finally:
        if connection.open:
            connection.close()


def execute_user_qa_record_sql():
    """
    使用 pymysql 连接数据库并执行 SQL 语句。
    初始化特殊结构json数据
    """

    sql_insert_data = """
    INSERT INTO chat_db.t_user_qa_record (user_id,uuid,conversation_id,message_id,task_id,chat_id,question,to2_answer,
    to4_answer,qa_type,file_key,create_time) VALUES(%s, %s, %s,%s, %s, %s, %s, %s, %s, %s,%s,%s)
    """
    # 紧凑格式数据,去掉换行
    data_to_insert = [
        (
            1,
            "82766aca-146d-44ac-9280-fc829991848f",
            "ed0ea22a-4403-4e9d-8947-92899b8f1b73",
            "eafb17a3-0fa3-4f99-b9db-196d4de12df3",
            "09e16efa-dedf-421a-b944-93537a8ff9cf",
            "3b542378-c492-4063-8c25-2e20e2d9428d",
            "统计案件数据按分局分组饼图",
            r'{"data": {"messageType": "continue", "content": "## 数据趋势概述  \n不同分局事件数量存在明显差异  \n\n**关键发现**  \n- '
            r'徐汇分局事件数最多,达10起  \n- 浦东分局次之(7起),朝阳、天河、海淀分局并列第三(各4起)  \n- 武侯、徐汇分局呈现极端值特征  \n\n**注意**  \n数据反映的是静态总量分布,未包含时间维度变化信息"}, "dataType": "t02"}',
            r'{"data": {"chart_type": "饼图", "template_code": "temp02", "data": [{"name": "浦东分局", "value": "7", '
            r'"percent": false}, {"name": "朝阳分局", "value": "4", "percent": false}, {"name": "天河分局", "value": "4", "percent": false}, {"name": "南山分局", "value": "3", "percent": false}, {"name": "武侯分局", "value": "1", "percent": false}, {"name": "锦江分局", "value": "2", "percent": false}, {"name": "徐汇分局", "value": "10", "percent": false}, {"name": "海淀分局", "value": "4", "percent": false}, {"name": "白云分局", "value": "3", "percent": false}, {"name": "福田分局", "value": "2", "percent": false}], "note": "数据来源: xxx数据库,以上数据仅供参考,具体情况可能会根据xx进一步调查和统计而有所变化"}, "dataType": "t04"}',
            "DATABASE_QA",
            "",
            "2025-07-09 14:35:42",
        ),
        (
            1,
            "db2d6f8c-f990-43a9-ba21-79dfcbb43c17",
            "38ad9103-d37b-4652-a9bf-cfebcfe3c9d6",
            "f3536814-65f6-4848-83a8-26429f5c71f9",
            "d4b18b90-8085-4d42-8fd5-b57f6b61b7a4",
            "3b542378-c492-4063-8c25-2e20e2d9428d",
            "统计案件数据按分局分组柱状图",
            r'{"data": {"messageType": "continue", "content": "## 分局案件数量分布趋势  '
            r'\n\n从数据来看,各分局的案件总数呈现出明显的区域差异。**徐汇分局以10起案件位居首位**,其次是**浦东分局(7起)和朝阳、天河、海淀分局(均为4起)**,其他分局案件数均低于3起。  \n\n**关键发现**  \n- 徐汇分局案件数量最多,是最低值的10倍  \n- 三个分局并列第二梯队,案件数为4起  \n- 超过半数分局案件数≤2起  \n\n**注意**  \n该数据未体现时间维度变化,仅反映静态总量分布情况,建议补充时间序列数据以分析动态趋势。"}, "dataType": "t02"}',
            r'{"data": {"chart_type": "柱状图", "template_code": "temp03", "data": [["product", "总数"], ["浦东分局", "7"], '
            r'["朝阳分局", "4"], ["天河分局", "4"], ["南山分局", "3"], ["武侯分局", "1"], ["锦江分局", "2"], ["徐汇分局", "10"], ["海淀分局", "4"], ["白云分局", "3"], ["福田分局", "2"]], "note": "数据来源: xxx数据库,以上数据仅供参考,具体情况可能会根据xx进一步调查和统计而有所变化"}, "dataType": "t04"}',
            "DATABASE_QA",
            "",
            "2025-07-09 14:36:41",
        ),
    ]

    # 创建数据库连接
    connection = pymysql.connect(
        host=HOST,
        user="root",
        password=MYSQL_ROOT_PASSWORD,
        port=PORT,
        db="chat_db",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )

    try:
        with connection.cursor() as cursor:
            # 使用 executemany 方法插入多条数据
            cursor.executemany(sql_insert_data, data_to_insert)
        # 提交事务
        connection.commit()
    except MySQLError as e:
        print(f"Error executing query: {e}")
        # 如果出现错误,则回滚事务
        if connection.open:
            connection.rollback()
    finally:
        # 关闭数据库连接
        connection.close()


if __name__ == "__main__":
    check_sql_file(SQL_FILE)
    execute_sql_file(SQL_FILE)
    execute_user_qa_record_sql()
```

**执行流程:**
1. 检查 `init_sql.sql` 文件是否存在
2. 连接 MySQL(不指定数据库,因为数据库可能不存在)
3. 执行 SQL 文件(创建数据库 + 表结构)
4. 插入测试数据(JSON 格式的问答记录)

**使用方法:**
```bash
cd common
uv run python initialize_mysql.py
```

---

## 六、双引擎实战:用户查询示例

### 6.1 ORM 方式(简单查询)

```python
from model.db_connection_pool import get_db_pool
from model.db_models import TUser
from sqlalchemy.orm import Session

pool = get_db_pool()

async def get_user_by_name(username: str):
    with pool.get_session() as session:
        session: Session = session
        user = session.query(TUser).filter(TUser.userName == username).first()
        return user
```

### 6.2 原生 SQL 方式(复杂查询)

```python
from common.mysql_util import MysqlUtil

mysql_client = MysqlUtil()

async def get_fraud_statistics():
    sql = """
        SELECT
            division_name,
            COUNT(*) as total_cases,
            SUM(fraud_money) as total_amount,
            AVG(fraud_money) as avg_amount
        FROM t_alarm_info
        WHERE is_fraud = '是'
        GROUP BY division_name
        ORDER BY total_amount DESC
        LIMIT 10
    """
    return mysql_client.query_mysql_dict(sql)
```

---

## 七、本章总结

### 7.1 核心要点回顾

1. **SQLAlchemy 2.0 Mapped 类型注解**: 提供类型安全和 IDE 支持
2. **单例模式连接池**: 避免重复创建连接,提高性能
3. **双引擎策略**: ORM 处理 CRUD,原生 SQL 处理复杂查询
4. **参数化查询**: 防止 SQL 注入攻击
5. **初始化脚本**: 支持快速部署和测试

### 7.2 最佳实践建议

**选择 ORM 的场景:**
- 单表查询
- 简单的增删改查
- 需要类型检查的业务逻辑

**选择原生 SQL 的场景:**
- 多表关联查询
- 复杂的统计分析
- 需要使用数据库特定函数

### 7.3 下一章预告

下一章我们将学习 **JWT 认证 + 异常处理**,实现无状态的用户鉴权机制。

---

**完整文件清单:**
- `model/db_connection_pool.py` (101 行)
- `model/db_models.py` (201 行)
- `common/mysql_util.py` (347 行)
- `common/initialize_mysql.py` (143 行)
