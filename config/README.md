# Environment Configuration Guide

This directory contains environment-specific configuration files for the Patient Feedback Collection API. The configuration system supports multiple deployment environments (local, UAT, production) with environment-specific overrides.

## How Configuration Loading Works

The application automatically loads the correct configuration file based on the `ENVIRONMENT` variable:

**Automatic Detection** (`backend/app/core/config.py`):
1. Checks `ENVIRONMENT` variable (defaults to "development")
2. Maps to config file:
   - `ENVIRONMENT=development` → loads `config/.env.local`
   - `ENVIRONMENT=staging` → loads `config/.env.uat`
   - `ENVIRONMENT=production` → loads `config/.env.prod`
3. Falls back to root `.env` if environment file not found
4. Uses Field defaults if no config file exists

**This works both:**
- **In Docker**: docker-compose sets `ENVIRONMENT` and provides `env_file`
- **Locally**: Set `ENVIRONMENT` variable or rely on default (development)

## Configuration Files

### Tracked in Git (Templates)
- **`.env.base`** - Base configuration with all variables and development defaults
- **`.env.local.example`** - Local development template with placeholders
- **`.env.uat.example`** - UAT/staging environment template with placeholders
- **`.env.prod.example`** - Production environment template with placeholders

### Not Tracked in Git (Actual Configurations)
- **`.env.local`** - Local development configuration (gitignored)
- **`.env.uat`** - UAT/staging configuration with real credentials (gitignored)
- **`.env.prod`** - Production configuration with real credentials (gitignored)

## Quick Start

### Local Development

```bash
# 1. Create your local environment file from template
cp config/.env.local.example config/.env.local

# 2. Edit config/.env.local and replace placeholders:
#    - TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
#    - OPENAI_API_KEY
#    - PUBLIC_URL (use ngrok URL - see step 3)

# 3. Start ngrok (in a separate terminal)
ngrok http 3000
# Copy the ngrok URL (e.g., https://abc123.ngrok.io)
# Update PUBLIC_URL in config/.env.local

# 4. Start services
docker compose -f docker-compose.dev.yml up
```

### UAT/Staging Deployment

```bash
# 1. Copy the UAT template
cp config/.env.uat.example config/.env.uat

# 2. Edit config/.env.uat and replace all REPLACE_WITH_* placeholders
# - Database credentials
# - Twilio credentials
# - OpenAI API key
# - Storage credentials (MinIO or Hetzner)
# - JWT secret key

# 3. Deploy using UAT docker-compose
docker compose -f docker-compose.uat.yml up -d

# 4. Verify deployment
curl https://api-uat.your-domain.com/api/v1/health/ready
```

### Production Deployment (Docker Compose)

```bash
# 1. Copy the production template
cp config/.env.prod.example config/.env.prod

# 2. Edit config/.env.prod and replace all REPLACE_WITH_* placeholders
# ⚠️  IMPORTANT: Use strong, unique credentials for production
# - Generate JWT secret: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# - Use production Twilio credentials
# - Use production OpenAI API key
# - Use Hetzner Object Storage credentials

# 3. Deploy using production docker-compose
docker compose -f docker-compose.production.yml up -d

# 4. Verify deployment
curl https://api.your-domain.com/api/v1/health/ready
```

### Production Deployment (CapRover)

CapRover uses an inline Dockerfile and doesn't support docker-compose or mounted config files. Environment variables must be set via the CapRover UI.

```bash
# 1. Open CapRover dashboard
# Navigate to: Apps → your-app-name → App Configs → Environment Variables

# 2. Use config/.env.prod.example as a reference
# Copy each variable and its value, replacing REPLACE_WITH_* placeholders

# 3. Set environment variables in CapRover UI:
# - Click "Bulk Edit"
# - Paste variables in KEY=value format
# - Click "Save & Update"

# 4. Deploy your code
git push caprover main

# 5. Verify deployment
curl https://your-app.caprover-domain.com/api/v1/health/ready
```

## Configuration Architecture

### Storage Configuration by Environment

| Environment | Storage Backend | Endpoint | Bucket | Access |
|-------------|----------------|----------|--------|--------|
| **Local** | MinIO (Docker) | `http://minio:9000` (in container) or `http://localhost:9000` (from host) | `voice-recordings` | minioadmin/minioadmin |
| **UAT** | MinIO (Docker, default) or Hetzner | `http://minio:9000` (Docker) or `https://nbg1.your-objectstorage.com` (Hetzner) | `voice-recordings-uat` or `acme-supervisor-uat` | minioadmin/minioadmin (Docker) or Hetzner credentials |
| **Production** | Hetzner Object Storage (external) | `https://nbg1.your-objectstorage.com` | `acme-supervisor` | Hetzner credentials |

