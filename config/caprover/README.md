# CapRover Environment Configuration Templates

This folder contains environment variable templates for deploying to CapRover.

## Files

| File | CapRover App | Project |
|------|--------------|---------|
| `.env.caprover.prod.backend` | `acme-supervisor-backend` | `acme-supervisor` |
| `.env.caprover.prod.worker` | `acme-supervisor-worker` | `acme-supervisor` |
| `.env.caprover.prod.beat` | `acme-supervisor-beat` | `acme-supervisor` |
| `.env.caprover.uat.backend` | `acme-supervisor-uat-backend` | `acme-supervisor-uat` |
| `.env.caprover.uat.worker` | `acme-supervisor-uat-worker` | `acme-supervisor-uat` |
| `.env.caprover.uat.beat` | `acme-supervisor-uat-beat` | `acme-supervisor-uat` |

## How to Use

### 1. Create CapRover Projects

In CapRover Dashboard → Projects:
- Create `acme-supervisor` (Production)
- Create `acme-supervisor-uat` (UAT)

### 2. Create Apps in Each Project

**Production Project (`acme-supervisor`):**
```
acme-supervisor-mongodb     (One-Click MongoDB)
acme-supervisor-redis       (One-Click Redis)
acme-supervisor-backend     (App, Port 3000)
acme-supervisor-worker      (App, No HTTP)
acme-supervisor-beat        (App, No HTTP)
```

**UAT Project (`acme-supervisor-uat`):**
```
acme-supervisor-uat-mongodb     (One-Click MongoDB)
acme-supervisor-uat-redis       (One-Click Redis)
acme-supervisor-uat-minio       (One-Click MinIO)
acme-supervisor-uat-backend     (App, Port 3000)
acme-supervisor-uat-worker      (App, No HTTP)
acme-supervisor-uat-beat        (App, No HTTP)
```

### 3. Configure Environment Variables

1. Open CapRover Dashboard
2. Go to the app (e.g., `acme-supervisor-backend`)
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
- MongoDB: `srv-captain--acme-supervisor-mongodb:27017`
- Redis: `srv-captain--acme-supervisor-redis:6379`

**UAT:**
- MongoDB: `srv-captain--acme-supervisor-uat-mongodb:27017`
- Redis: `srv-captain--acme-supervisor-uat-redis:6379`
- MinIO: `srv-captain--acme-supervisor-uat-minio:9000`

## Storage Configuration

| Environment | Storage | Endpoint |
|-------------|---------|----------|
| Production | Hetzner S3 | `https://fsn1.your-objectstorage.com` (external) |
| UAT | MinIO | `http://srv-captain--acme-supervisor-uat-minio:9000` (internal) |

## Important Notes

1. **JWT_SECRET_KEY must match** across backend, worker, and beat in the same environment
2. **ENABLE_BOOTSTRAP_ADMIN** should be `false` in production after initial setup
3. **MinIO credentials** for UAT default to `minioadmin/minioadmin` - change for security
4. Worker and Beat apps don't need HTTP port - disable in CapRover app settings
