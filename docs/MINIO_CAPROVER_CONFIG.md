# MinIO CapRover Configuration Guide

## Problem
MinIO console shows certificate error when trying to access API at `shifo-supervisor-uat-minio-api.ss-apps.shifo.org`

## Solution: Single App Configuration

CapRover's MinIO should run as a **single app** with both console and API.

### Correct Environment Variables

For app: `shifo-supervisor-uat-minio`

```bash
# Root credentials (for both console login AND S3 API)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# Region
MINIO_REGION_NAME=eu-east-1

# Console URL (for browser access)
MINIO_BROWSER_REDIRECT_URL=https://shifo-supervisor-uat-minio.ss-apps.shifo.org

# DO NOT set MINIO_SERVER_URL - let MinIO auto-configure
# OR set to internal service name:
# MINIO_SERVER_URL=http://srv-captain--shifo-supervisor-uat-minio:9000
```

### CapRover App Settings

**HTTP Settings:**
- ✅ Enable HTTPS: **Checked**
- ✅ Force HTTPS: **Checked**
- Container HTTP Port: **9001** (for console)
- ✅ Websocket Support: **Unchecked**

**Port Mapping (Advanced):**
If you need direct S3 API access from outside:
- Container Port: **9000**
- Host Port: Auto-assign

But for internal access (from backend/worker), use:
```
http://srv-captain--shifo-supervisor-uat-minio:9000
```

### Application Configuration (Backend/Worker/Beat)

```bash
# S3 Configuration (internal network)
S3_ENDPOINT_URL=http://srv-captain--shifo-supervisor-uat-minio:9000
S3_BUCKET_NAME=shifo-recordings
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_REGION=eu-east-1
```

### Console Access

**URL:** `https://shifo-supervisor-uat-minio.ss-apps.shifo.org`

**Credentials:**
- Username: `minioadmin`
- Password: `minioadmin`

### Delete Unnecessary API App

If `shifo-supervisor-uat-minio-api` exists as a separate app, you can safely delete it:

1. Go to CapRover → Apps
2. Find `shifo-supervisor-uat-minio-api`
3. Click app → **Delete**

The console and API should both run from `shifo-supervisor-uat-minio`.

### Troubleshooting

**If console still shows "invalid session":**

1. Check MinIO logs:
   ```bash
   # Via CapRover Dashboard
   Apps → shifo-supervisor-uat-minio → Logs
   ```

2. Restart the app:
   ```bash
   # Via CapRover Dashboard
   Apps → shifo-supervisor-uat-minio → Save & Update
   ```

3. Clear browser cache and try again

4. Verify DNS resolves correctly:
   ```bash
   nslookup shifo-supervisor-uat-minio.ss-apps.shifo.org
   ```

**If S3 uploads fail from backend:**

Check that `S3_ENDPOINT_URL` uses **internal service name** not HTTPS URL:
```bash
# ✅ Correct (internal)
S3_ENDPOINT_URL=http://srv-captain--shifo-supervisor-uat-minio:9000

# ❌ Wrong (external, SSL issues)
S3_ENDPOINT_URL=https://shifo-supervisor-uat-minio.ss-apps.shifo.org
```
