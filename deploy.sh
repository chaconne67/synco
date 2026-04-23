#!/bin/bash
set -euo pipefail

DRY_RUN=0
SKIP_TESTS=0
# --company=SLUG 인자 파싱 (현재는 single-tenant, 값 무시하고 "synco" 고정).
# 2번째 회사가 추가될 때 이 스텁을 실구현.
COMPANY="synco"

for arg in "$@"; do
    case "$arg" in
        --dry-run)
            DRY_RUN=1
            ;;
        --skip-tests)
            SKIP_TESTS=1
            ;;
        --company=*)
            COMPANY="${arg#*=}"
            ;;
        *)
            echo "Unknown option: $arg" >&2
            echo "Usage: ./deploy.sh [--dry-run] [--skip-tests] [--company=SLUG]" >&2
            exit 1
            ;;
    esac
done

export SYNCO_COMPANY_SLUG="$COMPANY"
echo ">>> Deploying synco (company=$COMPANY)"

TAG=$(date +%Y%m%d%H%M%S)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="/home/chaconne/synco-deploy"
DEPLOY_APP_DIR="${DEPLOY_ROOT}/synco"
DEPLOY_SRC_DIR="${DEPLOY_APP_DIR}/src"
DEPLOY_TEMPLATE_DIR="${PROJECT_ROOT}/deploy"
DEPLOY_NGINX_DIR="${DEPLOY_ROOT}/nginx"
STACK_TEMPLATE="${DEPLOY_TEMPLATE_DIR}/docker-stack-synco.yml"
STACK_FILE="/tmp/docker-stack-synco-${TAG}.yml"
PROD_ENV_FILE="${DEPLOY_APP_DIR}/.env.prod"
SECRETS_DIR="${DEPLOY_APP_DIR}/.secrets"
CLAUDE_DIR="${DEPLOY_APP_DIR}/.claude"
CLAUDE_JSON="${DEPLOY_APP_DIR}/.claude.json"
RUNTIME_LOG_DIR="${DEPLOY_APP_DIR}/runtime/logs"
APP_IMAGE="synco_app:${TAG}"
NGINX_IMAGE="synco_nginx:${TAG}"
HOSTNAME_CONSTRAINT="$(hostname)"
LOG_FILE="${RUNTIME_LOG_DIR}/deploy.log"

now() {
    date +"%Y-%m-%d %H:%M:%S"
}

log() {
    mkdir -p "$(dirname "${LOG_FILE}")"
    echo "[$(now)] $1" | tee -a "${LOG_FILE}"
}

require_file() {
    local path="$1"
    if [ ! -f "${path}" ]; then
        log "ERROR: Required file not found: ${path}"
        exit 1
    fi
}

clean() {
    rm -f "${STACK_FILE}"
}

sync_source_() {
    log "Sync current source into deploy workspace ..."
    mkdir -p "${DEPLOY_SRC_DIR}"

    rsync -a --delete \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='__pycache__' \
        --exclude='.pytest_cache' \
        --exclude='.ruff_cache' \
        --exclude='node_modules' \
        --exclude='.env' \
        --exclude='.env.*' \
        --exclude='.secrets' \
        --exclude='db.sqlite3' \
        --exclude='staticfiles' \
        --exclude='logs' \
        --exclude='.gstack-audit' \
        "${PROJECT_ROOT}/" "${DEPLOY_SRC_DIR}/"
}

sync_deploy_assets_() {
    log "Sync deploy templates and runtime directories ..."
    mkdir -p "${DEPLOY_NGINX_DIR}" "${SECRETS_DIR}" "${CLAUDE_DIR}" "${RUNTIME_LOG_DIR}"

    cp "${STACK_TEMPLATE}" "${DEPLOY_ROOT}/docker-stack-synco.yml"
    cp "${DEPLOY_TEMPLATE_DIR}/nginx/Dockerfile" "${DEPLOY_NGINX_DIR}/Dockerfile"
    cp "${DEPLOY_TEMPLATE_DIR}/nginx/nginx.conf" "${DEPLOY_NGINX_DIR}/nginx.conf"
}

