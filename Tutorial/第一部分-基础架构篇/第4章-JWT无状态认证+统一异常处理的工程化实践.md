# 第4章 JWT 无状态认证 + 统一异常处理的工程化实践

## 章节目标

1. 理解 JWT 无状态认证相比 Session 的优势,掌握分布式场景下的鉴权设计
2. 学会自定义异常类设计,实现业务异常与系统异常的分层处理
3. 掌握装饰器模式统一 API 响应格式,减少 80% 的重复代码
4. 实践完整的用户认证流程,包括登录、Token 生成、Token 验证和用户信息提取

## 一、为什么需要 JWT 而不是 Session

### 1.1 传统 Session 认证的痛点

**传统流程:**
```
1. 用户登录 → 服务器生成 Session ID → 存储到 Redis/内存
2. 返回 Session ID 给前端(通过 Cookie)
3. 前端每次请求携带 Session ID
4. 服务器从 Redis 查询 Session 验证用户身份
```

**三大问题:**

**问题1:水平扩展困难**
```
用户请求 → Nginx 负载均衡 → 服务器A(有 Session)
用户请求 → Nginx 负载均衡 → 服务器B(无 Session,需要 Sticky Session 或 Redis 共享)
```

**问题2:Redis 依赖**
```python
# 每次请求都要查 Redis
session_id = request.cookies.get("session_id")
user_info = redis_client.get(f"session:{session_id}")  # 增加网络IO
if not user_info:
    return "未登录"
```

**问题3:跨域麻烦**
- Cookie 不能跨域共享(api.example.com 和 www.example.com 需要特殊配置)

### 1.2 JWT 无状态认证的优势

**JWT 流程:**
```
1. 用户登录 → 服务器生成 JWT Token(包含用户信息 + 签名)
2. 返回 Token 给前端
3. 前端每次请求在 Header 中携带 Token
4. 服务器验证签名,解码 Token 获取用户信息(无需查数据库/Redis)
```

**JWT 结构示例:**
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjEiLCJ1c2VybmFtZSI6ImFkbWluIiwiZXhwIjoxNzMwMDAwMDAwfQ.signature
|------------ Header -----------|.|----- Payload(用户信息) -----|.|-- Signature(签名) --|
```

**三大优势:**
1. **无状态**: 服务器不存储 Session,Token 自包含用户信息
2. **易扩展**: 多台服务器共享同一个密钥即可,无需 Redis
3. **跨域友好**: Token 放在 HTTP Header 中,不受 Cookie 跨域限制

**唯一缺点:** Token 一旦签发无法主动失效(解决方案:设置短过期时间 + Refresh Token)

---

## 二、自定义异常设计:业务异常分层处理

### 2.1 为什么需要自定义异常

**反面案例(直接抛出 Python 内置异常):**
```python
@app.route("/api/user")
async def get_user(request):
    token = request.headers.get("Authorization")
    if not token:
        raise Exception("未登录")  # 问题:前端收到 500 错误,不知道具体原因
    # ...
```

**前端收到的响应:**
```json
{
  "error": "Internal Server Error",
  "status": 500
}
// 前端无法区分是"未登录"还是"数据库崩溃"
```

**正确做法(自定义异常 + 错误码):**
```python
raise MyException(SysCodeEnum.c_401)  # 401 未登录
raise MyException(SysCodeEnum.c_9999)  # 9999 系统异常
```

**前端收到的响应:**
```json
{
  "code": 401,
  "msg": "登录异常",
  "data": null
}
// 前端可以根据 code 做不同处理:401 跳转登录页,9999 提示系统错误
```

### 2.2 异常枚举定义

完整源码(`constants/code_enum.py`,共 58 行):

```python
from enum import Enum


class SysCodeEnum(Enum):
    """
    系统状态码定义
    """

    c_200 = (200, "ok", "ok")

    c_401 = (401, "登录异常", "登录异常")

    c_400 = (401, "无效Token", "无效Token")

    c_9999 = (9999, "系统异常", "系统异常")


class DiFyAppEnum(Enum):
    """
    DiFy app-key 枚举
    """

    DATABASE_QA = ("DATABASE_QA", "数据问答")

    FILEDATA_QA = ("FILEDATA_QA", "表格问答")

    COMMON_QA = ("COMMON_QA", "智能问答")

    REPORT_QA = ("REPORT_QA", "深度搜索")


