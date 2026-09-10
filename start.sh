#!/usr/bin/env bash
#
# start.sh — launch the MahaVistaar ingestion pipeline locally.
#
#   ./start.sh                 # backend API + ingestion worker + frontend
#   ./start.sh --backend-only  # API + worker only
#   ./start.sh --frontend-only # Next.js console only
#   ./start.sh --no-worker     # API + frontend, no ingestion worker
#   ./start.sh --install       # force dependency reinstall (pip + npm)
#   ./start.sh --migrate       # run `alembic upgrade head` before starting
#   ./start.sh --quiet         # log to files only, do not stream to the terminal
#   ./start.sh --no-reclaim    # leave a previous run alone, fail instead
#   ./start.sh --help
#
# Every line each service prints is streamed here as
#   HH:MM:SS api      Application startup complete.
# with one colour per service, and written without colour to logs/<service>.log.
# Ctrl+C stops every process this script started.
#
# Each run first stops the services left behind by the previous one, so the
# console always talks to the code that is on disk right now.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

VENV_DIR="$ROOT_DIR/.venv"
LOG_DIR="$ROOT_DIR/logs"

RUN_BACKEND=1
RUN_WORKER=1
RUN_FRONTEND=1
FORCE_INSTALL=0
RUN_MIGRATIONS=0
STREAM_LOGS=1
RECLAIM_PORTS=1

# ---------------------------------------------------------------- output utils
if [ -t 1 ]; then
  C_RESET=$'\033[0m'; C_BLUE=$'\033[34m'; C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_DIM=$'\033[2m'
  C_CYAN=$'\033[36m'; C_MAGENTA=$'\033[35m'
else
  C_RESET=""; C_BLUE=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_DIM=""
  C_CYAN=""; C_MAGENTA=""
fi
info()  { printf '%s==>%s %s\n' "$C_BLUE"   "$C_RESET" "$*"; }
ok()    { printf '%s  ok%s %s\n' "$C_GREEN"  "$C_RESET" "$*"; }
warn()  { printf '%s warn%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
err()   { printf '%s fail%s %s\n' "$C_RED"    "$C_RESET" "$*" >&2; }
dim()   { printf '%s      %s%s\n' "$C_DIM" "$*" "$C_RESET"; }

usage() { awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "${BASH_SOURCE[0]}"; }

# ---------------------------------------------------------------- parse args
while [ $# -gt 0 ]; do
  case "$1" in
    --backend-only)  RUN_FRONTEND=0 ;;
    --frontend-only) RUN_BACKEND=0; RUN_WORKER=0 ;;
    --no-worker)     RUN_WORKER=0 ;;
    --install)       FORCE_INSTALL=1 ;;
    --migrate)       RUN_MIGRATIONS=1 ;;
    --quiet)         STREAM_LOGS=0 ;;
    --no-reclaim)    RECLAIM_PORTS=0 ;;
    -h|--help)       usage; exit 0 ;;
    *) err "unknown option: $1"; usage; exit 1 ;;
  esac
  shift
done

# ---------------------------------------------------------------- environment
if [ ! -f "$ROOT_DIR/.env" ]; then
  err ".env not found at $ROOT_DIR/.env — the backend and frontend both read it."
  exit 1
fi

# Export .env for the backend; the frontend loads the same file via next.config.ts.
# macOS ships bash 3.2, where `source <(...)` silently sets nothing — use a temp file.
ENV_TMP="$(mktemp -t mahavistaar-env)"
trap 'rm -f "$ENV_TMP"' EXIT
tr -d '\r' <"$ROOT_DIR/.env" \
  | grep -E '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=' \
  | sed -E 's/^[[:space:]]*(export[[:space:]]+)?//' >"$ENV_TMP"
# A variable already set in the shell wins, mirroring frontend/next.config.ts.
while IFS= read -r __line; do
  __key="${__line%%=*}"
  __val="${__line#*=}"
  __val="$(printf '%s' "$__val" | sed -E "s/^[\"']//; s/[\"']$//")"
  eval "__seen=\${$__key+set}"
  [ -n "${__seen:-}" ] && continue
  export "$__key=$__val"
done <"$ENV_TMP"
unset __line __key __val __seen
rm -f "$ENV_TMP"
trap - EXIT

