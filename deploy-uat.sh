#!/bin/bash
# UAT Deployment Script for CapRover
# Deploys backend, worker, and beat services to shifo-supervisor-uat project

set -e

CAPROVER_MACHINE="captain-ss"
BRANCH=$(git rev-parse --abbrev-ref HEAD)
COMMIT=$(git rev-parse --short HEAD)

echo "=========================================="
echo "Deploying to UAT"
echo "Branch: $BRANCH"
echo "Commit: $COMMIT"
echo "=========================================="

# Function to deploy a service
deploy_service() {
    local SERVICE=$1
    local APP_NAME=$2
    local DOCKERFILE=$3

    echo ""
    echo "Deploying $SERVICE..."
    echo "App: $APP_NAME"
    echo "Dockerfile: $DOCKERFILE"

    # Create temporary captain-definition
    cat > captain-definition <<EOF
{
  "schemaVersion": 2,
  "dockerfilePath": "$DOCKERFILE"
}
EOF

    # Deploy to CapRover
    caprover deploy \
        --caproverName "$CAPROVER_MACHINE" \
        --caproverApp "$APP_NAME"

    echo "✓ $SERVICE deployed successfully"
}

# Deploy Backend
deploy_service "Backend" "shifo-supervisor-uat-backend" "./docker/Dockerfile.api"

# Deploy Worker
deploy_service "Worker" "shifo-supervisor-uat-worker" "./docker/Dockerfile.worker"

# Deploy Beat
deploy_service "Beat" "shifo-supervisor-uat-beat" "./docker/Dockerfile.beat"

echo ""
echo "=========================================="
echo "UAT DEPLOYMENT COMPLETE!"
echo "Backend: https://shifo-supervisor-uat-backend.ss-apps.shifo.org"
echo "=========================================="
