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
              sh """#!/bin/bash
                set -e
                REPO_URL="${scm.userRemoteConfigs[0].url}"
                
                # Copy redis.conf if it exists
                if [ -f "redis.conf" ]; then
                  echo "📝 Copying redis.conf to deployment..."
                  scp -i '$SSH_KEY' -P ${env.DEPLOY_SSH_PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null redis.conf \\$SSH_USER@${env.DEPLOY_SSH_HOST}:${env.DEPLOY_PATH}/redis.conf || echo "⚠️  Failed to copy redis.conf"
                fi

                ssh -i '$SSH_KEY' -p ${env.DEPLOY_SSH_PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \\$SSH_USER@${env.DEPLOY_SSH_HOST} "set -e
                  mkdir -p ${env.DEPLOY_PATH}
                  if [ ! -d ${env.DEPLOY_PATH}/.git ]; then
                    echo '📦 First deploy: cloning repo...'
                    git clone --branch ${env.DEPLOY_BRANCH} --single-branch \$REPO_URL ${env.DEPLOY_PATH}
                  fi

                  cd ${env.DEPLOY_PATH}
                  echo '📥 Updating code...'
                  git fetch origin ${env.DEPLOY_BRANCH}
                  git reset --hard origin/${env.DEPLOY_BRANCH}

                  # Copy .env.example to .env if .env doesn't exist
                  if [ -f .env.example ] && [ ! -f .env ]; then
                    echo '📝 Creating .env from .env.example...'
                    cp .env.example .env
                  fi

                  echo '🐳 Deploying containers...'
                  docker compose -f ${env.DEPLOY_COMPOSE_FILE} up -d --build

                  echo '⏳ Waiting for containers to start...'
                  sleep 10

                  # Run database migrations
                  echo '🔄 Running database migrations...'
                  docker exec binance-bot-api alembic upgrade head 2>/dev/null || echo '⚠️  Migrations failed or alembic not available'

                  # Verify deployment with retries
                  echo '✅ Verifying deployment...'
                  sleep 5
                  MAX_RETRIES=5
                  RETRY_COUNT=0
                  HEALTH_CHECK_PASSED=false
                  
                  while [ \\\$RETRY_COUNT -lt \\\$MAX_RETRIES ]; do
                    if docker exec binance-bot-api curl -f http://localhost:8000/health > /dev/null 2>&1; then
                      echo '✅ Health check passed!'
                      HEALTH_CHECK_PASSED=true
                      break
                    else
                      RETRY_COUNT=\\\$(expr \\\$RETRY_COUNT + 1)
                      if [ \\\$RETRY_COUNT -lt \\\$MAX_RETRIES ]; then
                        echo \"⚠️  Health check failed (attempt \\\$RETRY_COUNT/\\\$MAX_RETRIES), retrying in 5 seconds...\"
                        sleep 5
                      fi
                    fi
                  done
                  
                  if [ \"\\\$HEALTH_CHECK_PASSED\" != \"true\" ]; then
                    echo '❌ Health check failed after \\\$MAX_RETRIES attempts!'
                    echo '📋 Container status:'
                    docker ps -a --filter name=binance-bot-api --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'
                    echo '📋 API container logs (last 50 lines):'
                    docker logs --tail 50 binance-bot-api || true
                    echo '❌ Deployment verification failed - pipeline will fail'
                    exit 1
                  fi

                  echo '✅ Running containers:'
                  docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'
                "
              """
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
                   docker exec binance-bot-api alembic upgrade head 2>/dev/null || echo '⚠️  Migrations failed';
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