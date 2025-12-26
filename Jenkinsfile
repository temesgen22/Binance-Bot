pipeline {
  agent any

  environment {
    DEPLOY_ENABLED = 'true'
    DEPLOY_SSH_CREDENTIALS_ID = 'cloud-server-ssh'
    DEPLOY_SSH_HOST = '95.216.216.26'
    DEPLOY_SSH_PORT = '22'
    DEPLOY_PATH = '/home/jenkins-deploy/binance-bot'
    DEPLOY_BRANCH = 'main'
    DEPLOY_COMPOSE_FILE = 'docker-compose.prod.yml'
  }

  options { timestamps() }

  // Automatic triggers: Uncomment one of these for automatic deployment
  // Option 1: GitHub webhook trigger (recommended)
  // triggers {
  //   githubPush()
  // }
  
  // Option 2: Poll SCM every 5 minutes
  // triggers {
  //   pollSCM('H/5 * * * *')
  // }
  
  // Option 3: Schedule daily at 2 AM
  // triggers {
  //   cron('H 2 * * *')
  // }

  stages {
    stage('Checkout') {
      steps { checkout scm }
    }

    stage('Run Tests (optional)') {
      when { expression { return fileExists('requirements.txt') } }
      steps {
        script {
          if (isUnix()) {
            sh '''#!/bin/bash
              set -e
              python3 -V || python -V
              python3 -m venv .venv || python -m venv .venv
              . .venv/bin/activate
              pip install -U pip
              pip install -r requirements.txt
              pip install pytest pytest-asyncio
              # Skip database tests if DATABASE_URL is not set (common in CI)
              # Database tests are marked with @pytest.mark.database and will skip gracefully
              pytest -q -m "not database" || pytest -q --ignore=tests/test_async_database.py
            '''
          } else {
            powershell '''
              $ErrorActionPreference="Stop"
              python --version
              python -m venv .venv
              .\\.venv\\Scripts\\Activate.ps1
              python -m pip install -U pip
              pip install -r requirements.txt
              pip install pytest pytest-asyncio
              pytest -q -m "not slow and not database"
            '''
          }
        }
      }
    }

    stage('Deploy to Production (SSH)') {
      when { expression { return env.DEPLOY_ENABLED == 'true' } }
      steps {
        withCredentials([
          sshUserPrivateKey(
            credentialsId: env.DEPLOY_SSH_CREDENTIALS_ID,
            usernameVariable: 'SSH_USER',
            keyFileVariable: 'SSH_KEY'
          )
        ]) {
          script {
            // Use bash if agent is unix; PowerShell if windows
            if (isUnix()) {
              sh '''#!/bin/bash
                set -euo pipefail

                HOST="$DEPLOY_SSH_HOST"
                PORT="$DEPLOY_SSH_PORT"
                PATH_ON_SERVER="$DEPLOY_PATH"
                BRANCH="$DEPLOY_BRANCH"
                COMPOSE_FILE="$DEPLOY_COMPOSE_FILE"
                REPO_URL="$(git config --get remote.origin.url)"

                if [ ! -f "$SSH_KEY" ]; then
                  echo "❌ SSH key file not found: $SSH_KEY"
                  exit 1
                fi

                chmod 600 "$SSH_KEY" || true

                SSH_OPTS=( -i "$SSH_KEY" -p "$PORT"
                  -o IdentitiesOnly=yes
                  -o PreferredAuthentications=publickey
                  -o PubkeyAuthentication=yes
                  -o BatchMode=yes
                  -o StrictHostKeyChecking=no
                  -o UserKnownHostsFile=/dev/null
                  -o ConnectTimeout=10
                )

                SCP_OPTS=( -i "$SSH_KEY" -P "$PORT"
                  -o IdentitiesOnly=yes
                  -o PreferredAuthentications=publickey
                  -o PubkeyAuthentication=yes
                  -o BatchMode=yes
                  -o StrictHostKeyChecking=no
                  -o UserKnownHostsFile=/dev/null
                  -o ConnectTimeout=10
                )

                echo "🚀 Deploying to $SSH_USER@$HOST:$PORT"

                echo "🔍 Testing SSH..."
                ssh "${SSH_OPTS[@]}" "$SSH_USER@$HOST" "whoami"

                # Ensure deploy dir exists first
                ssh "${SSH_OPTS[@]}" "$SSH_USER@$HOST" "mkdir -p '$PATH_ON_SERVER'"

                # Copy redis.conf if exists
                if [ -f "redis.conf" ]; then
                  echo "📝 Copying redis.conf..."
                  scp "${SCP_OPTS[@]}" redis.conf "$SSH_USER@$HOST:$PATH_ON_SERVER/redis.conf"
                fi

                # OPTIONAL: copy .env from Jenkins (recommended via Jenkins Secret File)
                # scp "${SCP_OPTS[@]}" "$ENV_FILE" "$SSH_USER@$HOST:$PATH_ON_SERVER/.env"

                ssh "${SSH_OPTS[@]}" "$SSH_USER@$HOST" \
                  "PATH_ON_SERVER='$PATH_ON_SERVER' BRANCH='$BRANCH' REPO_URL='$REPO_URL' COMPOSE_FILE='$COMPOSE_FILE' bash -s" <<'REMOTE'
                set -euo pipefail

                # Backup .env file if it exists (before any destructive operations)
                ENV_BACKUP="/tmp/binance-bot-env-backup-$(date +%s)"
                if [ -f "$PATH_ON_SERVER/.env" ]; then
                  echo "💾 Backing up existing .env file..."
                  cp "$PATH_ON_SERVER/.env" "$ENV_BACKUP"
                fi

                # Check if directory exists and is a git repo
                if [ -d "$PATH_ON_SERVER/.git" ]; then
                  echo "📁 Existing git repository found"
                  cd "$PATH_ON_SERVER"
                elif [ -d "$PATH_ON_SERVER" ]; then
                  echo "⚠️ Directory exists but is not a git repo, removing..."
                  rm -rf "$PATH_ON_SERVER"
                  echo "📦 Cloning repo..."
                  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$PATH_ON_SERVER"
                  cd "$PATH_ON_SERVER"
                else
                  echo "📦 First deploy: cloning repo..."
                  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$PATH_ON_SERVER"
                  cd "$PATH_ON_SERVER"
                fi

                echo "📥 Updating code..."
                git fetch origin "$BRANCH"
                git reset --hard "origin/$BRANCH"

                # Restore .env file if it was backed up
                if [ -f "$ENV_BACKUP" ]; then
                  echo "💾 Restoring .env file from backup..."
                  cp "$ENV_BACKUP" "$PATH_ON_SERVER/.env"
                  rm -f "$ENV_BACKUP"
                  echo "✅ .env file restored"
                fi

                if [ ! -f .env ]; then
                  echo "❌ .env missing at $PATH_ON_SERVER/.env"
                  exit 1
                fi

                echo "🐳 Deploying containers..."
                docker compose -f "$COMPOSE_FILE" up -d --build

                echo "⏳ Waiting..."
                sleep 10

                echo "🔍 Verifying database exists..."
                DB_EXISTS=$(docker exec binance-bot-postgres psql -U postgres -lqt 2>/dev/null | grep -w binance_bot || echo "")
                if [ -n "$DB_EXISTS" ]; then
                  echo "✅ Database exists"
                else
                  echo "⚠️  Database not found, creating it..."
                  if docker exec binance-bot-postgres psql -U postgres -c "CREATE DATABASE binance_bot;" 2>/dev/null; then
                    echo "✅ Database created successfully"
                  else
                    echo "❌ Failed to create database. Attempting to continue anyway..."
                  fi
                fi

        echo "🔄 Running migrations..."
        # Run migrations and capture output
        # Set ALEMBIC_MIGRATION env var to allow default JWT secret during migrations
        MIGRATION_OUTPUT=$(docker exec -e ALEMBIC_MIGRATION=true binance-bot-api alembic upgrade head 2>&1) || MIGRATION_STATUS=$?
                echo "$MIGRATION_OUTPUT"
                
                if [ "${MIGRATION_STATUS:-0}" -eq 0 ]; then
                  echo "✅ Migrations completed successfully"
                else
                  # Check if error is due to existing tables
                  if echo "$MIGRATION_OUTPUT" | grep -qE "(already exists|DuplicateTable)"; then
                    echo "⚠️ Tables already exist, syncing Alembic version table..."
                    docker exec binance-bot-api alembic stamp head
                    echo "✅ Database stamped to current head"
                  else
                    echo "❌ Migration failed with unexpected error"
                    exit 1
                  fi
                fi

                # Wait for FastAPI service to fully initialize (lifespan startup can take time)
                echo "⏳ Waiting for FastAPI service to initialize (180 seconds)..."
                sleep 180

                # Check if container is running
                echo "🔍 Checking container status..."
                if ! docker ps --format '{{.Names}}' | grep -q '^binance-bot-api$'; then
                  echo "❌ API container is not running!"
                  echo "📋 Container status:"
                  docker ps -a --filter name=binance-bot-api --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
                  echo "📋 API container logs (last 100 lines):"
                  docker logs --tail 100 binance-bot-api || true
                  exit 1
                fi

                # Check if container is healthy (if healthcheck is configured)
                CONTAINER_STATUS=$(docker inspect --format='{{.State.Status}}' binance-bot-api 2>/dev/null || echo "unknown")
                if [ "$CONTAINER_STATUS" != "running" ]; then
                  echo "⚠️  Container status: $CONTAINER_STATUS"
                  echo "📋 API container logs (last 100 lines):"
                  docker logs --tail 100 binance-bot-api || true
                fi

                echo "✅ Waiting for Docker health check to pass..."
                # Wait for Docker's built-in health check (from Dockerfile)
                # Health check: interval=10s, timeout=10s, start-period=120s, retries=12
                # Maximum wait time: start-period (120s) + (retries * interval) = 120 + (12 * 10) = 240s
                MAX_WAIT_TIME=240
                ELAPSED=0
                HEALTH_CHECK_PASSED=false
                
                while [ $ELAPSED -lt $MAX_WAIT_TIME ]; do
                  HEALTH_STATUS=$(docker inspect --format='{{.State.Health.Status}}' binance-bot-api 2>/dev/null || echo "unknown")
                  
                  if [ "$HEALTH_STATUS" = "healthy" ]; then
                    echo "✅ Docker health check passed (status: $HEALTH_STATUS)"
                    HEALTH_CHECK_PASSED=true
                    break
                  elif [ "$HEALTH_STATUS" = "unhealthy" ]; then
                    echo "❌ Docker health check reports unhealthy"
                    break
                  else
                    # Status is "starting" or "unknown" - still waiting
                    echo "⏳ Health check status: $HEALTH_STATUS (waiting...)"
                    sleep 10
                    ELAPSED=$((ELAPSED + 10))
                  fi
                done

                # Verify health check passed
                if [ "$HEALTH_CHECK_PASSED" != "true" ]; then
                  FINAL_STATUS=$(docker inspect --format='{{.State.Health.Status}}' binance-bot-api 2>/dev/null || echo "unknown")
                  echo "❌ Docker health check failed after waiting (final status: $FINAL_STATUS)"
                  echo "📋 Container status:"
                  docker ps -a --filter name=binance-bot-api --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
                  echo "📋 Health check details:"
                  docker inspect --format='{{json .State.Health}}' binance-bot-api 2>/dev/null | python3 -m json.tool 2>/dev/null || docker inspect binance-bot-api | grep -A 20 '"Health"' || true
                  echo "📋 API container logs (last 100 lines):"
                  docker logs --tail 100 binance-bot-api || true
                  echo "📋 Checking if port 8000 is listening inside container:"
                  docker exec binance-bot-api sh -c "netstat -tlnp 2>/dev/null | grep 8000 || ss -tlnp 2>/dev/null | grep 8000 || echo 'Port 8000 not found in netstat/ss output'" || true
                  exit 1
                fi

                # Optional: Check Nginx reverse proxy (if Nginx is configured)
                if command -v nginx >/dev/null 2>&1 && [ -f /etc/nginx/sites-enabled/binance-bot ]; then
                  echo "✅ Health check (Nginx proxy)..."
                  if curl -fsS http://localhost/health >/dev/null 2>&1; then
                    echo "✅ Nginx proxy health check OK"
                  else
                    echo "⚠️  Nginx proxy health check failed (Nginx may need configuration)"
                  fi
                fi

                docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
                exit 0
REMOTE
              '''
            } else {
              powershell """
                \$ErrorActionPreference='Stop'
                \$REPO_URL='${scm.userRemoteConfigs[0].url}'
                \$COMPOSE_FILE='${env.DEPLOY_COMPOSE_FILE}'
                \$SSH_OPTS = @(
                  '-i', '${'$'}env:SSH_KEY',
                  '-p', '${env.DEPLOY_SSH_PORT}',
                  '-o', 'StrictHostKeyChecking=no',
                  '-o', 'UserKnownHostsFile=/dev/null'
                )

                ssh @SSH_OPTS ${'$'}env:SSH_USER@${env.DEPLOY_SSH_HOST} `
                  "set -e;
                   mkdir -p ${env.DEPLOY_PATH};
                   if [ ! -d ${env.DEPLOY_PATH}/.git ]; then
                     echo '📦 First deploy: cloning repo...';
                     git clone --branch ${env.DEPLOY_BRANCH} --single-branch \$REPO_URL ${env.DEPLOY_PATH};
                   fi;
                   cd ${env.DEPLOY_PATH};
                   echo '📥 Updating code...';
                   git fetch origin ${env.DEPLOY_BRANCH};
                   git reset --hard origin/${env.DEPLOY_BRANCH};
                   if [ -f .env.example ] && [ ! -f .env ]; then
                     echo '📝 Creating .env from .env.example...';
                     cp .env.example .env;
                   fi;
                   echo '🐳 Deploying containers...';
                   docker compose -f $COMPOSE_FILE up -d --build;
                   echo '⏳ Waiting for containers to start...';
                   sleep 10;
                   echo '🔄 Running database migrations...';
                   docker exec -e ALEMBIC_MIGRATION=true binance-bot-api alembic upgrade head 2>/dev/null || echo '⚠️  Migrations failed';
                   echo '⏳ Waiting for FastAPI service to initialize (30 seconds)...';
                   sleep 30;
                   echo '🔍 Checking container status...';
                   if ! docker ps --format '{{.Names}}' | grep -q '^binance-bot-api\$'; then
                     echo '❌ API container is not running!';
                     echo '📋 Container status:';
                     docker ps -a --filter name=binance-bot-api --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}';
                     echo '📋 API container logs (last 100 lines):';
                     docker logs --tail 100 binance-bot-api || true;
                     exit 1;
                   fi;
                   CONTAINER_STATUS=\$(docker inspect --format='{{.State.Status}}' binance-bot-api 2>/dev/null || echo 'unknown');
                   if [ \"\$CONTAINER_STATUS\" != \"running\" ]; then
                     echo \"⚠️  Container status: \$CONTAINER_STATUS\";
                     echo '📋 API container logs (last 100 lines):';
                     docker logs --tail 100 binance-bot-api || true;
                   fi;
                   echo '✅ Waiting for Docker health check to pass...';
                   MAX_WAIT_TIME=240;
                   ELAPSED=0;
                   HEALTH_CHECK_PASSED=false;
                   while [ \$ELAPSED -lt \$MAX_WAIT_TIME ]; do
                     HEALTH_STATUS=\$(docker inspect --format='{{.State.Health.Status}}' binance-bot-api 2>/dev/null || echo 'unknown');
                     if [ \"\$HEALTH_STATUS\" = 'healthy' ]; then
                       echo '✅ Docker health check passed (status: '\$HEALTH_STATUS')';
                       HEALTH_CHECK_PASSED=true;
                       break;
                     elif [ \"\$HEALTH_STATUS\" = 'unhealthy' ]; then
                       echo '❌ Docker health check reports unhealthy';
                       break;
                     else
                       echo '⏳ Health check status: '\$HEALTH_STATUS' (waiting...)';
                       sleep 10;
                       ELAPSED=\$((ELAPSED + 10));
                     fi;
                   done;
                   if [ \"\$HEALTH_CHECK_PASSED\" != 'true' ]; then
                     FINAL_STATUS=\$(docker inspect --format='{{.State.Health.Status}}' binance-bot-api 2>/dev/null || echo 'unknown');
                     echo '❌ Docker health check failed after waiting (final status: '\$FINAL_STATUS')';
                     echo '📋 Container status:';
                     docker ps -a --filter name=binance-bot-api --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}';
                     echo '📋 Health check details:';
                     docker inspect --format='{{json .State.Health}}' binance-bot-api 2>/dev/null | python3 -m json.tool 2>/dev/null || docker inspect binance-bot-api | grep -A 20 '"Health"' || true;
                     echo '📋 API container logs (last 100 lines):';
                     docker logs --tail 100 binance-bot-api || true;
                     echo '📋 Checking if port 8000 is listening inside container:';
                     docker exec binance-bot-api sh -c 'netstat -tlnp 2>/dev/null | grep 8000 || ss -tlnp 2>/dev/null | grep 8000 || echo \"Port 8000 not found in netstat/ss output\"' || true;
                     echo '❌ Deployment verification failed - pipeline will fail';
                     exit 1;
                   fi
                   echo '✅ Running containers:';
                   docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'
                  "
              """
            }
          }
        }
      }
    }
  }

  post {
    always { deleteDir() }
    failure { echo '❌ Pipeline failed. Check console output.' }
  }
}