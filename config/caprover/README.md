# CapRover Environment Configuration Templates

This folder contains environment variable templates for deploying to CapRover.

## Files

| File | CapRover App | Project |
|------|--------------|---------|
| `.env.caprover.prod.backend` | `shifo-supervisor-backend` | `shifo-supervisor` |
| `.env.caprover.prod.worker` | `shifo-supervisor-worker` | `shifo-supervisor` |
| `.env.caprover.prod.beat` | `shifo-supervisor-beat` | `shifo-supervisor` |
| `.env.caprover.uat.backend` | `shifo-supervisor-uat-backend` | `shifo-supervisor-uat` |
| `.env.caprover.uat.worker` | `shifo-supervisor-uat-worker` | `shifo-supervisor-uat` |
| `.env.caprover.uat.beat` | `shifo-supervisor-uat-beat` | `shifo-supervisor-uat` |

## How to Use

### 1. Create CapRover Projects

In CapRover Dashboard → Projects:
- Create `shifo-supervisor` (Production)
- Create `shifo-supervisor-uat` (UAT)

### 2. Create Apps in Each Project

**Production Project (`shifo-supervisor`):**
```
shifo-supervisor-mongodb     (One-Click MongoDB)
shifo-supervisor-redis       (One-Click Redis)
shifo-supervisor-backend     (App, Port 3000)
shifo-supervisor-worker      (App, No HTTP)
shifo-supervisor-beat        (App, No HTTP)
```

**UAT Project (`shifo-supervisor-uat`):**
```
shifo-supervisor-uat-mongodb     (One-Click MongoDB)
shifo-supervisor-uat-redis       (One-Click Redis)
shifo-supervisor-uat-minio       (One-Click MinIO)
shifo-supervisor-uat-backend     (App, Port 3000)
shifo-supervisor-uat-worker      (App, No HTTP)
shifo-supervisor-uat-beat        (App, No HTTP)
```

### 3. Configure Environment Variables

1. Open CapRover Dashboard
2. Go to the app (e.g., `shifo-supervisor-backend`)
3. Click **App Configs** tab
4. Scroll to **Environment Variables**
5. Click **Bulk Edit**
6. Copy-paste the contents from the corresponding `.env.caprover.*` file
7. Replace all `REPLACE_WITH_*` placeholders with actual values
8. Click **Save & Update**

### 4. Placeholders to Replace

| Placeholder | Description |
|-------------|-------------|
| `REPLACE_WITH_YOUR_DOMAIN` | Your CapRover domain (e.g., `apps.example.com`) |
| `REPLACE_WITH_PROD_TWILIO_*` | Production Twilio credentials |
| `REPLACE_WITH_UAT_TWILIO_*` | UAT Twilio credentials |
| `REPLACE_WITH_PROD_OPENAI_API_KEY` | Production OpenAI API key |
| `REPLACE_WITH_UAT_OPENAI_API_KEY` | UAT OpenAI API key |
| `REPLACE_WITH_PROD_JWT_SECRET_KEY` | Production JWT secret (generate new) |
| `REPLACE_WITH_UAT_JWT_SECRET_KEY` | UAT JWT secret (generate new) |
| `REPLACE_WITH_HETZNER_*` | Hetzner S3 storage credentials |
| `REPLACE_WITH_STRONG_PASSWORD` | Strong password for admin bootstrap |

### 5. Generate JWT Secret

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Internal Service Names

CapRover uses internal Docker networking. Services are accessible via:

```
srv-captain--{app-name}
```

**Production:**
- MongoDB: `srv-captain--shifo-supervisor-mongodb:27017`
- Redis: `srv-captain--shifo-supervisor-redis:6379`

**UAT:**
- MongoDB: `srv-captain--shifo-supervisor-uat-mongodb:27017`
- Redis: `srv-captain--shifo-supervisor-uat-redis:6379`
- MinIO: `srv-captain--shifo-supervisor-uat-minio:9000`

## Storage Configuration

| Environment | Storage | Endpoint |
|-------------|---------|----------|
| Production | Hetzner S3 | `https://fsn1.your-objectstorage.com` (external) |
| UAT | MinIO | `http://srv-captain--shifo-supervisor-uat-minio:9000` (internal) |

## Important Notes

1. **JWT_SECRET_KEY must match** across backend, worker, and beat in the same environment
2. **ENABLE_BOOTSTRAP_ADMIN** should be `false` in production after initial setup
3. **MinIO credentials** for UAT default to `minioadmin/minioadmin` - change for security
4. Worker and Beat apps don't need HTTP port - disable in CapRover app settings
