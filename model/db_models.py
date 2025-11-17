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
    is_fraud: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="是否电诈(是，否）")
    fraud_general_class: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="诈骗大类")
    drainage_type: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="引流方式")
    drainage_addr_account: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="引流地址、账号")
    drainage_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="引流联系时间")
    fraud_publicity: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="是否看（听）过反诈宣传(是，否）")
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
        DECIMAL(12, 2), nullable=False, comment="行小计（quantity * unit_price）"
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
