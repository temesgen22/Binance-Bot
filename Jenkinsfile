pipeline {
    agent any

    environment {
        // Try python3 first, fallback to python
        PYTHON = 'python3'
        VENV = '.venv'
        IMAGE_NAME = 'binance-bot'
        SSH_CRED_ID = 'cloud-server-ssh'   // same ID you set in Jenkins
        SERVER_HOST = '95.216.216.26'     // or DNS name
                          // 🔰 Enable deployment and tell the deploy stage which creds/host to use
        DEPLOY_ENABLED = 'true'
        DEPLOY_SSH_CREDENTIALS_ID = 'cloud-server-ssh'
        DEPLOY_SSH_HOST = '95.216.216.26'
        DEPLOY_SSH_PORT = '22'
        DEPLOY_PATH = '/home/jenkins-deploy/binance-bot'
        // Optionally set DOCKER_REGISTRY_URL and DOCKER_REGISTRY_CREDENTIALS_ID in Jenkins
        // Deployment settings (optional):
        // DEPLOY_ENABLED = 'true' to enable deployment
        // DEPLOY_SSH_CREDENTIALS_ID = Jenkins credential ID for SSH key
        // DEPLOY_SSH_HOST = Cloud server hostname/IP
        // DEPLOY_SSH_PORT = SSH port (default: 22)
        // DEPLOY_PATH = Deployment path on server (default: /opt/binance-bot)
    }

    options {
        // ansiColor('xterm')
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Check Prerequisites') {
            steps {
                script {
                    // Check Python
                    def pythonCheck = sh(
                        script: 'command -v python3 || command -v python || exit 1',
                        returnStatus: true
                    )
                    if (pythonCheck != 0) {
                        error('Python 3 is not installed. Please install Python 3.11+ on the Jenkins agent.')
                    }
                    
                    // Check if running as root (needed for apt-get installs)
                    def isRoot = sh(
                        script: 'test "$(id -u)" = "0" && echo "yes" || echo "no"',
                        returnStdout: true
                    ).trim()
                    if (isRoot == "no") {
                        echo "⚠️  Warning: Not running as root. Some package installations may fail."
                        echo "   If venv creation fails, ensure python3-venv is pre-installed or run Jenkins as root."
                    }
                    
                    // Check Docker
                    def dockerCheck = sh(
                        script: 'command -v docker || exit 1',
                        returnStatus: true
                    )
                    if (dockerCheck != 0) {
                        error('Docker is not installed. Please install Docker on the Jenkins agent.')
                    }
                    
                    // Check if Docker CLI is available
                    def dockerCliCheck = sh(
                        script: 'command -v docker > /dev/null 2>&1 || exit 1',
                        returnStatus: true
                    )
                    if (dockerCliCheck != 0) {
                        error("""
Docker CLI is not installed in the Jenkins container.

If Jenkins is running in Docker, you need to:
1. Install Docker CLI in the container, OR
2. Mount Docker socket and binary from host

Quick fix (if Jenkins is in Docker):
  docker exec -u root jenkins bash -c "apt-get update && apt-get install -y docker.io"
  docker restart jenkins
""")
                    }

                    // Verify Docker daemon is running
                    def dockerDaemonCheck = sh(
                        script: 'docker info > /dev/null 2>&1 || exit 1',
                        returnStatus: true
                    )
                    if (dockerDaemonCheck != 0) {
                        def dockerError = sh(
                            script: 'docker info 2>&1 || true',
                            returnStdout: true
                        ).trim()
                        error("""
Docker daemon is not accessible. Please check Docker setup.

Error details:
${dockerError}

If Jenkins is running in Docker:
  - Ensure Docker socket is mounted: -v /var/run/docker.sock:/var/run/docker.sock

If Jenkins is on a host/server:
  - Start Docker: sudo systemctl start docker
  - Add Jenkins user to docker group: sudo usermod -aG docker jenkins
  - Restart Jenkins: sudo systemctl restart jenkins
""")
                    }

                    echo "✓ Python found: ${env.PYTHON}"
                    echo "✓ Docker found and running"
                }
            }
        }

        stage('Set up Python environment') {
            steps {
                // Pure bash, no Groovy interpolation needed
                sh '''#!/bin/bash
                set -e

                PYTHON_CMD="$(command -v python3 || command -v python)"
                PYTHON_VER="$($PYTHON_CMD --version | cut -d' ' -f2 | cut -d'.' -f1,2)"

                echo "Using Python: $PYTHON_CMD (version $PYTHON_VER)"
                echo "Virtualenv path: $VENV"

                # Try to create venv, if it fails, install python3-venv package
                if ! "$PYTHON_CMD" -m venv "$VENV" 2>/dev/null; then
                    echo "python3-venv not available, trying to install..."

                    if [ "$(id -u)" = "0" ]; then
                        apt-get update -qq
                        # Try version-specific package first, fallback to generic
                        apt-get install -y "python${PYTHON_VER}-venv" 2>/dev/null || apt-get install -y python3-venv
                        "$PYTHON_CMD" -m venv "$VENV"
                    else
                        echo "⚠️  Not running as root. Cannot install python3-venv automatically."
                        echo "   Please ensure python3-venv is pre-installed in the Jenkins container."
                        echo "   Example (from host): docker exec -u root jenkins apt-get update && docker exec -u root jenkins apt-get install -y python3-venv"
                        exit 1
                    fi
                fi

                . "$VENV/bin/activate"
                pip install --upgrade pip
                pip install -r requirements.txt
                # Dev dependencies for tests (async support)
                pip install pytest pytest-asyncio
                '''
            }
        }

        stage('Run Tests') {
            steps {
                sh '''#!/bin/bash
                set -e
                . "$VENV/bin/activate"
                pytest tests/ -v
                '''
            }
        }

        stage('Build Docker image') {
            steps {
                sh '''#!/bin/bash
                set -e
                # Build Docker image
                # Note: DNS resolution for Docker Hub is handled at the Docker daemon level
                # If DNS issues occur, configure DNS in /etc/docker/daemon.json on the Jenkins host
                docker build -t "$IMAGE_NAME:$BUILD_NUMBER" .
                '''
            }
        }

        stage('Push Docker image') {
            when {
                expression {
                    return env.DOCKER_REGISTRY_URL?.trim() && env.DOCKER_REGISTRY_CREDENTIALS_ID?.trim()
                }
            }
            steps {
                script {
                    withCredentials([
                        usernamePassword(
                            credentialsId: env.DOCKER_REGISTRY_CREDENTIALS_ID,
                            usernameVariable: 'DOCKER_REGISTRY_USR',
                            passwordVariable: 'DOCKER_REGISTRY_PSW'
                        )
                    ]) {
                        sh '''#!/bin/bash
                        set -e
                        echo "$DOCKER_REGISTRY_PSW" | docker login "$DOCKER_REGISTRY_URL" -u "$DOCKER_REGISTRY_USR" --password-stdin
                        docker tag "$IMAGE_NAME:$BUILD_NUMBER" "$DOCKER_REGISTRY_URL/$IMAGE_NAME:$BUILD_NUMBER"
                        docker push "$DOCKER_REGISTRY_URL/$IMAGE_NAME:$BUILD_NUMBER"
                        echo "✅ Image pushed: $DOCKER_REGISTRY_URL/$IMAGE_NAME:$BUILD_NUMBER"
                        '''
                    }
                }
            }
        }

        stage('Deploy to Cloud Server') {
            when {
                expression {
                    return env.DEPLOY_ENABLED == 'true' && env.DEPLOY_SSH_CREDENTIALS_ID?.trim()
                }
            }
            steps {
                script {
                    withCredentials([
                        sshUserPrivateKey(
                            credentialsId: env.DEPLOY_SSH_CREDENTIALS_ID,
                            usernameVariable: 'SSH_USER',
                            keyFileVariable: 'SSH_KEY'
                        )
                    ]) {
                        sh """#!/bin/bash
                        set -e

                        SSH_HOST="${env.DEPLOY_SSH_HOST ?: ''}"
                        SSH_PORT="${env.DEPLOY_SSH_PORT ?: '22'}"
                        DEPLOY_PATH="${env.DEPLOY_PATH ?: '/opt/binance-bot'}"
                        COMPOSE_FILE="${env.DEPLOY_COMPOSE_FILE ?: 'docker-compose.yml'}"

                        if [ -z "\$SSH_HOST" ]; then
                            echo "❌ DEPLOY_SSH_HOST not set. Skipping deployment."
                            exit 0
                        fi

                        echo "🚀 Deploying to \$SSH_USER@\$SSH_HOST:\$SSH_PORT"

                        # Setup SSH options
                        SSH_OPTS="-i \$SSH_KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"



                        # Create deployment directory
                        ssh \$SSH_OPTS -p \$SSH_PORT \$SSH_USER@\$SSH_HOST "mkdir -p \$DEPLOY_PATH"




                         echo "📥 Pulling latest code from GitHub..."
                         ssh \$SSH_OPTS -p \$SSH_PORT \$SSH_USER@\$SSH_HOST "
                              cd \$DEPLOY_PATH
                              # Fetch latest from remote
                              git fetch origin main
                              # Reset local branch to exactly match remote (handles divergent branches)
                              git reset --hard origin/main
                              # Ensure we're on main branch
                              git checkout main 2>/dev/null || true
                         "

                        # Copy .env.example if .env doesn't exist
                        if [ -f ".env.example" ]; then
                            ssh \$SSH_OPTS \$SSH_USER@\$SSH_HOST "
                                if [ ! -f \$DEPLOY_PATH/.env ]; then
                                    echo '📝 Creating .env from .env.example...'
                                    cp \$DEPLOY_PATH/.env.example \$DEPLOY_PATH/.env 2>/dev/null || true
                                fi
                            "
                        fi

                        # Copy redis.conf to deployment (required for Redis to start)
                        if [ -f "redis.conf" ]; then
                            echo "📝 Copying redis.conf to deployment..."
                            scp \$SSH_OPTS -P \$SSH_PORT redis.conf \$SSH_USER@\$SSH_HOST:\$DEPLOY_PATH/redis.conf
                        else
                            echo "⚠️  Warning: redis.conf not found in repository!"
                            echo "   Redis container may fail to start without this file."
                        fi
                        
                        # Copy restore scripts to deployment (needed for automatic Redis restore)
                        if [ -d "scripts" ]; then
                            echo "📝 Copying restore scripts to deployment..."
                            ssh \$SSH_OPTS -p \$SSH_PORT \$SSH_USER@\$SSH_HOST "mkdir -p \$DEPLOY_PATH/scripts"
                            scp \$SSH_OPTS -P \$SSH_PORT scripts/restore_redis.sh \$SSH_USER@\$SSH_HOST:\$DEPLOY_PATH/scripts/ 2>/dev/null || echo "   ⚠️  restore_redis.sh not found"
                            scp \$SSH_OPTS -P \$SSH_PORT scripts/check_and_restore_redis.sh \$SSH_USER@\$SSH_HOST:\$DEPLOY_PATH/scripts/ 2>/dev/null || echo "   ⚠️  check_and_restore_redis.sh not found"
                        fi

                        # Pull latest image and restart
                       # if [ -n "${env.DOCKER_REGISTRY_URL?.trim()}" ]; then
                         #   IMAGE_TAG="${env.DOCKER_REGISTRY_URL}/${env.IMAGE_NAME}:${env.BUILD_NUMBER}"
                         #   echo "📥 Pulling image: \$IMAGE_TAG"
                         #   ssh \$SSH_OPTS \$SSH_USER@\$SSH_HOST "
                            #    cd \$DEPLOY_PATH
                            #    docker pull \$IMAGE_TAG || true
                            #    docker tag \$IMAGE_TAG ${env.IMAGE_NAME}:latest || true
                        #    "
                        # fi

                        # Restart services
                        echo "🔄 Restarting services..."
                        ssh \$SSH_OPTS \$SSH_USER@\$SSH_HOST "
                            cd \$DEPLOY_PATH
                            if [ -f docker-compose.yml ]; then
                                # Verify Redis volume exists before stopping (safety check)
                                echo '📦 Checking Redis volume...'
                                docker volume ls | grep redis-data || echo '⚠️  Warning: redis-data volume not found'
                                
                                # Stop containers WITHOUT removing volumes (volumes persist data)
                                echo '🛑 Stopping containers (volumes will be preserved)...'
                                docker-compose down --remove-orphans || true
                                
                                # Pull latest images (for images from registry)
                                echo '📥 Pulling latest images from registry (if any)...'
                                docker-compose pull || true
                                
                                # Rebuild and start services with latest code
                                # This rebuilds the image locally with the code just pulled from GitHub
                                echo '🔨 Rebuilding Docker image with latest code...'
                                echo '🚀 Starting services (will rebuild if needed)...'
                                docker-compose up -d --build
                                
                                # Verify Redis volume still exists
                                echo '✅ Verifying Redis volume after restart...'
                                docker volume ls | grep redis-data && echo '✅ Redis volume preserved' || echo '⚠️  Warning: Redis volume not found'
                                
                                # Wait for Redis to start and check if data exists
                                echo ''
                                echo '⏳ Waiting for Redis to start...'
                                sleep 5
                                
                                # Check if Redis has data
                                KEY_COUNT=\$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
                                echo "📊 Redis keys after restart: \$KEY_COUNT"
                                
                                # If Redis is empty, try to restore from backup
                                if [ "\$KEY_COUNT" -eq "0" ]; then
                                    echo ''
                                    echo '⚠️  WARNING: Redis is empty after restart!'
                                    echo '🔍 Checking for backups to restore...'
                                    
                                    BACKUP_DIR=\${BACKUP_DIR:-/home/jenkins-deploy/redis-backups}
                                    if [ -d "\$BACKUP_DIR" ]; then
                                        LATEST_BACKUP=\$(ls -t "\$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | head -1)
                                        if [ -n "\$LATEST_BACKUP" ] && [ -f "\$LATEST_BACKUP" ]; then
                                            echo "📦 Found latest backup: \$LATEST_BACKUP"
                                            echo "🔄 Attempting to restore from backup..."
                                            
                                            # Check if restore script exists
                                            if [ -f "\$DEPLOY_PATH/scripts/restore_redis.sh" ]; then
                                                bash "\$DEPLOY_PATH/scripts/restore_redis.sh" "\$LATEST_BACKUP" || {
                                                    echo '⚠️  Restore script failed, trying manual restore...'
                                                    # Manual restore: stop Redis, copy backup, restart
                                                    docker-compose stop redis
                                                    sleep 2
                                                    
                                                    REDIS_VOLUME=\$(docker volume ls | grep redis-data | awk '{print \$2}' | head -1)
                                                    if [ -n "\$REDIS_VOLUME" ]; then
                                                        BACKUP_FILE=\$(basename \$LATEST_BACKUP)
                                                        docker run --rm -e BACKUP_FILE=\${BACKUP_FILE} -v "\$REDIS_VOLUME":/data -v "\$BACKUP_DIR":/backup:ro alpine sh -c 'cd /data && rm -rf appendonly.aof appendonlydir dump.rdb && cp /backup/$BACKUP_FILE dump.rdb && chmod 644 dump.rdb && ls -lh dump.rdb'
                                                        echo '✅ Backup copied to Redis volume'
                                                    fi
                                                    
                                                    docker-compose up -d redis
                                                    sleep 5
                                                    
                                                    # Verify restore
                                                    KEY_COUNT_AFTER=\$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
                                                    if [ "\$KEY_COUNT_AFTER" -gt "0" ]; then
                                                        echo "✅ Redis restored! Keys: \$KEY_COUNT_AFTER"
                                                    else
                                                        echo "⚠️  Restore completed but Redis still empty"
                                                    fi
                                                }
                                            else
                                                echo '⚠️  Restore script not found at \$DEPLOY_PATH/scripts/restore_redis.sh'
                                            fi
                                        else
                                            echo '⚠️  No backup files found in \$BACKUP_DIR'
                                        fi
                                    else
                                        echo '⚠️  Backup directory not found: \$BACKUP_DIR'
                                    fi
                                else
                                    echo '✅ Redis has data - no restore needed'
                                fi
                                
                                docker-compose ps
                            else
                                echo '⚠️  docker-compose.yml not found. Skipping restart.'
                            fi
                        "

                        echo "✅ Deployment completed!"
                        """
                    }
                }
            }
        }
    }

    post {
        always {
            script {
                // Only run docker commands if Docker is available
                def dockerAvailable = sh(
                    script: 'command -v docker > /dev/null 2>&1',
                    returnStatus: true
                ) == 0

                if (dockerAvailable) {
                    sh 'docker system prune -f || true'
                }
            }
            deleteDir()
        }
        failure {
            echo 'Pipeline failed. Check the console output for details.'
            echo 'Common issues:'
            echo '1. Python 3.11+ not installed on Jenkins agent'
            echo '2. Docker not installed or not running on Jenkins agent'
            echo '3. Jenkins user does not have permission to use Docker'
        }
    }
}