class DataTypeEnum(Enum):
    """
    自定义数据类型枚举
    """

    ANSWER = ("t02", "答案")

    LOCATION = ("t03", "溯源")

    BUS_DATA = ("t04", "业务数据")

    TASK_ID = ("t11", "任务ID,方便后续点赞等操作")

    STREAM_END = ("t99", "流式推流结束")


class DiFyCodeEnum(Enum):
    """
    DiFy 返回数据流定义
    """

    MESSAGE = ("message", "答案")

    MESSAGE_END = ("message_end", "结束")

    MESSAGE_ERROR = ("error", "错误")
```

**设计要点:**
1. **元组结构**: `(错误码, 错误消息, 详细信息)`
2. **语义化命名**: `c_401` 表示 HTTP 401 未授权
3. **可扩展**: 新增错误码只需添加枚举值

### 2.3 自定义异常类实现

完整源码(`common/exception.py`,共 42 行):

```python
from constants.code_enum import SysCodeEnum


class MyException(Exception):
    """
    自定义异常类,用于处理特定业务逻辑中的异常情况。

    该类继承自内置的 Exception 类,接收一个 SysCodeEnum 类型的参数,
    从中提取错误代码、错误消息和详细信息。
    """

    def __init__(self, ex_code: SysCodeEnum, detail: str = ""):
        """
        初始化自定义异常实例。

        Args:
            ex_code (SysCodeEnum): 错误代码枚举值,包含错误代码、错误消息和详细信息。
            detail (str, optional): 额外的错误详细信息,默认为空字符串。
        """
        self.code = ex_code.value[0]
        self.message = ex_code.value[1]
        self.detail = ex_code.value[2] if not detail else detail
        super().__init__(f"{ex_code.name}({self.code}): {self.message} - {self.detail}")

    def __str__(self) -> str:
        """
        返回异常的字符串表示形式,包含错误代码、错误消息和详细信息。

        Returns:
            str: 异常的字符串表示。
        """
        return f"MyException: code: {self.code}, message: {self.message} - detail: {self.detail}"

    def to_dict(self) -> dict:
        """
        将异常信息转换为字典格式,方便在 API 响应中返回。

        Returns:
            dict: 包含错误代码和错误消息的字典。
        """
        return {"code": self.code, "message": self.message}
```

**使用示例:**
```python
from common.exception import MyException
from constants.code_enum import SysCodeEnum

# 场景1:用户未登录
if not token:
    raise MyException(SysCodeEnum.c_401)

# 场景2:Token 无效
try:
    payload = jwt.decode(token, SECRET_KEY)
except:
    raise MyException(SysCodeEnum.c_400)

# 场景3:系统异常(带自定义详情)
try:
    result = complex_operation()
except Exception as e:
    raise MyException(SysCodeEnum.c_9999, detail=str(e))
```

---

## 三、统一响应装饰器:消灭重复代码

### 3.1 传统写法的重复代码问题

**反面案例(每个接口都要写一遍异常处理):**
```python
@app.route("/api/user")
async def get_user(request):
    try:
        # 业务逻辑
        user = await user_service.get_user(user_id)
        return response.json({"code": 200, "msg": "ok", "data": user})
    except MyException as e:
        return response.json({"code": e.code, "msg": e.message, "data": None})
    except Exception as e:
        return response.json({"code": 9999, "msg": "系统异常", "data": None})

@app.route("/api/order")
async def get_order(request):
    try:
        # 业务逻辑
        order = await order_service.get_order(order_id)
        return response.json({"code": 200, "msg": "ok", "data": order})
    except MyException as e:
        return response.json({"code": e.code, "msg": e.message, "data": None})
    except Exception as e:
        return response.json({"code": 9999, "msg": "系统异常", "data": None})
```

**问题:** 每个接口都复制粘贴异常处理代码,维护成本高

### 3.2 装饰器模式统一处理

完整源码(`common/res_decorator.py`,共 97 行):

```python
import json
import logging
import traceback
from datetime import date, datetime
from functools import wraps

from sanic import response

from common.exception import MyException
from constants.code_enum import SysCodeEnum


class CustomJSONEncoder(json.JSONEncoder):
    """
    自定义的 JSON 编码器,用于处理日期类型
    """

    def default(self, obj):
        """
        处理 Python 对象序列化
        :param obj:
        :return:
        """
        if isinstance(obj, date):
            # 处理 date 类型
            return obj.strftime("%Y-%m-%d")
        elif isinstance(obj, datetime):
            # 处理 datetime 类型
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        return super().default(obj)


