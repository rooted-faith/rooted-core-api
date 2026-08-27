# Admin Sub Application

This is the Admin sub-application for Rooted Core API, mounted at `/admin` path.

## Structure

```
portal/apps/admin/
├── __init__.py          # Admin app factory function
├── routers/             # Admin API routers
│   └── __init__.py      # Router registration
└── serializers/         # Admin API serializers
```

## Usage

The admin sub-app is automatically mounted to the main application at `/admin` path.

### Example Routes

- Health check: `GET /admin/healthz`
- Admin API routes: `GET /admin/api/v1/...`

## Adding New Routes

1. Create a new router file in `portal/apps/admin/routers/`
2. Register it in `portal/apps/admin/routers/__init__.py`
3. The route will be available at `/admin/{your_prefix}/...`

## Container Access

The admin app shares the same container instance with the main app, so all handlers, providers, and services are available.
