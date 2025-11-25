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
                        SSH_OPTS="-i \$SSH_KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p \$SSH_PORT"
                        
                        # Create deployment directory
                        ssh \$SSH_OPTS \$SSH_USER@\$SSH_HOST "mkdir -p \$DEPLOY_PATH"
                        
                        # Copy docker-compose file
                        if [ -f "\$COMPOSE_FILE" ]; then
                            echo "📦 Copying docker-compose file..."
                            scp \$SSH_OPTS -P \$SSH_PORT "\$COMPOSE_FILE" \$SSH_USER@\$SSH_HOST:\$DEPLOY_PATH/
                        fi
                        
                        # Copy .env.example if .env doesn't exist
                        if [ -f ".env.example" ]; then
                            ssh \$SSH_OPTS \$SSH_USER@\$SSH_HOST "
                                if [ ! -f \$DEPLOY_PATH/.env ]; then
                                    echo '📝 Creating .env from .env.example...'
                                    cp \$DEPLOY_PATH/.env.example \$DEPLOY_PATH/.env 2>/dev/null || true
                                fi
                            "
                        fi
                        
                        # Pull latest image and restart
                        if [ -n "${env.DOCKER_REGISTRY_URL?.trim()}" ]; then
                            IMAGE_TAG="${env.DOCKER_REGISTRY_URL}/${env.IMAGE_NAME}:${env.BUILD_NUMBER}"
                            echo "📥 Pulling image: \$IMAGE_TAG"
                            ssh \$SSH_OPTS \$SSH_USER@\$SSH_HOST "
                                cd \$DEPLOY_PATH
                                docker pull \$IMAGE_TAG || true
                                docker tag \$IMAGE_TAG ${env.IMAGE_NAME}:latest || true
                            "
                        fi
                        
                        # Restart services
                        echo "🔄 Restarting services..."
                        ssh \$SSH_OPTS \$SSH_USER@\$SSH_HOST "
                            cd \$DEPLOY_PATH
                            if [ -f docker-compose.yml ]; then
                                docker-compose down || true
                                docker-compose pull || true
                                docker-compose up -d
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