def async_json_resp(func):
    """
    Decorator for asynchronous json response
    """

    @wraps(func)
    async def http_res_wrapper(request, *args, **kwargs):
        """
        统一响应处理包装器
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        data = None
        # 获取请求方法和参数
        method = request.method
        path = request.path
        params = request.args
        content_type = request.content_type
        content_types = ["application/json"]
        if content_type in content_types:
            json_body = request.json if request.json else {}
        else:
            json_body = ""

        try:
            data = await func(request, *args, **kwargs)
            body = {
                "code": SysCodeEnum.c_200.value[0],
                "msg": SysCodeEnum.c_200.value[1],
                "data": data,
            }
            res = response.json(body, dumps=CustomJSONEncoder().encode)

            logging.info(f"Request Path: {path},Method: {method}, Params: {params}, JSON Body: {json_body}, Response: {body}")

            return res

        except MyException as e:
            body = {
                "code": e.code,
                "msg": e.message,
                "data": data,
            }

            res = response.json(body, dumps=CustomJSONEncoder().encode)

            logging.info(f"Request Path: {path}, Method: {method},Params: {params}, JSON Body: {json_body}, Response: {body}")
            return res

        except Exception as e:
            body = {
                "code": SysCodeEnum.c_9999.value[0],
                "msg": SysCodeEnum.c_9999.value[1],
                "data": data,
            }
            res = response.json(body, dumps=CustomJSONEncoder().encode)

            logging.info(f"Request Path: {path}, Method: {method},Params: {params}, JSON Body: {json_body}, Response: {body}")

            traceback.print_exception(e)
            return res

    return http_res_wrapper
```

**三大核心功能:**

**1. 自动处理日期序列化**
```python
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")  # datetime 转字符串
        return super().default(obj)
```

**问题:** Python 的 `datetime` 对象无法直接序列化为 JSON
**解决:** 自定义 JSON 编码器,自动将日期转为字符串

**2. 统一响应格式**
```python
{
    "code": 200,      # 业务状态码
    "msg": "ok",      # 提示消息
    "data": {...}     # 实际数据
}
```

**3. 三层异常处理**
```python
try:
    data = await func(request, *args, **kwargs)  # 执行业务逻辑
    return {"code": 200, "msg": "ok", "data": data}
except MyException as e:  # 业务异常
    return {"code": e.code, "msg": e.message, "data": None}
except Exception as e:  # 系统异常
    return {"code": 9999, "msg": "系统异常", "data": None}
```

### 3.3 使用装饰器后的简洁代码

```python
from common.res_decorator import async_json_resp

@app.route("/api/user")
@async_json_resp  # 只需加这一行装饰器
async def get_user(request):
    user = await user_service.get_user(user_id)
    return user  # 直接返回数据,装饰器自动包装成 {"code": 200, "msg": "ok", "data": user}

@app.route("/api/order")
@async_json_resp
async def get_order(request):
    order = await order_service.get_order(order_id)
    return order  # 装饰器自动处理异常和响应格式
```

**效果对比:**
- 传统写法: 每个接口 20 行代码(包含异常处理)
- 装饰器方式: 每个接口 3 行代码(减少 85% 代码量)

---

## 四、JWT 认证实现:从登录到鉴权的完整流程

### 4.1 用户登录与 Token 生成

完整源码(`services/user_service.py`,共 359 行,关键部分):

```python
import json
import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import List, Any

import jwt
import requests
from sqlalchemy.orm import Session

from common.exception import MyException
from common.mysql_util import MysqlUtil
from constants.code_enum import SysCodeEnum, DiFyAppEnum, DataTypeEnum
from constants.dify_rest_api import DiFyRestApi
from model.db_connection_pool import get_db_pool
from model.db_models import TUserQaRecord, TUser
from model.serializers import model_to_dict

logger = logging.getLogger(__name__)

mysql_client = MysqlUtil()
pool = get_db_pool()


async def authenticate_user(username, password):
    """验证用户凭据并返回用户信息或 None"""
    with pool.get_session() as session:
        session: Session = session
        user_dict = model_to_dict(
            session.query(TUser).filter(TUser.userName == username).filter(TUser.password == password).first()
        )
        if user_dict:
            return user_dict
        return False


async def generate_jwt_token(user_id, username):
    """生成 JWT token"""
    payload = {
        "id": str(user_id),
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=24),
    }  # Token 过期时间
    token = jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")
    return token


async def decode_jwt_token(token):
    """解析 JWT token 并返回 payload"""
    try:
        # 使用与生成 token 时相同的密钥和算法来解码 token
        payload = jwt.decode(token, key=os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
        # 检查 token 是否过期
        if "exp" in payload and datetime.utcfromtimestamp(payload["exp"]) < datetime.utcnow():
            raise jwt.ExpiredSignatureError("Token has expired")
        return payload
    except jwt.ExpiredSignatureError as e:
        # 处理过期的 token
        return None, 401, str(e)
    except jwt.InvalidTokenError as e:
        # 处理无效的 token
        return None, 400, str(e)
    except Exception as e:
        # 处理其他可能的错误
        return None, 500, str(e)


async def get_user_info(request) -> dict:
    """获取登录用户信息"""
    token = request.headers.get("Authorization")

    # 检查 Authorization 头是否存在
    if not token:
        logging.error("Authorization header is missing")
        raise MyException(SysCodeEnum.c_401)

    # 检查 Authorization 头格式是否正确
    if not token.startswith("Bearer "):
        logging.error("Invalid Authorization header format")
        raise MyException(SysCodeEnum.c_400)

    # 提取 token
    token = token.split(" ")[1].strip()

    # 检查 token 是否为空
    if not token:
        logging.error("Token is empty or whitespace")
        raise MyException(SysCodeEnum.c_400)

    try:
        # 解码 JWT token
        user_info = await decode_jwt_token(token)
    except Exception as e:
        logging.error(f"Failed to decode JWT token: {e}")
        raise MyException(SysCodeEnum.c_401)

    return user_info
```

**关键方法解析:**

**1. 用户登录验证**
```python
async def authenticate_user(username, password):
    with pool.get_session() as session:
        user = session.query(TUser)\
            .filter(TUser.userName == username)\
            .filter(TUser.password == password)\
            .first()
        if user:
            return model_to_dict(user)  # 转为字典返回
        return False
```

**注意:** 生产环境密码需要加密(bcrypt/argon2),这里简化处理

**2. JWT Token 生成**
```python
async def generate_jwt_token(user_id, username):
    payload = {
        "id": str(user_id),
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=24),  # 24小时后过期
    }
    token = jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")
    return token
```

**JWT Payload 包含:**
- `id`: 用户ID(用于后续查询用户数据)
- `username`: 用户名(用于日志记录)
- `exp`: 过期时间(Unix 时间戳)

**3. Token 验证与解析**
```python
async def decode_jwt_token(token):
    try:
        payload = jwt.decode(token, key=os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
        # 检查是否过期
        if datetime.utcfromtimestamp(payload["exp"]) < datetime.utcnow():
            raise jwt.ExpiredSignatureError("Token has expired")
        return payload
    except jwt.ExpiredSignatureError:
        return None, 401, "Token 已过期"
    except jwt.InvalidTokenError:
        return None, 400, "无效 Token"
```

**安全检查点:**
1. 验证签名(防止 Token 被篡改)
2. 检查过期时间(防止 Token 被永久使用)
3. 捕获解析异常(防止畸形 Token 导致崩溃)

**4. 从请求头提取用户信息**
```python
async def get_user_info(request) -> dict:
    token = request.headers.get("Authorization")

    # 检查1: Authorization 头是否存在
    if not token:
        raise MyException(SysCodeEnum.c_401)

    # 检查2: 格式是否为 "Bearer <token>"
    if not token.startswith("Bearer "):
        raise MyException(SysCodeEnum.c_400)

    # 提取 token
    token = token.split(" ")[1].strip()

    # 检查3: token 不为空
    if not token:
        raise MyException(SysCodeEnum.c_400)

    # 解码获取用户信息
    user_info = await decode_jwt_token(token)
    return user_info
```

**HTTP Header 示例:**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjEiLCJ1c2VybmFtZSI6ImFkbWluIn0.xxx
```

### 4.2 完整登录流程示例

**Controller 层(controllers/user_controller.py):**
```python
from sanic import Blueprint
from common.res_decorator import async_json_resp
from services.user_service import authenticate_user, generate_jwt_token

bp = Blueprint("user", url_prefix="/api/user")

@bp.post("/login")
@async_json_resp
async def login(request):
    """用户登录"""
    data = request.json
    username = data.get("username")
    password = data.get("password")

    # 验证用户
    user = await authenticate_user(username, password)
    if not user:
        raise MyException(SysCodeEnum.c_401, detail="用户名或密码错误")

    # 生成 Token
    token = await generate_jwt_token(user["id"], user["userName"])

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["userName"],
        }
    }

@bp.get("/info")
@async_json_resp
async def get_current_user(request):
    """获取当前登录用户信息"""
    user_info = await get_user_info(request)  # 自动从 Header 提取 Token
    return user_info
```

**前端调用示例:**
```javascript
// 1. 登录
const loginRes = await fetch("/api/user/login", {
  method: "POST",
  body: JSON.stringify({ username: "admin", password: "123456" }),
  headers: { "Content-Type": "application/json" }
});
const { token } = await loginRes.json();

// 2. 存储 Token
localStorage.setItem("token", token);

// 3. 后续请求携带 Token
const userRes = await fetch("/api/user/info", {
  headers: {
    "Authorization": `Bearer ${token}`
  }
});
const userData = await userRes.json();
```

---

## 五、最佳实践:安全加固建议

### 5.1 Token 泄漏风险防护

**问题:** JWT Token 一旦泄漏,攻击者可以冒充用户

**解决方案:**
1. **HTTPS 传输**: 防止中间人截获 Token
2. **短过期时间**: 24 小时过期,减少泄漏窗口期
3. **Refresh Token**: 长期 Token 存储在 HttpOnly Cookie 中,短期 Token 用于 API 请求

**Refresh Token 实现思路:**
```python
# 登录时返回两个 Token
{
    "access_token": "短期Token(1小时)",
    "refresh_token": "长期Token(7天,存储在 HttpOnly Cookie)"
}

# access_token 过期时,用 refresh_token 换取新 access_token
@bp.post("/refresh")
async def refresh_token(request):
    refresh_token = request.cookies.get("refresh_token")
    # 验证 refresh_token 并生成新 access_token
    new_access_token = generate_jwt_token(user_id, username)
    return {"access_token": new_access_token}
```

### 5.2 密码存储安全

**反面案例(明文存储密码):**
```python
# 数据库中存储: password = "123456"
# 数据库泄漏 = 所有用户密码泄漏
```

**正确做法(bcrypt 加密):**
```python
import bcrypt

# 注册时加密
password_hash = bcrypt.hashpw("123456".encode(), bcrypt.gensalt())
# 存储: password = "$2b$12$KIXxZ...."

# 登录时验证
is_valid = bcrypt.checkpw("123456".encode(), password_hash)
```

### 5.3 防止 SQL 注入

**已在第3章 MysqlUtil 中实现参数化查询:**
```python
# 安全写法
sql = "SELECT * FROM t_user WHERE userName=%s AND password=%s"
result = mysql_client.query_mysql_dict_params(sql, (username, password))
```

---

## 六、实战演练:完整的用户认证接口

### 6.1 用户登录接口

```python
from sanic import Blueprint
from common.res_decorator import async_json_resp
from common.exception import MyException
from constants.code_enum import SysCodeEnum
from services.user_service import authenticate_user, generate_jwt_token

bp = Blueprint("auth", url_prefix="/api/auth")

@bp.post("/login")
@async_json_resp
async def login(request):
    """
    用户登录
    请求体:
    {
        "username": "admin",
        "password": "123456"
    }
    """
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        raise MyException(SysCodeEnum.c_400, detail="用户名和密码不能为空")

    # 验证用户
    user = await authenticate_user(username, password)
    if not user:
        raise MyException(SysCodeEnum.c_401, detail="用户名或密码错误")

    # 生成 Token
    token = await generate_jwt_token(user["id"], user["userName"])

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["userName"],
            "mobile": user.get("mobile"),
        }
    }
```

**响应示例:**
```json
{
  "code": 200,
  "msg": "ok",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "id": 1,
      "username": "admin",
      "mobile": "13800138000"
    }
  }
}
```

### 6.2 获取当前用户信息接口

```python
@bp.get("/user/info")
@async_json_resp
async def get_current_user_info(request):
    """
    获取当前登录用户信息
    请求头:
    Authorization: Bearer <token>
    """
    user_info = await get_user_info(request)

    # 根据 user_id 查询完整用户信息
    with pool.get_session() as session:
        user = session.query(TUser).filter(TUser.id == user_info["id"]).first()
        if not user:
            raise MyException(SysCodeEnum.c_401, detail="用户不存在")

        return {
            "id": user.id,
            "username": user.userName,
            "mobile": user.mobile,
            "createTime": user.createTime,
        }
```

### 6.3 受保护的接口示例

```python
@bp.post("/user/qa/record")
@async_json_resp
async def add_qa_record(request):
    """
    新增问答记录(需要登录)
    """
    # 验证用户身份
    user_info = await get_user_info(request)
    user_id = user_info["id"]

    # 业务逻辑
    data = request.json
    question = data.get("question")
    answer = data.get("answer")

    # 插入数据库
    sql = "INSERT INTO t_user_qa_record (user_id, question, to2_answer) VALUES (%s, %s, %s)"
    mysql_client.insert(sql, (user_id, question, answer))

    return {"message": "记录已保存"}
```

---

## 七、ORM 辅助工具:model_to_dict

### 7.1 为什么需要序列化工具

**问题:** SQLAlchemy 模型对象无法直接序列化为 JSON
```python
user = session.query(TUser).first()
return user  # 报错: Object of type 'TUser' is not JSON serializable
```

**解决方案:** 将模型对象转为字典

### 7.2 序列化工具实现

完整源码(`model/serializers.py`,共 56 行):

```python
import datetime
import json
from typing import Any, Dict, List, Union
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm.exc import DetachedInstanceError


def model_to_dict(
    model_instance: Union[DeclarativeBase, List[DeclarativeBase]],
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    将SQLAlchemy模型实例转换为字典
    :param model_instance: SQLAlchemy模型实例或实例列表
    :return: 字典或字典列表
    """
    # 处理列表情况
    if isinstance(model_instance, list):
        return [single_model_to_dict(item) for item in model_instance]

    # 处理单个实例情况
    return single_model_to_dict(model_instance)


