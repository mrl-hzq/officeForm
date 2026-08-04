pipeline {
    agent any

    environment {
        DOCKER_IMAGE = "officeform-test:${BUILD_NUMBER}"
    }

    stages {
        stage('Build Test Container Image') {
            steps {
                echo "Building Docker container image ${DOCKER_IMAGE}..."
                sh 'docker build -t ${DOCKER_IMAGE} .'
            }
        }

        stage('Run Pytest inside Isolated Container') {
            steps {
                echo "Executing 30 Pytest unit & integration tests inside container..."
                sh '''
                    mkdir -p junit-reports
                    docker run --rm \
                        -v $(pwd)/junit-reports:/app/junit-reports \
                        ${DOCKER_IMAGE} \
                        pytest tests \
                            --junitxml=junit-reports/test-results.xml \
                            --cov=app \
                            --cov-report=term-missing \
                            --cov-report=xml:junit-reports/coverage.xml \
                            -v
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'junit-reports/*.xml'
                }
            }
        }

        stage('Container Startup Smoke Test') {
            steps {
                echo "Testing container HTTP readiness..."
                sh '''
                    TEST_CONTAINER="officeform-smoke-${BUILD_NUMBER}"
                    docker run -d --name ${TEST_CONTAINER} -p 3999:3000 ${DOCKER_IMAGE}
                    sleep 3
                    docker exec ${TEST_CONTAINER} python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:3000/').getcode())"
                    docker rm -f ${TEST_CONTAINER} || true
                '''
            }
        }
    }

    post {
        always {
            echo "Cleaning up build image ${DOCKER_IMAGE}..."
            sh 'docker rmi ${DOCKER_IMAGE} || true'
        }
        success {
            echo '✓ Containerized build and test pipeline completed successfully!'
        }
        failure {
            echo '✗ Containerized build or test failure detected.'
        }
    }
}
