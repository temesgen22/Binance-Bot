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
                    
                    // Check Docker
                    def dockerCheck = sh(
                        script: 'command -v docker || exit 1',
                        returnStatus: true
                    )
                    if (dockerCheck != 0) {
                        error('Docker is not installed. Please install Docker on the Jenkins agent.')
                    }
                    
                    // Verify Docker daemon is running
                    def dockerDaemonCheck = sh(
                        script: 'docker info > /dev/null 2>&1 || exit 1',
                        returnStatus: true
                    )
                    if (dockerDaemonCheck != 0) {
                        error('Docker daemon is not running. Please start Docker service on the Jenkins agent.')
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
                    
                    sh """
                    ${pythonCmd} --version
                    ${pythonCmd} -m venv ${VENV}
                    . ${VENV}/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                    """
                }
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
                . ${VENV}/bin/activate
                pytest tests/ -v
                '''
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