def single_model_to_dict(model_instance: DeclarativeBase) -> Dict[str, Any]:
    """
    将单个SQLAlchemy模型实例转换为字典
    :param model_instance: SQLAlchemy模型实例
    :return: 字典表示
    """
    result = {}
    try:
        for column in model_instance.__table__.columns:
            try:
                value = getattr(model_instance, column.name)
                if isinstance(value, datetime.datetime):
                    value = value.isoformat() if value else None
                elif isinstance(value, datetime.date):
                    value = value.isoformat() if value else None
                result[column.name] = value
            except DetachedInstanceError:
                # 处理与session分离的实例
                result[column.name] = None
    except Exception as e:
        # 如果出现其他错误,返回空字典或部分数据
        pass
    return result


def model_to_json(model_instance: Union[DeclarativeBase, List[DeclarativeBase]]) -> str:
    """
    将SQLAlchemy模型实例转换为JSON字符串
    :param model_instance: SQLAlchemy模型实例或实例列表
    :return: JSON字符串
    """
    return json.dumps(model_to_dict(model_instance), ensure_ascii=False, default=str)
```

**使用示例:**
```python
from model.serializers import model_to_dict

# 单个对象
user = session.query(TUser).first()
user_dict = model_to_dict(user)
# {"id": 1, "userName": "admin", "createTime": "2024-01-01T10:00:00"}

