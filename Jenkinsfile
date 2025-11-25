pipeline {
    agent any

    environment {
        PYTHON = 'python3'
        VENV = '.venv'
        IMAGE_NAME = 'binance-bot'
        // Optionally set DOCKER_REGISTRY_URL and DOCKER_REGISTRY_CREDENTIALS_ID in Jenkins
    }

    options {
        ansiColor('xterm')
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Set up Python environment') {
            steps {
                sh '''
                ${PYTHON} -m venv ${VENV}
                . ${VENV}/bin/activate
                pip install --upgrade pip
                pip install -r requirements.txt
                '''
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
            sh 'docker system prune -f || true'
            deleteDir()
        }
    }
}

