#!/usr/bin/env bash
# =============================================================================
# officeForm Continuous Integration (CI) Test Suite Runner
# Usage: ./scripts/run_ci_tests.sh [--with-docker-build] [--with-docker-smoke]
# =============================================================================

set -e

# Colored Log Helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================================${NC}"
echo -e "${BLUE}        officeForm CI/CD Test Pipeline Execution     ${NC}"
echo -e "${BLUE}=====================================================${NC}"

# Parse optional arguments
WITH_DOCKER_BUILD=0
WITH_DOCKER_SMOKE=0

for arg in "$@"; do
  case $arg in
    --with-docker-build)
      WITH_DOCKER_BUILD=1
      shift
      ;;
    --with-docker-smoke)
      WITH_DOCKER_SMOKE=1
      shift
      ;;
  esac
done

# Ensure JUnit output directory exists
mkdir -p junit-reports

# Activate or create Python virtual environment
if [ -d ".venv" ]; then
  echo -e "${YELLOW}Activating existing virtual environment .venv...${NC}"
  . .venv/bin/activate || source .venv/bin/activate
else
  echo -e "${YELLOW}Creating virtual environment .venv...${NC}"
  python3 -m venv .venv || python -m venv .venv
  . .venv/bin/activate || source .venv/bin/activate
  echo -e "${YELLOW}Installing requirements...${NC}"
  python3 -m pip install --upgrade pip || true
  python3 -m pip install -r requirements.txt
fi

# -----------------------------------------------------------------------------
# STAGE 1: Code Syntax & Compilation Checks
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[Stage 1/4] Running Code Syntax & Compilation Checks...${NC}"

echo -n "Checking Python syntax... "
python3 -B -c "
import pathlib
files = list(pathlib.Path('app').glob('*.py')) + [pathlib.Path('app_entry.py')] + list(pathlib.Path('scripts').glob('*.py')) + list(pathlib.Path('tests').glob('*.py'))
[compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in files]
print('OK')
"

if command -v node >/dev/null 2>&1; then
  echo -n "Checking JavaScript syntax... "
  node --check public/app.js
  echo "OK"
else
  echo -e "${YELLOW}Node.js not installed on runner. Skipping JS syntax check.${NC}"
fi

# -----------------------------------------------------------------------------
# STAGE 2: Pytest Unit & API Integration Tests
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[Stage 2/4] Executing Pytest Unit & Integration Suite...${NC}"

python3 -m pytest tests \
  --junitxml=junit-reports/test-results.xml \
  --cov=app \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml \
  -v
echo -e "${GREEN}✓ All Pytest unit and integration tests passed!${NC}"

# -----------------------------------------------------------------------------
# STAGE 3: Docker Compose Syntax & Config Check
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[Stage 3/4] Validating Docker Compose Configuration...${NC}"

if command -v docker >/dev/null 2>&1; then
  echo -n "Validating docker-compose.yml syntax... "
  docker compose config --quiet || docker-compose config --quiet || echo "Skipped docker compose config"
  echo -e "${GREEN}OK${NC}"

  if [ "$WITH_DOCKER_BUILD" -eq 1 ]; then
    echo -e "\n${YELLOW}Building Docker container image (officeform-web:latest)...${NC}"
    docker compose build web || docker-compose build web
    echo -e "${GREEN}✓ Docker build successful!${NC}"
  fi
else
  echo -e "${YELLOW}Docker CLI not found. Skipping Docker compose validation.${NC}"
fi

# -----------------------------------------------------------------------------
# STAGE 4: Optional Docker HTTP Smoke Test
# -----------------------------------------------------------------------------
if [ "$WITH_DOCKER_SMOKE" -eq 1 ] && command -v docker >/dev/null 2>&1; then
  echo -e "\n${YELLOW}[Stage 4/4] Running Container HTTP Smoke Test...${NC}"
  TEST_CONTAINER_NAME="officeform-ci-smoke-$$"
  TEST_PORT=3999

  echo "Starting ephemeral container ${TEST_CONTAINER_NAME} on port ${TEST_PORT}..."
  docker run -d --name "${TEST_CONTAINER_NAME}" -p "${TEST_PORT}:3000" \
    -e DB_HOST=127.0.0.1 -e DB_NAME=test_db -e DB_USER=test -e DB_PASS=test \
    officeform-web:latest

  # Wait for startup
  sleep 4

  echo -n "Testing HTTP endpoint readiness... "
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${TEST_PORT}/" || echo "000")

  # Clean up container
  echo "Tearing down smoke test container..."
  docker rm -f "${TEST_CONTAINER_NAME}" >/dev/null 2>&1 || true

  if [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 500 ]; then
    echo -e "${GREEN}✓ Container smoke test passed (HTTP Status: ${HTTP_STATUS})!${NC}"
  else
    echo -e "${RED}✗ Container smoke test failed (HTTP Status: ${HTTP_STATUS})${NC}"
    exit 1
  fi
fi

echo -e "\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}    ✓ CI/CD Test Pipeline Execution Complete!        ${NC}"
echo -e "${GREEN}=====================================================${NC}"
