pipeline {
    agent any

    environment {
        // Try python3 first, fallback to python
        PYTHON = sh(script: 'command -v python3 || command -v python || echo "python3"', returnStdout: true).trim()
        VENV = '.venv'
        IMAGE_NAME = 'binance-bot'
        // Optionally set DOCKER_REGISTRY_URL and DOCKER_REGISTRY_CREDENTIALS_ID in Jenkins
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

See docs/JENKINS_DOCKER_IN_DOCKER.md for detailed instructions.

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
  - See docs/JENKINS_DOCKER_IN_DOCKER.md for complete setup

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
                script {
                    // Detect Python version
                    def pythonCmd = sh(
                        script: 'command -v python3 || command -v python',
                        returnStdout: true
                    ).trim()
                    
                    // Get Python version for package name
                    def pythonVersion = sh(
                        script: "${pythonCmd} --version | cut -d' ' -f2 | cut -d'.' -f1,2",
                        returnStdout: true
                    ).trim()
                    
                    sh """
                    ${pythonCmd} --version
                    # Try to create venv, if it fails, install python3-venv package
                    if ! ${pythonCmd} -m venv ${env.VENV} 2>/dev/null; then
                        echo "python3-venv not available, installing..."
                        # Check if we have root access
                        if [ "\\$(id -u)" = "0" ]; then
                            apt-get update -qq
                            # Try version-specific package first, fallback to generic
                            apt-get install -y python${pythonVersion}-venv 2>/dev/null || apt-get install -y python3-venv
                            # Retry venv creation
                            ${pythonCmd} -m venv ${env.VENV}
                        else
                            echo "⚠️  Not running as root. Cannot install python3-venv automatically."
                            echo "   Please ensure python3-venv is pre-installed in the Jenkins container."
                            echo "   Run: docker exec -u root jenkins apt-get update && apt-get install -y python3-venv"
                            exit 1
                        fi
                    fi
                    . ${env.VENV}/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                    # Install dev dependencies for testing (includes pytest-asyncio)
                    pip install pytest pytest-asyncio
                    """
                }
            }
        }

        stage('Run Tests') {
            steps {
                sh """
                . ${env.VENV}/bin/activate
                pytest tests/ -v
                """
            }
        }

        stage('Build Docker image') {
            steps {
                sh '''
                docker build -t ${IMAGE_NAME}:${BUILD_NUMBER} .
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
                        sh '''
                        echo "${DOCKER_REGISTRY_PSW}" | docker login ${DOCKER_REGISTRY_URL} -u "${DOCKER_REGISTRY_USR}" --password-stdin
                        docker tag ${IMAGE_NAME}:${BUILD_NUMBER} ${DOCKER_REGISTRY_URL}/${IMAGE_NAME}:${BUILD_NUMBER}
                        docker push ${DOCKER_REGISTRY_URL}/${IMAGE_NAME}:${BUILD_NUMBER}
                        '''
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

