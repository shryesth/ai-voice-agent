# Deployment Guide

## CapRover CLI Deployment to UAT

### Prerequisites

1. **Install CapRover CLI**:
   ```bash
   npm install -g caprover
   ```

2. **Login to CapRover**:
   ```bash
   caprover login
   ```
   - URL: `https://captain.ss-apps.acme.org`
   - Password: Your CapRover admin password
   - Machine name: `captain-ss`

3. **Verify Login**:
   ```bash
   caprover list
   ```

### Deploy to UAT

#### Option 1: Automated Deployment Script (Recommended)

Deploy all services (backend, worker, beat) at once:

```bash
./deploy-uat.sh
```

This will:
- Deploy backend to `acme-supervisor-uat-backend`
- Deploy worker to `acme-supervisor-uat-worker`
- Deploy beat to `acme-supervisor-uat-beat`

#### Option 2: Manual Deployment

Deploy each service individually from the project root:

**Backend:**
```bash
# Create captain-definition for backend
cat > captain-definition <<EOF
{
  "schemaVersion": 2,
  "dockerfilePath": "./docker/Dockerfile.api"
}
EOF

caprover deploy --caproverName captain-ss --caproverApp acme-supervisor-uat-backend
```

**Worker:**
```bash
# Update captain-definition for worker
cat > captain-definition <<EOF
{
  "schemaVersion": 2,
  "dockerfilePath": "./docker/Dockerfile.worker"
}
EOF

caprover deploy --caproverName captain-ss --caproverApp acme-supervisor-uat-worker
```

**Beat:**
```bash
# Update captain-definition for beat
cat > captain-definition <<EOF
{
  "schemaVersion": 2,
  "dockerfilePath": "./docker/Dockerfile.beat"
}
EOF

caprover deploy --caproverName captain-ss --caproverApp acme-supervisor-uat-beat
```

### Verify Deployment

Check the health endpoint:
```bash
curl https://acme-supervisor-uat-backend.ss-apps.acme.org/api/v1/health/live
```

Expected response:
```json
{"status": "healthy"}
```

### View Logs

Via CapRover CLI:
```bash
caprover logs --caproverName captain-ss --caproverApp acme-supervisor-uat-backend
caprover logs --caproverName captain-ss --caproverApp acme-supervisor-uat-worker
caprover logs --caproverName captain-ss --caproverApp acme-supervisor-uat-beat
```

Or via CapRover Dashboard:
- Navigate to: https://captain.ss-apps.acme.org
- Go to Apps → Select app → View Logs

## GitLab CI/CD Deployment

The project uses GitLab CI/CD for automated deployments:

### UAT Deployment
- **Trigger**: Push to `develop` or `feature/*` branches
- **Process**: Builds Docker images → Pushes to GitLab Registry → Deploys to CapRover
- **Manual approval**: Required in GitLab pipeline

### Production Deployment
- **Trigger**: Push to `main` branch
- **Process**: Same as UAT, deploys to production CapRover apps
- **Manual approval**: Required in GitLab pipeline

## Environment Configuration

Environment variables are configured in CapRover dashboard:

1. Go to: https://captain.ss-apps.acme.org
2. Select the app (e.g., `acme-supervisor-uat-backend`)
3. Click **App Configs** tab
4. Scroll to **Environment Variables** → **Bulk Edit**
5. Use templates from `config/caprover/*.env.caprover.uat.*`

### Key Environment Variables

See templates in `config/caprover/` for complete list:
- `.env.caprover.uat.backend` - Backend API configuration
- `.env.caprover.uat.worker` - Celery worker configuration
- `.env.caprover.uat.beat` - Celery beat scheduler configuration

## Infrastructure Services

The following services must be running before deploying apps:

| Service | App Name | Notes |
|---------|----------|-------|
| MongoDB | `acme-supervisor-uat-mongodb` | One-Click App |
| Redis | `acme-supervisor-uat-redis` | One-Click App |
| MinIO | `acme-supervisor-uat-minio` | One-Click App |

## Rollback

### Via GitLab CI/CD
Run the `rollback:uat` job from the GitLab pipeline.

### Via CLI
Deploy a previous commit or the `:develop` tagged image:

```bash
caprover deploy \
  --caproverName captain-ss \
  --caproverApp acme-supervisor-uat-backend \
  --imageName registry.gitlab.com/your-project/api:develop
```

## Troubleshooting

### Build Fails
- Check Dockerfile paths are correct
- Ensure `requirements.txt` is up to date
- Review build logs in CapRover dashboard

### Health Check Fails
- Verify environment variables are set correctly
- Check MongoDB/Redis connections
- Review app logs for startup errors

### Deployment Timeout
- Increase build timeout in CapRover app settings
- Check internet connectivity for pulling base images

## Architecture

```
┌─────────────────────────────────────────┐
│         CapRover Infrastructure         │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────┐  ┌──────────────┐    │
│  │   MongoDB    │  │    Redis     │    │
│  │   (UAT)      │  │    (UAT)     │    │
│  └──────────────┘  └──────────────┘    │
│         │                 │             │
│         │                 │             │
│  ┌──────┴─────────────────┴──────┐     │
│  │                                │     │
│  │  Backend (Port 3000)           │     │
│  │  Worker (No HTTP)              │     │
│  │  Beat (No HTTP)                │     │
│  │                                │     │
│  └────────────────────────────────┘     │
│                                         │
└─────────────────────────────────────────┘
```