**MinIO Setup (Local & UAT with docker-compose):**
- MinIO Console (Web UI) accessible at `http://localhost:9001`
- Buckets must be created manually on first setup (see "Access MinIO Console" in CLAUDE.md)
- Dev bucket: `voice-recordings`, UAT bucket: `voice-recordings-uat`

**Note:** S3_REGION must match your storage provider:
- **Local MinIO**: Use `us-east-1` (default, region doesn't matter for local MinIO)
- **Hetzner nbg1**: Use `eu-central-1` (Nuremberg, Germany)
- **AWS S3**: Use your bucket's actual region (e.g., `us-east-1`, `eu-west-1`, etc.)

### Environment-Specific Settings

#### CORS Configuration by Environment

| Environment | CORS Policy | Origins Allowed | Security Level |
|-------------|-------------|----------------|----------------|
| **Local (development)** | Relaxed | All origins (`*`) | Low (dev only) |
| **UAT (staging)** | Relaxed | All origins (`*`) | Low (internal testing) |
| **Production** | Strict | Only configured origins via `CORS_ORIGINS` | High (public-facing) |

**Why relaxed CORS for dev/UAT?**
- Easier frontend development and testing
- Multiple frontend URLs (localhost:3000, ngrok, preview deployments)
- No security risk (dev/UAT not exposed to public)

**Production CORS**: Set `CORS_ORIGINS` to comma-separated list of allowed frontend URLs:
```bash
CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

#### Local Development
- **Log Level**: `debug` (text format)
- **MongoDB**: `localhost:27017` (docker-compose overrides to `mongodb:27017` in containers)
- **Redis**: `localhost:6379` (docker-compose overrides to `redis:6379` in containers)
- **Storage**: MinIO at `localhost:9000`
- **CORS**: Relaxed (allow all origins)
- **Monitoring**: Prometheus enabled, backups disabled

#### UAT/Staging
- **Log Level**: `info` (JSON format)
- **MongoDB**: UAT instance with authentication
- **Redis**: UAT instance
- **Storage**: MinIO (Docker, default) or Hetzner Object Storage (optional)
- **CORS**: Relaxed (allow all origins)
- **Monitoring**: Full monitoring enabled, automated backups
- **Resource Limits**: Moderate (1.5 CPU, 1.5GB memory for API)

#### Production
- **Log Level**: `info` (JSON format)
- **MongoDB**: Production instance with authentication
- **Redis**: Production instance
- **Storage**: Hetzner Object Storage
- **CORS**: Strict (configured origins only)
- **Monitoring**: Full monitoring enabled, automated backups
- **Resource Limits**: Production-grade (2 CPU, 2GB memory for API)
- **Concurrency**: Higher (20 concurrent calls vs 10 in local/UAT)

## Docker Compose Integration

Each docker-compose file references a specific environment configuration:

- **`docker-compose.dev.yml`** → `config/.env.local`
- **`docker-compose.uat.yml`** → `config/.env.uat`
- **`docker-compose.production.yml`** → `config/.env.prod`

The docker-compose files override certain variables (like MongoDB and Redis URIs) to use container hostnames instead of localhost.

## Security Best Practices

### ✅ DO
- Keep `.env.base` and `.env.*.example` files in git (no secrets)
- Use placeholders (e.g., `REPLACE_WITH_*`) in example files
- Generate strong, unique secrets for each environment
- Set production secrets via CapRover UI or secrets management system
- Use different credentials for each environment
- Rotate secrets regularly

### ❌ DON'T
- Never commit `.env.local`, `.env.uat`, or `.env.prod` to git
- Never hardcode production credentials in code
- Never reuse development credentials in production
- Never share credentials via Slack, email, or other insecure channels

## Generating Secrets

```bash
# Generate JWT secret key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate a strong password
python3 -c "import secrets, string; alphabet = string.ascii_letters + string.digits + string.punctuation; print(''.join(secrets.choice(alphabet) for i in range(32)))"
```

## Verifying Configuration

After setting up a new environment, verify the configuration:

### Check Environment Variable
```bash
# Inside container
docker compose -f docker-compose.dev.yml exec api env | grep ENVIRONMENT
# Should show: ENVIRONMENT=development (or staging/production)
```

### Check Storage Connection
```bash
# Run storage integration test
docker compose -f docker-compose.dev.yml exec api pytest tests/integration/test_s3_storage.py -v
```

### Check Health Endpoint
```bash
# Check application health
curl http://localhost:3000/api/v1/health/ready

# Expected response (if all dependencies are healthy):
{
  "status": "ready",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "storage": "healthy"
  }
}
```

## Troubleshooting

### Issue: Docker compose can't find .env file
**Solution**: Ensure you've created the environment-specific file (e.g., `config/.env.local` for local dev)

```bash
# Check if file exists
ls -la config/.env.local

