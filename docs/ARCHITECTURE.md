# Rooted Core API - 项目架构文档

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 技术栈](#2-技术栈)
- [3. 架构设计](#3-架构设计)
- [4. 目录结构](#4-目录结构)
- [5. 核心组件](#5-核心组件)
- [6. 数据流](#6-数据流)
- [7. 依赖注入](#7-依赖注入)
- [8. 中间件](#8-中间件)
- [9. 路由结构](#9-路由结构)
- [10. Admin Sub Application](#10-admin-sub-application)
- [11. 开发指南](#11-开发指南)
- [12. 最佳实践](#12-最佳实践)

---

## 1. 项目概述

Rooted Core API 是一个基于 FastAPI 构建的现代化 RESTful API 服务，采用模块化架构设计，支持多应用挂载（Sub Application）模式。

### 核心特性

- **异步处理**: 全面采用 async/await 异步编程模式
- **依赖注入**: 使用 dependency-injector 实现依赖注入
- **模块化设计**: 支持主应用和子应用（Sub App）架构
- **请求上下文管理**: 基于 ContextVar 的请求级别上下文管理
- **分布式追踪**: 集成 Sentry 进行性能监控和错误追踪
- **类型安全**: 使用 Pydantic 进行数据验证和类型检查

---

## 2. 技术栈

### 核心框架

- **FastAPI 0.35.0**: 现代、快速的 Web 框架
- **Python 3.13+**: 编程语言
- **SQLAlchemy**: ORM 框架
- **asyncpg**: PostgreSQL 异步驱动
- **Redis**: 缓存和会话存储

### 依赖管理

- **uv**: 包管理和依赖管理工具

### 数据库

- **PostgreSQL**: 主数据库
- **Alembic**: 数据库迁移工具

### 认证与授权

- **JWT**: Token 管理
- **RBAC**: 基于角色的访问控制

### 监控与追踪

- **Sentry**: 错误追踪和性能监控
- **OpenTelemetry**: 分布式追踪

### 其他工具

- **Pydantic**: 数据验证
- **dependency-injector**: 依赖注入容器
- **fastapi-limiter**: 速率限制

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Main App                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Middleware Layer                     │  │
│  │  - CORS Middleware                                │  │
│  │  - CoreRequestMiddleware (DB Session)             │  │
│  │  - AuthMiddleware (Authentication)                │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────┐      ┌──────────────────────┐   │
│  │   Main API       │      │   Admin Sub App       │   │
│  │   /api/*         │      │   /admin/*            │   │
│  └──────────────────┘      └──────────────────────┘   │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │         Dependency Injection Container             │  │
│  │  - Handlers, Providers, Services                  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 3.2 设计模式

#### 依赖注入模式 (Dependency Injection)

使用 `dependency-injector` 实现依赖注入，所有服务、处理器和提供者都通过 Container 进行管理。

#### 请求上下文模式 (Request Context)

使用 Python 的 `ContextVar` 实现请求级别的上下文管理，包括：

- Request Context: HTTP 请求信息
- User Context: 用户信息
- Session Context: 数据库会话

#### 工厂模式 (Factory Pattern)

- `Container`: 服务工厂
- `create_admin_app()`: Admin 应用工厂

#### 中间件模式 (Middleware Pattern)

请求处理流程：

1. CORS Middleware (最外层)
2. CoreRequestMiddleware (数据库会话管理)
3. AuthMiddleware (认证和授权)

---

## 4. 目录结构

```
rooted-core-api/
├── portal/                          # 主应用包
│   ├── __init__.py                  # 包初始化
│   ├── __main__.py                  # CLI 入口点
│   ├── main.py                      # FastAPI 应用入口
│   ├── config.py                    # 配置管理
│   ├── container.py                 # 依赖注入容器
│   │
│   ├── apps/                        # 子应用模块
│   │   └── admin/                  # Admin 子应用
│   │       ├── __init__.py          # Admin app 工厂
│   │       ├── routers/             # Admin 路由
│   │       └── serializers/         # Admin 序列化器
│   │
│   ├── authorization/              # 授权相关
│   │   └── access_token.py         # Token 认证
│   │
│   ├── cli/                        # CLI 工具
│   │   └── main.py                # CLI 入口
│   │
│   ├── exceptions/                 # 异常处理
│   │   ├── responses/             # 异常响应
│   │   │   └── base.py           # 基础异常类
│   │   └── validation_errors.py   # 验证错误
│   │
│   ├── handlers/                  # 业务逻辑处理器
│   │   └── admin/                 # Admin 处理器
│   │
│   ├── libs/                      # 共享库
│   │   ├── consts/                # 常量定义
│   │   ├── contexts/              # 上下文管理
│   │   │   ├── request_context.py
│   │   │   ├── user_context.py
│   │   │   ├── request_session_context.py
│   │   │   └── api_context.py
│   │   ├── database/              # 数据库相关
│   │   │   ├── aio_orm.py         # 异步 ORM Session
│   │   │   ├── aio_pg.py          # PostgreSQL 连接
│   │   │   ├── aio_redis.py       # Redis 连接
│   │   │   ├── orm.py             # ORM 基础类
│   │   │   └── session_proxy.py   # Session 代理
│   │   ├── decorators/            # 装饰器
│   │   │   └── sentry_tracer.py   # Sentry 追踪装饰器
│   │   ├── logger/                # 日志系统
│   │   │   ├── logger.py
│   │   │   ├── generator.py
│   │   │   └── const.py
│   │   ├── shared/                # 共享工具
│   │   │   ├── converter.py       # 类型转换
│   │   │   ├── asserts.py         # 断言工具
│   │   │   └── validator.py       # 验证器
│   │   └── utils/                 # 工具函数
│   │       └── lifespan.py        # 应用生命周期
│   │
│   ├── middlewares/                # 中间件
│   │   ├── core_request.py        # 核心请求中间件
│   │   └── auth_middleware.py     # 认证中间件
│   │
│   ├── models/                    # 数据库模型
│   │   └── mixins/                # 模型混入
│   │
│   ├── providers/                 # 服务提供者
│   │   ├── jwt_provider.py       # JWT 提供者
│   │   └── password_provider.py  # 密码提供者
│   │
│   ├── routers/                   # 路由
│   │   ├── api_root.py           # API 根路由
│   │   └── apis/                 # API 路由
│   │       └── v1/               # v1 API
│   │
│   ├── schemas/                   # 共享 Schema
│   │   ├── base.py
│   │   ├── auth.py
│   │   └── rate_limiter.py
│   │
│   └── serializers/               # 序列化器
│       ├── v1/                   # v1 序列化器
│       ├── mixins/               # 序列化器混入
│       └── response_examples/    # 响应示例
│
├── alembic/                       # 数据库迁移
│   ├── versions/                  # 迁移版本
│   └── env.py                     # Alembic 环境配置
│
├── tests/                         # 测试套件
│   ├── fixtures/                  # 测试夹具
│   └── handlers/                 # 处理器测试
│
├── docs/                          # 文档
│   └── ARCHITECTURE.md           # 本文档
│
├── pyproject.toml                 # uv 配置
├── alembic.ini                    # Alembic 配置
├── example.env                    # 环境变量示例
└── README.md                      # 项目说明
```

---

## 5. 核心组件

### 5.1 应用入口 (`portal/main.py`)

主应用入口，负责：

- 初始化 FastAPI 应用
- 配置中间件
- 注册路由
- 挂载子应用
- 设置异常处理
- 配置 OpenAPI 文档

**关键函数**:

- `get_application()`: 创建并配置 FastAPI 应用
- `mount_admin_app()`: 挂载 Admin 子应用
- `register_middleware()`: 注册中间件
- `register_router()`: 注册路由

### 5.2 配置管理 (`portal/config.py`)

使用 Pydantic Settings 进行配置管理，支持：

- 环境变量读取
- 类型验证
- 默认值设置
- 动态配置加载（Google Cloud 凭证、Rate Limiter 配置等）

**配置类别**:

- 应用基础配置
- 数据库配置
- Redis 配置
- JWT 配置
- Google Cloud 配置
- AWS S3 配置
- CORS 配置

### 5.3 依赖注入容器 (`portal/container.py`)

使用 `dependency-injector` 管理所有依赖：

```python
class Container(containers.DeclarativeContainer):
    # 配置
    config = providers.Configuration()
    
    # 数据库
    postgres_connection = providers.Singleton(PostgresConnection)
    db_session = providers.Factory(Session)
    request_session = providers.Factory(SessionProxy)
    
    # Redis
    redis_client = providers.Singleton(RedisPool)
    
    # Handlers, Providers 等
    # ...
```

### 5.4 数据库层

#### ORM 基础类 (`portal/libs/database/orm.py`)

- `Base`: SQLAlchemy DeclarativeBase，配置命名约定
- `ModelBase`: 基础模型类，包含 `id` 字段

#### 异步 Session (`portal/libs/database/aio_orm.py`)

提供异步数据库操作接口：

- `Session`: 异步数据库会话
- `_Select`, `_Insert`, `_Update`, `_Delete`: 查询构建器

#### Session 代理 (`portal/libs/database/session_proxy.py`)

`SessionProxy`: 请求级别的 Session 代理，从 ContextVar 解析实际的 Session。

### 5.5 上下文管理

#### Request Context (`portal/libs/contexts/request_context.py`)

存储每个请求的 HTTP 信息：

- IP 地址
- User Agent
- 请求方法、URL、路径
- 请求 ID

#### User Context (`portal/libs/contexts/user_context.py`)

存储当前请求的用户信息：

- 用户 ID
- 认证信息
- 权限信息

#### Session Context (`portal/libs/contexts/request_session_context.py`)

管理请求级别的数据库会话。

### 5.6 中间件

#### CoreRequestMiddleware (`portal/middlewares/core_request.py`)

核心请求中间件，负责：

1. 创建数据库会话
2. 设置请求上下文
3. 自动提交/回滚事务
4. 清理资源

#### AuthMiddleware (`portal/middlewares/auth_middleware.py`)

认证和授权中间件，负责：

1. Token 验证
2. 用户身份识别
3. 权限检查
4. 设置用户上下文

### 5.7 异常处理

#### 异常类层次结构

```
ApiBaseException (HTTPException)
├── BadRequestException (400)
│   └── ParamError
├── NotFoundException (404)
├── ConflictErrorException (409)
├── EntityTooLargeException (413)
└── NotImplementedException (501)
```

### 5.8 日志系统

#### Logger (`portal/libs/logger/`)

- 基于 Python `logging` 模块
- 支持环境级别配置
- 分离错误和普通日志输出

### 5.9 追踪系统

#### Sentry Tracer (`portal/libs/decorators/sentry_tracer.py`)

提供装饰器：

- `@distributed_trace()`: 分布式追踪装饰器
- `@start_transaction()`: 事务追踪装饰器

---

## 6. 数据流

### 6.1 请求处理流程

```
1. HTTP Request
   ↓
2. CORS Middleware (处理跨域)
   ↓
3. CoreRequestMiddleware
   ├── 创建数据库会话
   ├── 设置请求上下文
   └── 设置会话上下文
   ↓
4. AuthMiddleware
   ├── 验证 Token
   ├── 检查权限
   └── 设置用户上下文
   ↓
5. Router Handler
   ├── 从 Container 获取 Handler
   ├── 执行业务逻辑
   └── 返回响应
   ↓
6. CoreRequestMiddleware (清理)
   ├── 提交/回滚事务
   ├── 关闭数据库会话
   └── 清理上下文
   ↓
7. HTTP Response
```

### 6.2 数据库操作流程

```
1. Handler 接收请求
   ↓
2. 从 Container 获取 SessionProxy
   ↓
3. SessionProxy 从 ContextVar 解析实际 Session
   ↓
4. 执行数据库操作
   ├── Select/Insert/Update/Delete
   └── 自动事务管理
   ↓
5. 中间件自动提交/回滚
```

---

## 7. 依赖注入

### 7.1 Container 配置

Container 使用 `dependency-injector` 的 `DeclarativeContainer`：

```python
class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        packages=[
            "portal.authorization",
            "portal.handlers",
            "portal.routers",
            "portal.middlewares",
        ],
    )
```

### 7.2 Provider 类型

- **Singleton**: 单例提供者（如 Redis、PostgreSQL 连接）
- **Factory**: 工厂提供者（每次调用创建新实例，如 Session、Handler）

### 7.3 使用示例

```python
# 在 Handler 中使用
from dependency_injector.wiring import inject, Provide

class UserHandler:
    @inject
    def __init__(
        self,
        session: Session = Provide[Container.request_session],
        redis_client: RedisPool = Provide[Container.redis_client],
    ):
        self.session = session
        self.redis_client = redis_client
```

---

## 8. 中间件

### 8.1 中间件执行顺序

中间件的执行顺序是**反向**的（后进先出）：

```
注册顺序: CORS → CoreRequest → Auth
执行顺序: Auth → CoreRequest → CORS
```

### 8.2 CoreRequestMiddleware

**职责**:

- 创建和管理数据库会话
- 设置请求上下文
- 自动事务管理（提交/回滚）
- 资源清理

**关键代码**:

```python
db_session = container.db_session()
session_ctx_token = set_request_session(db_session)
try:
    # 设置请求上下文
    response = await call_next(request)
except Exception as e:
    await db_session.rollback()
    raise e
else:
    await db_session.commit()
finally:
    await db_session.close()
    reset_request_session(session_ctx_token)
```

### 8.3 AuthMiddleware

**职责**:

- Token 验证
- 用户身份识别
- 权限检查
- 设置用户上下文

---

## 9. 路由结构

### 9.1 主应用路由

```
/api
  └── /v1
      ├── /healthz
      └── ... (其他 API 路由)
```

### 9.2 Admin 子应用路由

```
/admin
  ├── /healthz
  └── /api/v1
      └── ... (Admin API 路由)
```

### 9.3 路由注册

主应用路由在 `portal/routers/api_root.py` 中注册：

```python
router = APIRouter()
router.include_router(api_v1_router, prefix="/v1")
```

Admin 路由在 `portal/apps/admin/routers/__init__.py` 中注册。

---

## 10. Admin Sub Application

### 10.1 设计目的

Admin Sub Application 是一个独立的 FastAPI 应用，通过 `mount` 方式挂载到主应用，实现：

- 模块化架构
- 独立的路由管理
- 共享 Container 和中间件
- 独立的文档和配置

### 10.2 创建和挂载

**创建** (`portal/apps/admin/__init__.py`):

```python
def create_admin_app(container: Container) -> FastAPI:
    admin_app = FastAPI(
        title="Rooted Core Admin API",
        lifespan=lifespan,
    )
    admin_app.container = container
    register_routers(admin_app)
    return admin_app
```

**挂载** (`portal/main.py`):

```python
def mount_admin_app(application: FastAPI, container: Container):
    admin_app = create_admin_app(container=container)
    application.mount("/admin", admin_app)
```

### 10.3 特性

- **共享 Container**: Admin app 使用主应用的 Container 实例
- **共享中间件**: 主应用的中间件自动应用到 Admin app
- **独立路由**: Admin 路由在 `/admin` 路径下
- **独立文档**: 可以配置独立的 OpenAPI 文档

### 10.4 添加路由

在 `portal/apps/admin/routers/__init__.py` 中：

```python
def register_routers(app: FastAPI) -> None:
    from .auth import router as auth_router
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["Admin - Authentication"])
```

---

## 11. 开发指南

### 11.1 添加新的 Handler

1. 在 `portal/handlers/` 创建 Handler 类
2. 在 `portal/container.py` 注册 Provider
3. 在 Router 中使用 Handler

**示例**:

```python
# portal/handlers/user.py
class UserHandler:
    def __init__(self, session: Session):
        self.session = session
    
    async def get_user(self, user_id: UUID):
        # 业务逻辑
        pass

# portal/container.py
user_handler = providers.Factory(
    handlers.UserHandler,
    session=request_session,
)
```

### 11.2 添加新的路由

1. 在 `portal/routers/apis/v1/` 创建路由文件
2. 在 `portal/routers/apis/v1/__init__.py` 注册路由
3. 创建对应的 Serializer

**示例**:

```python
# portal/routers/apis/v1/user.py
from fastapi import APIRouter
from dependency_injector.wiring import inject, Provide
from portal.container import Container

router = APIRouter(tags=["User"])

@router.get("/users/{user_id}")
@inject
async def get_user(
    user_id: UUID,
    handler: UserHandler = Provide[Container.user_handler],
):
    return await handler.get_user(user_id)
```

### 11.3 添加新的 Model

1. 在 `portal/models/` 创建 Model 类
2. 继承 `ModelBase`
3. 使用 Alembic 创建迁移

**示例**:

```python
# portal/models/user.py
from portal.libs.database.orm import ModelBase
from sqlalchemy import Column, String

class User(ModelBase):
    __tablename__ = "user"
    
    username = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
```

### 11.4 添加新的 Provider

1. 在 `portal/providers/` 创建 Provider 类
2. 在 `portal/container.py` 注册 Provider

**示例**:

```python
# portal/providers/jwt_provider.py
class JWTProvider:
    def create_token(self, payload: dict) -> str:
        # JWT 创建逻辑
        pass

# portal/container.py
jwt_provider = providers.Singleton(JWTProvider)
```

### 11.5 数据库迁移

```bash
# 创建迁移
uv run alembic revision --autogenerate -m "description"

# 执行迁移
uv run alembic upgrade head

# 回滚迁移
uv run alembic downgrade -1
```

---

## 12. 最佳实践

### 12.1 代码组织

- **Handlers**: 只包含业务逻辑，不直接操作数据库
- **Models**: 只定义数据结构，不包含业务逻辑
- **Providers**: 封装外部服务调用
- **Serializers**: 定义 API 输入输出格式

### 12.2 错误处理

- 使用项目定义的异常类
- 在 Handler 中抛出异常，由全局异常处理器处理
- 提供有意义的错误消息

### 12.3 日志记录

- 使用 `@distributed_trace` 装饰器进行追踪
- 记录关键操作和错误
- 避免记录敏感信息

### 12.4 性能优化

- 使用异步操作
- 合理使用数据库连接池
- 使用 Redis 缓存
- 避免 N+1 查询问题

### 12.5 安全性

- 所有敏感操作都需要认证
- 使用权限检查中间件
- 验证所有输入数据
- 使用参数化查询防止 SQL 注入

### 12.6 测试

- 为每个 Handler 编写测试
- 使用 pytest 和 pytest-asyncio
- 使用 fixtures 管理测试数据
- 测试覆盖关键业务逻辑

---

## 附录

### A. 环境变量配置

参考 `example.env` 文件，主要配置项包括：

- **应用配置**: `ENV`, `APP_NAME`, `VERSION`
- **数据库配置**: `DATABASE_HOST`, `DATABASE_USER`, `DATABASE_PASSWORD`
- **Redis 配置**: `REDIS_URL`
- **JWT 配置**: `JWT_SECRET_KEY`
- **Google Cloud 配置**: `GOOGLE_APPLICATION_CREDENTIALS`
- **AWS 配置**: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

### B. 常用命令

```bash
# 安装依赖
uv sync

# 运行应用
uv run uvicorn portal:app --reload

# 运行测试
uv run pytest

# 数据库迁移
uv run alembic upgrade head

# 代码格式化（如果配置了）
uv run black .
```

### C. 相关文档

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)
- [dependency-injector 文档](https://python-dependency-injector.ets-labs.org/)
- [Alembic 文档](https://alembic.sqlalchemy.org/)

---

**文档版本**: 1.0.0  
**最后更新**: 2025-01-XX  
**维护者**: Rooted Core Team