# The Next.js dev server proxies /api to NEXT_PUBLIC_API_PROXY_TARGET, so the API
# must listen on that port for the console to reach it. Override with API_PORT=…
PROXY_TARGET="${NEXT_PUBLIC_API_PROXY_TARGET:-http://localhost:8002}"
PROXY_PORT="$(printf '%s' "$PROXY_TARGET" | sed -nE 's#.*:([0-9]+)/?$#\1#p')"
API_PORT="${API_PORT:-${PROXY_PORT:-${API_HOST_PORT:-8002}}}"
UI_PORT="${UI_PORT:-${UI_HOST_PORT:-3000}}"

# Local PostgreSQL runs as a Docker container; named here so the preflight
# failure message can tell you exactly how to bring it back.
PG_CONTAINER="${PG_CONTAINER:-mahavistaar-postgres}"
PG_VOLUME="${PG_VOLUME:-mahavistaar-ingestion-pipeline_backend-db-data}"

if [ -n "${API_HOST_PORT:-}" ] && [ "$API_HOST_PORT" != "$API_PORT" ]; then
  warn "API_HOST_PORT=$API_HOST_PORT in .env, but the UI proxies to port $API_PORT — using $API_PORT."
fi

mkdir -p "$LOG_DIR"

# Our log formatter reads each service through a pipe, and Python block-buffers
# stdout when it is not a terminal — without this the worker would look silent.
export PYTHONUNBUFFERED=1

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
port_pids() { lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' '; }
pid_command() { ps -ww -o command= -p "$1" 2>/dev/null; }
pid_cwd() { lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1; }