# 对象列表
users = session.query(TUser).all()
users_list = model_to_dict(users)
# [{"id": 1, ...}, {"id": 2, ...}]
```

---

## 八、本章总结

### 8.1 核心要点回顾

1. **JWT 无状态认证**: 无需 Redis 存储 Session,服务器水平扩展友好
2. **自定义异常设计**: 通过枚举定义错误码,前端可根据 code 做差异化处理
3. **装饰器统一响应**: 减少 85% 重复代码,自动处理异常和日期序列化
4. **三层安全检查**: Token 格式验证 → 签名验证 → 过期时间验证
5. **ORM 序列化工具**: 自动将模型对象转为字典,处理日期类型

### 8.2 安全加固检查清单

- [ ] 密码使用 bcrypt 加密存储
- [ ] JWT 密钥设置为强随机字符串(至少 32 位)
- [ ] Token 过期时间不超过 24 小时
- [ ] 所有 SQL 查询使用参数化避免注入
- [ ] HTTPS 传输防止中间人攻击
- [ ] 日志中不记录敏感信息(密码、Token)

### 8.3 下一章预告

第一部分(基础架构篇)已完成,下一章我们将进入 **第二部分 LangChain/LangGraph 智能体基础**,学习如何构建 AI 问答系统的核心引擎。

---

**完整文件清单:**
- `common/exception.py` (42 行) - 自定义异常类
- `constants/code_enum.py` (58 行) - 错误码枚举
- `common/res_decorator.py` (97 行) - 统一响应装饰器
- `services/user_service.py` (359 行) - 用户认证服务
- `model/serializers.py` (56 行) - ORM 序列化工具