sync_runtime_secrets_() {
    local legacy_assets_dir="${DEPLOY_SRC_DIR}/assets"
    local local_secrets_dir="${PROJECT_ROOT}/.secrets"

    log "Sync runtime secret files ..."

    if [ -d "${local_secrets_dir}" ]; then
        rsync -a --delete "${local_secrets_dir}/" "${SECRETS_DIR}/"
    fi

    if [ ! -f "${SECRETS_DIR}/client_secret.json" ] && [ -f "${legacy_assets_dir}/client_secret.json" ]; then
        cp "${legacy_assets_dir}/client_secret.json" "${SECRETS_DIR}/client_secret.json"
    fi

    if [ ! -f "${SECRETS_DIR}/google_token.json" ] && [ -f "${legacy_assets_dir}/google_token.json" ]; then
        cp "${legacy_assets_dir}/google_token.json" "${SECRETS_DIR}/google_token.json"
    fi

    find "${CLAUDE_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true

    if [ -f "${HOME}/.claude/.credentials.json" ]; then
        cp "${HOME}/.claude/.credentials.json" "${CLAUDE_DIR}/.credentials.json"
        chmod 600 "${CLAUDE_DIR}/.credentials.json"
    fi

    if [ -f "${HOME}/.claude/settings.json" ]; then
        cp "${HOME}/.claude/settings.json" "${CLAUDE_DIR}/settings.json"
    fi

    if [ -d "${HOME}/.claude/config" ]; then
        rsync -a --delete "${HOME}/.claude/config/" "${CLAUDE_DIR}/config/"
    fi

    if [ -f "${HOME}/.claude.json" ]; then
        cp "${HOME}/.claude.json" "${CLAUDE_JSON}"
    fi

    if [ ! -f "${CLAUDE_JSON}" ]; then
        touch "${CLAUDE_JSON}"
    fi

    chmod 600 "${CLAUDE_JSON}"

    if [ ! -f "${SECRETS_DIR}/client_secret.json" ] || [ ! -f "${SECRETS_DIR}/google_token.json" ]; then
        log "WARNING: Google Drive secret files are missing under ${SECRETS_DIR}"
    fi

    if [ ! -d "${CLAUDE_DIR}" ] || [ ! -f "${CLAUDE_JSON}" ]; then
        log "WARNING: Claude CLI auth files are missing under ${DEPLOY_APP_DIR}"
    fi
}