# A port holder counts as ours only when it is a process this repo started:
# either its working directory is this checkout, or it runs one of our modules.
pid_is_ours() {
  local pid="$1" cwd cmd
  cwd="$(pid_cwd "$pid")"
  case "$cwd" in "$ROOT_DIR"|"$ROOT_DIR"/*) return 0 ;; esac
  cmd="$(pid_command "$pid")"
  case "$cmd" in
    *backend.app.main*|*backend.worker*) return 0 ;;
    *"$ROOT_DIR"*) return 0 ;;
  esac
  return 1
}

# Free `port`, but only by stopping leftovers from a previous run of this
# script. Anything else on the port is reported and left alone.
reclaim_port() {
  local port="$1" label="$2" override="$3" pid mine="" others="" waited
  port_busy "$port" || return 0

  for pid in $(port_pids "$port"); do
    if [ "$RECLAIM_PORTS" = 1 ] && pid_is_ours "$pid"; then
      mine="$mine $pid"
    else
      others="$others $pid"
    fi
  done

  if [ -n "$others" ]; then
    err "Port $port ($label) is in use by a process this script did not start:"
    for pid in $others; do
      err "  pid $pid  $(pid_command "$pid" | cut -c1-100)"
    done
    err "Stop it, or re-run with $override=<free port>."
    return 1
  fi

  for pid in $mine; do
    warn "Port $port held by a leftover $label from an earlier run (pid $pid) — stopping it"
    kill -TERM "$pid" 2>/dev/null || true
  done

  waited=0
  while [ "$waited" -lt 20 ]; do
    port_busy "$port" || { ok "Port $port released"; return 0; }
    sleep 0.5
    waited=$((waited + 1))
  done

  for pid in $mine; do kill -KILL "$pid" 2>/dev/null || true; done
  sleep 1
  if port_busy "$port"; then
    err "Port $port ($label) is still busy after stopping pid$mine."
    return 1
  fi
  ok "Port $port released"
}

# ------------------------------------------------------- stop a previous run
# Ports only reveal listeners. The ingestion worker binds nothing at all, so a
# leftover one survives every port check and quietly competes for jobs, and a
# Next dev server that has lost its socket still owns .next/dev/lock and makes
# the next one refuse to start. Both are invisible to reclaim_port, so before
# launching anything we stop every process from this checkout that runs one of
# the services this invocation is responsible for.
self_ancestors() {
  local pid=$$ depth=0 parent
  while [ "${pid:-0}" -gt 1 ] && [ "$depth" -lt 40 ]; do
    printf '%s ' "$pid"
    parent="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    [ -n "$parent" ] || break
    pid="$parent"
    depth=$((depth + 1))
  done
}

stale_pattern() {
  local pat=""
  if [ "$RUN_BACKEND"  = 1 ]; then pat="$pat|backend[.]app[.]main"; fi
  if [ "$RUN_WORKER"   = 1 ]; then pat="$pat|backend[.]worker"; fi
  if [ "$RUN_FRONTEND" = 1 ]; then pat="$pat|next-server|next dev|npm run dev|[.]bin/next"; fi
  printf '%s' "${pat#|}"
}

stop_previous_run() {
  local pattern snapshot skip pid cwd stale="" alive="" waited=0

  if [ "$RECLAIM_PORTS" != 1 ]; then
    warn "--no-reclaim: leaving any previous run in place"
    return 0
  fi

  pattern="$(stale_pattern)"
  [ -n "$pattern" ] || return 0

  # Snapshot first: matching against a live `ps` would match the matcher, whose
  # own command line necessarily contains the patterns we are searching for.
  snapshot="$(ps -axo pid=,command= 2>/dev/null || true)"
  skip=" $(self_ancestors) "

  for pid in $(printf '%s\n' "$snapshot" | awk -v re="$pattern" '$0 ~ re { print $1 }'); do
    case "$skip" in *" $pid "*) continue ;; esac
    # The working directory anchors the match to this checkout, so another
    # project's dev server and another repo's worker are left running.
    cwd="$(pid_cwd "$pid")"
    case "$cwd" in "$ROOT_DIR"|"$ROOT_DIR"/*) stale="$stale $pid" ;; esac
  done

  if [ -z "$stale" ]; then
    ok "No services left over from an earlier run"
  else
    for pid in $stale; do
      warn "Stopping leftover pid $pid — $(pid_command "$pid" | cut -c1-70)"
      kill -TERM "$pid" 2>/dev/null || true
    done
    while [ "$waited" -lt 16 ]; do
      alive=""
      for pid in $stale; do
        if kill -0 "$pid" 2>/dev/null; then alive="$alive $pid"; fi
      done
      [ -n "$alive" ] || break
      sleep 0.5
      waited=$((waited + 1))
    done
    if [ -n "$alive" ]; then
      for pid in $alive; do kill -KILL "$pid" 2>/dev/null || true; done
      sleep 1
    fi
    ok "Previous run stopped"
  fi

  # Next records the dev server it believes is serving this directory. A stale
  # entry is enough for `next dev` to bail out with "Another next dev server is
  # already running", even when nothing is listening.
  if [ "$RUN_FRONTEND" = 1 ]; then
    rm -f "$ROOT_DIR/frontend/.next/dev/lock" 2>/dev/null || true
  fi
}

# ---------------------------------------------------------------- dependencies
if [ "$RUN_BACKEND" = 1 ] || [ "$RUN_WORKER" = 1 ]; then
  PYTHON_BIN="${PYTHON_BIN:-python3}"
  command -v "$PYTHON_BIN" >/dev/null 2>&1 || { err "python3 not found on PATH"; exit 1; }

  if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtualenv at .venv ($("$PYTHON_BIN" --version 2>&1))"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    FORCE_INSTALL=1
  fi
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"

  if [ "$FORCE_INSTALL" = 1 ] || ! python -c 'import fastapi, uvicorn, sqlalchemy, greenlet' >/dev/null 2>&1; then
    info "Installing backend dependencies (backend/requirements.txt)"
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r backend/requirements.txt
    ok "Backend dependencies installed"
  else
    ok "Backend dependencies present"
  fi
fi

if [ "$RUN_FRONTEND" = 1 ]; then
  command -v npm >/dev/null 2>&1 || { err "npm not found on PATH"; exit 1; }
  if [ "$FORCE_INSTALL" = 1 ] || [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
    info "Installing frontend dependencies (npm install)"
    (cd "$ROOT_DIR/frontend" && npm install --no-fund --no-audit)
    ok "Frontend dependencies installed"
  else
    ok "Frontend dependencies present"
  fi
fi

# ---------------------------------------------------------------- preflight
info "Checking backing services"

# A bare /dev/tcp connect waits for the OS timeout, which is over a minute for a
# host that silently drops packets — long enough to look like a hung script.
# Run the connect in a child and give up on it after TCP_TIMEOUT seconds.
tcp_open() { # host port seconds
  local host="$1" port="$2" seconds="$3" pid waited=0
  ( exec 3<>"/dev/tcp/$host/$port" ) 2>/dev/null &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$waited" -ge "$((seconds * 10))" ]; then
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 1
    fi
    sleep 0.1
    waited=$((waited + 1))
  done
  wait "$pid" 2>/dev/null
}

check_tcp() { # host port label required
  local host="$1" port="$2" label="$3" required="$4"
  if tcp_open "$host" "$port" "${TCP_TIMEOUT:-3}"; then
    ok "$label reachable on $host:$port"
  elif [ "$required" = required ]; then
    err "$label NOT reachable on $host:$port — the backend cannot start without it."
    return 1
  else
    warn "$label not reachable on $host:$port — related features will fail."
  fi
}

PREFLIGHT_FAILED=0
if [ "$RUN_BACKEND" = 1 ] || [ "$RUN_WORKER" = 1 ]; then
  check_tcp "${POSTGRES_HOST:-localhost}" "${POSTGRES_PORT:-5432}" "PostgreSQL" required || PREFLIGHT_FAILED=1
  check_tcp "$(printf '%s' "${QDRANT_URL:-http://localhost:6333}" | sed -E 's#https?://([^:/]+).*#\1#')" \
            "$(printf '%s' "${QDRANT_URL:-http://localhost:6333}" | sed -nE 's#.*:([0-9]+).*#\1#p')" \
            "Qdrant" optional || true
  check_tcp "$(printf '%s' "${MINIO_ENDPOINT:-localhost:9000}" | cut -d: -f1)" \
            "$(printf '%s' "${MINIO_ENDPOINT:-localhost:9000}" | cut -d: -f2)" \
            "MinIO" optional || true
fi
if [ "${NEXT_PUBLIC_AUTH_ENABLED:-false}" = "true" ] || [ "${AUTH_DISABLED:-true}" = "false" ]; then
  check_tcp localhost "${KEYCLOAK_HOST_PORT:-8181}" "Keycloak" optional || true
fi

if [ "$PREFLIGHT_FAILED" = 1 ]; then
  err "Start PostgreSQL (${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}, db ${POSTGRES_DB:-docs-pipeline}) and re-run."
  # The local database runs as a Docker container created from the .env
  # credentials. If it was removed, this recreates it; if it is merely
  # stopped, `docker start` is enough.
  if docker inspect "$PG_CONTAINER" >/dev/null 2>&1; then
    err "  The container exists but is not running:  docker start $PG_CONTAINER"
  else
    err "  Recreate the container:"
    err "    docker run -d --name $PG_CONTAINER --restart unless-stopped \\"
    err "      -p 127.0.0.1:${POSTGRES_PORT:-5432}:5432 \\"
    err "      -v ${PG_VOLUME}:/var/lib/postgresql/data \\"
    err "      -e POSTGRES_USER=\"\$POSTGRES_USER\" -e POSTGRES_PASSWORD=\"\$POSTGRES_PASSWORD\" \\"
    err "      -e POSTGRES_DB=\"\$POSTGRES_DB\" postgres:17"
  fi
  exit 1
fi

# ---------------------------------------------------------------- migrations
if [ "$RUN_MIGRATIONS" = 1 ]; then
  info "Applying Alembic migrations"
  alembic -c "$ROOT_DIR/alembic.ini" upgrade head 2>/dev/null \
    || alembic -c "$ROOT_DIR/backend/alembic.ini" upgrade head
  ok "Migrations applied"
fi

# ---------------------------------------------------------------- process mgmt
PIDS=()
NAMES=()

cleanup() {
  trap - INT TERM EXIT
  echo
  info "Shutting down"
  local i
  [ "${#PIDS[@]}" -eq 0 ] && { ok "Nothing to stop"; return; }
  for i in "${!PIDS[@]}"; do
    if kill -0 "${PIDS[$i]}" 2>/dev/null; then
      kill -TERM "-${PIDS[$i]}" 2>/dev/null || kill -TERM "${PIDS[$i]}" 2>/dev/null || true
      dim "stopped ${NAMES[$i]} (pid ${PIDS[$i]})"
    fi
  done
  wait 2>/dev/null || true
  ok "All processes stopped"
}
trap cleanup INT TERM EXIT

# Reads a service's combined stdout/stderr and stamps every line with the time
# and the service label: coloured on the terminal, plain in logs/<service>.log.
# Perl does this in one long-lived process; the shell fallback forks `date` per
# line, which is slower but keeps the script working without perl.
if command -v perl >/dev/null 2>&1; then
  log_stream() { # label colour logfile stream
    perl -e '
      my ($label, $colour, $reset, $logfile, $stream) = @ARGV;
      open(my $fh, ">>", $logfile) or die "cannot write $logfile: $!\n";
      select((select($fh), $| = 1)[0]);
      $| = 1;
      while (defined(my $line = <STDIN>)) {
        $line =~ s/\r?\n\z//;
        my @t = localtime;
        my $ts = sprintf("%02d:%02d:%02d", $t[2], $t[1], $t[0]);
        print $fh "$ts $label $line\n";
        print "$colour$ts $label$reset $line\n" if $stream;
      }
    ' "$1" "$2" "$C_RESET" "$3" "$4"
  }
else
  log_stream() { # label colour logfile stream
    local label="$1" colour="$2" logfile="$3" stream="$4" line ts
    while IFS= read -r line; do
      ts="$(date +%H:%M:%S)"
      printf '%s %s %s\n' "$ts" "$label" "$line" >>"$logfile"
      [ "$stream" = 1 ] && printf '%s%s %s%s %s\n' "$colour" "$ts" "$label" "$C_RESET" "$line"
    done
  }
fi

launch() { # name label colour logfile command...
  local name="$1" label="$2" colour="$3" logfile="$4"; shift 4
  local padded; padded="$(printf '%-8s' "$label")"
  : >"$logfile"
  set -m
  "$@" > >(log_stream "$padded" "$colour" "$logfile" "$STREAM_LOGS") 2>&1 &
  local pid=$!
  set +m
  PIDS+=("$pid"); NAMES+=("$name")
  ok "$name started (pid $pid) → ${logfile#$ROOT_DIR/}"
}

# ---------------------------------------------------------------- start
info "Stopping anything left from the previous run"
stop_previous_run

info "Starting services"

if [ "$RUN_BACKEND" = 1 ]; then
  reclaim_port "$API_PORT" "backend API" API_PORT || exit 1
  launch "backend API" "api" "$C_CYAN" "$LOG_DIR/backend.log" \
    python -u -m uvicorn backend.app.main:app --host 0.0.0.0 --port "$API_PORT" --reload
fi

if [ "$RUN_WORKER" = 1 ]; then
  launch "ingestion worker" "worker" "$C_MAGENTA" "$LOG_DIR/worker.log" python -u -m backend.worker
fi

if [ "$RUN_FRONTEND" = 1 ]; then
  reclaim_port "$UI_PORT" "frontend console" UI_PORT || exit 1
  launch "frontend console" "frontend" "$C_BLUE" "$LOG_DIR/frontend.log" \
    npm --prefix "$ROOT_DIR/frontend" run dev -- --port "$UI_PORT"
fi

# ---------------------------------------------------------------- wait & report
if [ "$RUN_BACKEND" = 1 ]; then
  info "Waiting for the API to become healthy"
  for _ in $(seq 1 40); do
    if curl -fsS "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
      ok "API healthy at http://localhost:$API_PORT/health"
      break
    fi
    kill -0 "${PIDS[0]}" 2>/dev/null || {
      err "Backend exited early — see logs/backend.log"
      [ "$STREAM_LOGS" = 1 ] || tail -n 30 "$LOG_DIR/backend.log"
      exit 1
    }
    sleep 1
  done
fi

DEAD=0
for i in "${!PIDS[@]}"; do
  if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
    err "${NAMES[$i]} exited during startup — see logs/"
    DEAD=1
  fi
done
echo
if [ "$DEAD" = 1 ]; then
  printf '%sMahaVistaar is running (degraded — see the failures above)%s\n' "$C_YELLOW" "$C_RESET"
else
  printf '%sMahaVistaar is running%s\n' "$C_GREEN" "$C_RESET"
fi
[ "$RUN_FRONTEND" = 1 ] && dim "Operator console   http://localhost:$UI_PORT"
[ "$RUN_BACKEND"  = 1 ] && dim "API                http://localhost:$API_PORT"
[ "$RUN_BACKEND"  = 1 ] && dim "Swagger UI         http://localhost:$API_PORT/docs"
if [ "$STREAM_LOGS" = 1 ]; then
  dim "Logs               streaming below, also in logs/{backend,worker,frontend}.log"
else
  dim "Logs               tail -f logs/*.log"
fi
dim "Stop               Ctrl+C"
echo

wait