# If missing, create from template
cp config/.env.local.example config/.env.local
# Then edit config/.env.local and replace placeholders
```

### Issue: S3/MinIO connection fails
**Solution**: Verify storage credentials and endpoint

```bash
# Check S3 configuration
docker compose -f docker-compose.dev.yml exec api env | grep S3_

# Test MinIO connection (local)
curl http://localhost:9000/minio/health/live

# Check MinIO logs
docker compose -f docker-compose.dev.yml logs minio
```

### Issue: MongoDB connection fails in containers
**Solution**: Docker compose overrides `MONGODB_URI` to use container hostname

```bash
# Inside container, MongoDB URI should be mongodb://mongodb:27017
docker compose -f docker-compose.dev.yml exec api env | grep MONGODB_URI

# If using localhost:27017, the docker-compose override isn't working
# Check docker-compose.dev.yml environment section
```

### Issue: Variables not being loaded
**Solution**: Verify docker-compose env_file path

```bash
# Check docker-compose file references correct path
grep env_file docker-compose.dev.yml
# Should show: env_file: config/.env.local
```

## Migration from Root .env

If you have an existing `.env` file in the project root:

```bash
# 1. Backup existing .env
cp .env .env.backup

# 2. Move configuration to config directory
cp .env config/.env.local
# Or if you prefer starting fresh:
cp config/.env.local.example config/.env.local
# Then edit config/.env.local with your credentials

# 3. Test with new configuration
docker compose -f docker-compose.dev.yml up

# 4. Once verified, you can remove the root .env file
# (But keep .env.backup for safety)
```

## MongoDB Performance Tuning (Optional)

MongoDB shows startup warnings about OS-level settings. These are **informational** and do not prevent MongoDB from working correctly. However, for optimal performance (especially with large datasets), you can configure your host OS.

### macOS (Development)

MongoDB warnings about `vm.max_map_count`, `transparent_hugepage`, and `swappiness` do not apply to macOS. These are Linux-specific kernel parameters. You can safely ignore these warnings on macOS.

### Linux (Development/Production)

To eliminate warnings and improve MongoDB performance:

```bash
# 1. Increase vm.max_map_count
sudo sysctl -w vm.max_map_count=838860

# Make persistent (survives reboots)
echo "vm.max_map_count=838860" | sudo tee -a /etc/sysctl.conf

# 2. Configure transparent hugepages
echo 'always' | sudo tee /sys/kernel/mm/transparent_hugepage/enabled
echo 'defer+madvise' | sudo tee /sys/kernel/mm/transparent_hugepage/defrag
echo '0' | sudo tee /sys/kernel/mm/transparent_hugepage/khugepaged/max_ptes_none

# Make persistent (add to /etc/rc.local or systemd service)

# 3. Set swappiness to 1
sudo sysctl -w vm.swappiness=1
echo "vm.swappiness=1" | sudo tee -a /etc/sysctl.conf

# 4. Verify settings
sysctl vm.max_map_count
sysctl vm.swappiness
cat /sys/kernel/mm/transparent_hugepage/enabled
```

### Docker Desktop (Windows/macOS)

For Docker Desktop users, these settings apply to the Docker VM, not your host OS:

1. Open Docker Desktop settings
2. Go to Resources → Advanced
3. Increase memory allocation to at least 4GB for MongoDB

### Production Deployment

For production deployments, these OS optimizations are **recommended**:
- Apply the Linux kernel parameter changes on the host OS
- Use dedicated MongoDB servers with optimized configurations
- Consider MongoDB Atlas (managed service) which handles all optimizations automatically

### When to Apply These Settings

- **Development**: Optional - Only if experiencing performance issues with large datasets
- **UAT**: Recommended - Mirrors production configuration for realistic testing
- **Production**: **Required** - Essential for optimal performance and stability

## Additional Resources

- **Main Documentation**: See root `README.md` for overall project setup
- **Development Guide**: See `CLAUDE.md` for development commands and architecture
- **API Documentation**: Run the API and visit `/docs` for Swagger UI
- **Storage Setup**: See `backend/app/infrastructure/storage/README.md` for S3/MinIO details

## Environment Variables Reference

For a complete list of all environment variables and their descriptions, see:
- `config/.env.base` - All variables with descriptions and defaults
- Project documentation in root `README.md`

## Support

For configuration issues or questions:
1. Check this README first
2. Review `CLAUDE.md` for architecture details
3. Check docker-compose logs: `docker compose -f docker-compose.dev.yml logs`
4. Verify health endpoint: `curl http://localhost:3000/api/v1/health/ready`