sync_optional_env_keys_() {
    local source_env="${PROJECT_ROOT}/.env"
    if [ ! -f "${source_env}" ]; then
        return
    fi

    log "Merge optional AI env keys into production env when missing ..."

    python3 - <<PY
from pathlib import Path

source_path = Path("${PROJECT_ROOT}/.env")
target_path = Path("${PROD_ENV_FILE}")
allowed = [
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_MODEL",
    "OPENROUTER_API_KEY",
    "MOONSHOT_API_KEY",
    "MINIMAX_API_KEY",
    "XAI_API_KEY",
    "BRAVE_API_KEY",
    "OPENCODE_API_KEY",
]

def parse_lines(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            rows.append((None, line))
        else:
            key, value = line.split("=", 1)
            rows.append((key, value))
    return rows

source = {key: value for key, value in parse_lines(source_path) if key}
target_rows = parse_lines(target_path)
target_keys = {key for key, _ in target_rows if key}

appended = []
for key in allowed:
    if key in source and key not in target_keys:
        appended.append(f"{key}={source[key]}")

if appended:
    text = target_path.read_text().rstrip() + "\n\n# Synced from ${PROJECT_ROOT}/.env for deploy parity\n" + "\n".join(appended) + "\n"
    target_path.write_text(text)
PY
}

preflight_() {
    log "Run migration drift check ..."
    cd "${PROJECT_ROOT}"
    uv run python manage.py makemigrations --check --dry-run

    if [ "${SKIP_TESTS}" -eq 0 ]; then
        log "Run test suite ..."
        uv run pytest -q --create-db
    else
        log "Skip test suite by request."
    fi
}

git_push_() {
    cd "${PROJECT_ROOT}"

    if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
        log "No uncommitted changes."
    else
        log "Commit uncommitted changes ..."
        git add -A
        git commit -m "deploy: $(date +%Y-%m-%d) release"
    fi

    local branch
    branch="$(git rev-parse --abbrev-ref HEAD)"
    log "Push ${branch} to origin ..."
    git push origin "${branch}"
}

backup_db_() {
    log "Create production DB backup ..."
    ssh -o IdentityFile=~/.ssh/id_ed25519 -o StrictHostKeyChecking=no chaconne@49.247.45.243 \
        "docker exec synco-postgres pg_dump -U synco synco > /mnt/backups/synco_${TAG}.sql" >/dev/null
}

build_images_() {
    log "Build application image ${APP_IMAGE} ..."
    docker build --pull -t "${APP_IMAGE}" -f "${DEPLOY_SRC_DIR}/Dockerfile" "${DEPLOY_SRC_DIR}"

    log "Build nginx image ${NGINX_IMAGE} ..."
    docker build --pull -t "${NGINX_IMAGE}" "${DEPLOY_NGINX_DIR}"
}

validate_release_() {
    log "Run Django deploy check inside release image ..."
    docker run --rm \
        --env-file "${PROD_ENV_FILE}" \
        -v "${SECRETS_DIR}:/app/.secrets:ro" \
        -v "${CLAUDE_DIR}:/root/.claude:ro" \
        -v "${CLAUDE_JSON}:/root/.claude.json:ro" \
        "${APP_IMAGE}" \
        python manage.py check --deploy

    log "Apply database migrations with release image ..."
    docker run --rm \
        --env-file "${PROD_ENV_FILE}" \
        -v "${SECRETS_DIR}:/app/.secrets:ro" \
        -v "${CLAUDE_DIR}:/root/.claude:ro" \
        -v "${CLAUDE_JSON}:/root/.claude.json:ro" \
        "${APP_IMAGE}" \
        python manage.py migrate --noinput
}

plan_release_() {
    log "Run Django deploy check inside release image ..."
    docker run --rm \
        --env-file "${PROD_ENV_FILE}" \
        -v "${SECRETS_DIR}:/app/.secrets:ro" \
        -v "${CLAUDE_DIR}:/root/.claude:ro" \
        -v "${CLAUDE_JSON}:/root/.claude.json:ro" \
        "${APP_IMAGE}" \
        python manage.py check --deploy

    log "Preview migration plan with release image ..."
    docker run --rm \
        --env-file "${PROD_ENV_FILE}" \
        -v "${SECRETS_DIR}:/app/.secrets:ro" \
        -v "${CLAUDE_DIR}:/root/.claude:ro" \
        -v "${CLAUDE_JSON}:/root/.claude.json:ro" \
        "${APP_IMAGE}" \
        python manage.py migrate --plan
}

render_stack_() {
    log "Render stack file ..."
    python3 - <<PY
from pathlib import Path

template = Path("${STACK_TEMPLATE}").read_text()
rendered = (
    template
    .replace("__APP_IMAGE__", "${APP_IMAGE}")
    .replace("__NGINX_IMAGE__", "${NGINX_IMAGE}")
    .replace("node.hostname == moa-svr", "node.hostname == ${HOSTNAME_CONSTRAINT}")
)
Path("${STACK_FILE}").write_text(rendered)
PY
}

wait_for_service_() {
    local service_name="$1"
    local waited=0

    while [ "${waited}" -lt 180 ]; do
        local replicas
        replicas="$(docker service ls --format '{{.Name}} {{.Replicas}}' | awk -v svc="${service_name}" '$1 == svc {print $2}')"
        if [ -n "${replicas}" ]; then
            local running desired
            running="${replicas%%/*}"
            desired="${replicas##*/}"
            if [ "${desired}" != "0" ] && [ "${running}" = "${desired}" ]; then
                log "Service ${service_name} is healthy (${replicas})."
                return 0
            fi
        fi
        sleep 5
        waited=$((waited + 5))
    done

    log "ERROR: Service ${service_name} did not stabilize in time."
    docker service ps "${service_name}" --no-trunc || true
    exit 1
}

cleanup_build_cache_() {
    log "Prune dangling Docker cache ..."
    docker image prune -f >/dev/null || true
    docker builder prune -f >/dev/null || true
}

deploy_stack_() {
    log "Deploy Synco stack ..."
    docker stack deploy -c "${STACK_FILE}" Synco --with-registry-auth --prune

    wait_for_service_ "Synco_synco_app"
    wait_for_service_ "Synco_nginx"
}

main() {
    require_file "${STACK_TEMPLATE}"
    require_file "${DEPLOY_TEMPLATE_DIR}/nginx/Dockerfile"
    require_file "${DEPLOY_TEMPLATE_DIR}/nginx/nginx.conf"
    require_file "${PROD_ENV_FILE}"

    preflight_
    git_push_
    sync_deploy_assets_
    sync_runtime_secrets_
    sync_source_
    sync_optional_env_keys_
    build_images_
    render_stack_

    if [ "${DRY_RUN}" -eq 1 ]; then
        plan_release_
        cleanup_build_cache_
        log "Dry run complete. Stack deploy skipped."
        exit 0
    fi

    backup_db_
    validate_release_
    deploy_stack_
    cleanup_build_cache_
    log "Synco deploy completed successfully."
}

trap clean EXIT INT TERM

main
