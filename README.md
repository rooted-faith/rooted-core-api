# Rooted Core API

A modern RESTful API service for the Rooted（扎根） devotional app backend, built with FastAPI and Clean Architecture.

## 🛠️ Tech Stack

- **Backend Framework**: FastAPI
- **Database**: PostgreSQL (using SQLAlchemy + asyncpg)
- **Cache**: Redis
- **Authentication**: JWT
- **Authorization**: RBAC (Role-Based Access Control)
- **File Storage**: AWS S3
- **Monitoring**: Sentry
- **Containerization**: Docker
- **Package Manager**: uv
- **Database Migration**: Alembic
- **Python Version**: 3.14+

## 📋 Prerequisites

- Python 3.14+
- PostgreSQL 12+
- Redis 6+
- Docker (optional)
- AWS S3 bucket (for file storage)

## 🚀 Quick Start

### 1. Install uv

[uv Installation Guide](https://docs.astral.sh/uv/getting-started/installation/)

### 2. Install Dependencies

```bash
uv sync
```

### 3. Environment Setup

Create a `.env` file in the project root:

```bash
cp example.env .env
```

Edit the `.env` file with your configuration values.

### 4. Database Setup

#### Run Database Migrations

```bash
# Create a new migration file
uv run alembic revision --autogenerate -m "description"

# Run migrations
uv run alembic upgrade head
```

#### Seed Bootstrap Data

```bash
# One-shot: seed locale, identity provider, legal document, system setting, and
# RBAC data, then interactively prompt for and create a superuser
uv run rooted-cli init-all
```

### 5. Run the Application

#### Development Environment

```bash
uv run uvicorn portal:app --reload --host 0.0.0.0 --port 8000
```

The application runs on `http://localhost:8000` by default.

## 📚 API Documentation

Once the application is running, you can access:

- **Interactive API Docs**: <http://localhost:8000/docs>
- **ReDoc Documentation**: <http://localhost:8000/redoc>
- **Health Check**: <http://localhost:8000/api/healthz>

## 📁 Project Structure

```
rooted-core-api/
├── portal/                    # Main application
│   ├── __init__.py
│   ├── __main__.py
│   ├── main.py               # FastAPI application entry point
│   ├── config.py             # Configuration
│   ├── container.py          # Dependency injection container
│   ├── authorization/       # Authentication related
│   ├── cli/                  # CLI tools
│   ├── exceptions/           # Exception handling
│   ├── handlers/            # Business logic handlers
│   ├── libs/                # Shared libraries
│   ├── middlewares/         # Middlewares
│   ├── models/              # Database models
│   ├── providers/           # Service providers
│   ├── routers/            # API routers
│   ├── schemas/            # Shared schemas
│   └── serializers/       # Serializers (request/response models)
├── alembic/                # Database migrations
├── tests/                  # Test suite
├── Dockerfile             # Docker configuration
├── pyproject.toml         # Project configuration (uv)
├── alembic.ini            # Alembic configuration
└── README.md              # This file
```

## 📝 Development Guidelines

### Database Migrations

- Use Alembic for database migrations
- **Do not** manually modify files in the `alembic/` directory
- When creating constraints, you don't need to provide a name. The project's naming convention is already configured in `libs/database/orm`

### API Routers

- BaseModels definitions should be placed in the `serializers/` directory, aligned with the router version
- All API router prefixes should be set only at the `__init__.py` level

### Testing

- Use pytest for testing
- Use `pytest.mark.asyncio` decorator for async tests
- Test files should be placed in the `tests/` directory

### Tracing

- Use OpenTelemetry for tracing
- Every function in handlers and providers should use the `@distributed_trace` decorator

