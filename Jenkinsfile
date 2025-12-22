pipeline {
  agent any

  environment {
    DEPLOY_ENABLED = 'true'
    DEPLOY_SSH_CREDENTIALS_ID = 'cloud-server-ssh'
    DEPLOY_SSH_HOST = '95.216.216.26'
    DEPLOY_SSH_PORT = '22'
    DEPLOY_PATH = '/home/jenkins-deploy/binance-bot'
    DEPLOY_BRANCH = 'main'
    DEPLOY_COMPOSE_FILE = 'docker-compose.yml'
  }

  options { timestamps() }

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
              pytest -q
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
              pytest -q
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

                echo "✅ Health check..."
                for i in 1 2 3 4 5; do
                  if docker exec binance-bot-api curl -fsS http://localhost:8000/health >/dev/null; then
                    echo "✅ Health OK"
                    docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
                    exit 0
                  fi
                  echo "⚠️ Health failed ($i/5), retrying..."
                  sleep 5
                done

                echo "❌ Health check failed"
                docker logs --tail 80 binance-bot-api || true
                exit 1
REMOTE
              '''
            } else {
              powershell """
                \$ErrorActionPreference='Stop'
                \$REPO_URL='${scm.userRemoteConfigs[0].url}'
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
                   docker compose -f ${env.DEPLOY_COMPOSE_FILE} up -d --build;
                   echo '⏳ Waiting for containers to start...';
                   sleep 10;
                   echo '🔄 Running database migrations...';
                   docker exec -e ALEMBIC_MIGRATION=true binance-bot-api alembic upgrade head 2>/dev/null || echo '⚠️  Migrations failed';
                   echo '✅ Verifying deployment...';
                   sleep 5;
                   MAX_RETRIES=5;
                   RETRY_COUNT=0;
                   HEALTH_CHECK_PASSED=false;
                   while [ \$RETRY_COUNT -lt \$MAX_RETRIES ]; do
                     if docker exec binance-bot-api curl -f http://localhost:8000/health > /dev/null 2>&1; then
                       echo '✅ Health check passed!';
                       HEALTH_CHECK_PASSED=true;
                       break;
                     else
                       RETRY_COUNT=\$((RETRY_COUNT + 1));
                       if [ \$RETRY_COUNT -lt \$MAX_RETRIES ]; then
                         echo \"⚠️  Health check failed (attempt \$RETRY_COUNT/\$MAX_RETRIES), retrying in 5 seconds...\";
                         sleep 5;
                       fi;
                     fi;
                   done;
                   if [ \"\$HEALTH_CHECK_PASSED\" != \"true\" ]; then
                     echo '❌ Health check failed after \$MAX_RETRIES attempts!';
                     echo '📋 Container status:';
                     docker ps -a --filter name=binance-bot-api --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}';
                     echo '📋 API container logs (last 50 lines):';
                     docker logs --tail 50 binance-bot-api || true;
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