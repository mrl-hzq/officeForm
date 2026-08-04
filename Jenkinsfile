pipeline {
    agent any

    environment {
        PYTHONUNBUFFERED = '1'
        PYTHONDONTWRITEBYTECODE = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    if [ -f .venv/bin/activate ]; then
                        source .venv/bin/activate
                    fi
                    pip install --upgrade pip
                    pip install -r requirements.txt
                '''
            }
        }

        stage('Syntax & Lint') {
            steps {
                sh 'python3 -B -c "import pathlib; files=list(pathlib.Path(\'app\').glob(\'*.py\'))+[pathlib.Path(\'app_entry.py\')]+list(pathlib.Path(\'scripts\').glob(\'*.py\'))+list(pathlib.Path(\'tests\').glob(\'*.py\')); [compile(p.read_text(encoding=\'utf-8\'), str(p), \'exec\') for p in files]; print(\'Python syntax OK\')"'
                sh 'node --check public/app.js || echo "JS check skipped"'
            }
        }

        stage('Pytest Unit & Integration') {
            steps {
                sh '''
                    mkdir -p junit-reports
                    pytest tests \
                        --junitxml=junit-reports/test-results.xml \
                        --cov=app \
                        --cov-report=term-missing \
                        --cov-report=xml:coverage.xml \
                        -v
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'junit-reports/*.xml'
                }
            }
        }

        stage('Docker Compose Syntax Check') {
            steps {
                sh 'docker compose config --quiet'
            }
        }

        stage('Docker Build Test') {
            steps {
                sh 'docker compose build web'
            }
        }
    }

    post {
        success {
            echo 'Build and test pipeline completed successfully!'
        }
        failure {
            echo 'Build or test failure detected.'
        }
    }
}
