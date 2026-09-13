#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="docker"
BACKUPS=0
RESTORE=""
DETACHED=0
STOP=0
usage() {
  echo "Nutzung: ./start-all [docker|docker-proxy|local] [-d] [--backups] [--restore DATEI] | --stop"
  echo "  -d, --detach    Docker-Dienste und optional Backups SSH-unabhängig starten"
  echo "  --backups       Backups um Mitternacht und beim geordneten Stoppen"
  echo "  --restore DATEI Sicherung nach interaktiver Bestätigung wiederherstellen"
  echo "  --stop          Mit -d gestarteten Betrieb geordnet beenden"
  echo "  -h, --help      Diese Hilfe anzeigen"
}
while (( $# )); do
  case "$1" in
    docker|docker-proxy|local) MODE="$1" ;;
    --backups) BACKUPS=1 ;;
    -d|--detach) DETACHED=1 ;;
    --stop) STOP=1 ;;
    -h|--help) usage; exit 0 ;;
    --restore)
      if (( $# < 2 )); then echo "--restore benötigt eine Backupdatei."; exit 1; fi
      RESTORE="$2"; shift ;;
    *) usage; exit 1 ;;
  esac
  shift
done
if (( STOP )); then
  if (( DETACHED || BACKUPS || ${#RESTORE} )) || [[ "$MODE" != docker ]]; then
    echo "--stop bitte ohne weitere Optionen verwenden."; exit 1
  fi
  exec python3 "$ROOT_DIR/ops/detached_start.py" --stop
fi
if [[ "$MODE" == local ]] && (( DETACHED )); then
  echo "-d benötigt docker oder docker-proxy; local bleibt ein Entwicklungsmodus."; exit 1
fi
if [[ "$MODE" == local ]] && (( BACKUPS || ${#RESTORE} )); then
  echo "Backups und Wiederherstellung benötigen den Docker-Modus."; exit 1
fi
BACKUP_PID=""
CHILD_PID=""
SHUTTING_DOWN=0
STARTUP_COMPLETE=0

cd "$ROOT_DIR"
# Held across startup and handed to the detached supervisor. Never delete this lock.
mkdir -p .local-state
chmod 700 .local-state
exec 9>.local-state/start-all.lock
if ! flock -n 9; then
  echo "[start-all] Bereits aktiv. Hintergrundbetrieb zuerst mit ./start-all --stop beenden."
  exit 1
fi

shutdown() {
  local exit_code=$?
  if (( SHUTTING_DOWN )); then
    return
  fi
  SHUTTING_DOWN=1
  trap - INT TERM EXIT
  echo
  if [[ -n "$BACKUP_PID" ]]; then
    kill -TERM -- "-$BACKUP_PID" 2>/dev/null || kill -TERM "$BACKUP_PID" 2>/dev/null || true
    wait "$BACKUP_PID" 2>/dev/null || true
  fi
  if (( exit_code != 0 && STARTUP_COMPLETE == 0 )) && [[ "$MODE" == docker || "$MODE" == docker-proxy ]]; then
    echo "[start-all] Start fehlgeschlagen (Exit $exit_code). Container bleiben für die Diagnose erhalten."
    docker compose ps -a || true
    docker compose logs --no-color --tail=100 ntfy ntfy-provisioner vp || true
    local ntfy_id
    ntfy_id="$(docker compose ps -a -q ntfy 2>/dev/null)" || ntfy_id=""
    if [[ -n "$ntfy_id" ]]; then
      echo "[start-all] Letzte ntfy-Healthchecks:"
      docker inspect --format '{{if .State.Health}}{{range .State.Health.Log}}{{.End}} exit={{.ExitCode}} {{.Output}}{{end}}{{else}}Kein Healthcheck vorhanden.{{end}}' "$ntfy_id" || true
    fi
    echo "[start-all] Nach Behebung erneut starten. Manuell beenden: docker compose down"
    exit "$exit_code"
  fi
  if (( BACKUPS && STARTUP_COMPLETE )); then
    echo "[start-all] Erstelle Abschlussbackup vor dem Herunterfahren..."
    if ! python3 "$ROOT_DIR/ops/backup.py"; then
      echo "[start-all] WARNUNG: Abschlussbackup fehlgeschlagen. Vorhandene Sicherungen bleiben erhalten." >&2
      exit_code=1
    fi
  fi
  echo "[start-all] Fahre alle Dienste herunter..."

  if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
    kill -TERM -- "-$CHILD_PID" 2>/dev/null || kill -TERM "$CHILD_PID" 2>/dev/null || true
    wait "$CHILD_PID" 2>/dev/null || true
  fi

  case "$MODE" in
    docker)
      docker compose down || true
      ;;
    docker-proxy)
      docker compose --profile proxy down || true
      ;;
  esac

  echo "[start-all] Alle Dienste wurden beendet."
  exit "$exit_code"
}

# Configure retention before touching containers or installing shutdown traps.
if [[ "$MODE" == docker || "$MODE" == docker-proxy ]]; then
  python3 "$ROOT_DIR/ops/configure_journal.py" --ensure --env-file "$ROOT_DIR/.env"
fi

if [[ -n "$RESTORE" ]]; then
  python3 "$ROOT_DIR/ops/restore.py" "$RESTORE"
fi

trap shutdown INT TERM EXIT

# Preserve attachments from older containers before Compose recreates them.
# Copy only missing files; never replace files already persisted on the host.
preserve_uploads() {
  local app_id staging
  app_id="$(docker compose ps -a -q app)"
  mkdir -p "$ROOT_DIR/uploads"
  if [[ -n "$app_id" ]]; then
    staging="$(mktemp -d)"
    if docker cp "$app_id:/app/uploads/." "$staging/"; then
      cp -an "$staging/." "$ROOT_DIR/uploads/"
    else
      echo "[start-all] Upload-Sicherung fehlgeschlagen. Start abgebrochen, alter Container bleibt erhalten."
      return 1
    fi
    rm -rf -- "$staging"
  fi
}

finish_docker_start() {
  if (( DETACHED )); then
    local options=()
    if (( BACKUPS )); then options+=(--backups); fi
    python3 "$ROOT_DIR/ops/detached_start.py" --launch --mode "$MODE" "${options[@]}"
    # The supervisor owns shutdown and backups from here on.
    trap - INT TERM EXIT
    local compose_options=()
    if [[ "$MODE" == docker-proxy ]]; then compose_options+=(--profile proxy); fi
    docker compose "${compose_options[@]}" logs --tail=100 || true
    echo "[start-all] Läuft im Hintergrund. Die SSH-Verbindung kann geschlossen werden."
    echo "[start-all] Logs: docker compose ${compose_options[*]} logs -f --tail=100"
    echo "[start-all] Beenden (inkl. Abschlussbackup bei --backups): ./start-all --stop"
    exit 0
  fi
  if (( BACKUPS )); then
    setsid python3 "$ROOT_DIR/ops/backup.py" --loop &
    BACKUP_PID=$!
  fi
  STARTUP_COMPLETE=1
}

case "$MODE" in
  docker)
    echo "[start-all] Starte Stack ohne Proxy (localhost-Testing)..."
    preserve_uploads
    docker compose up -d --build
    bash ./sync-ntfy-users.sh
    finish_docker_start
    docker compose logs -f
    ;;
  docker-proxy)
    echo "[start-all] Starte Stack inkl. Caddy-Proxy-Profil..."
    export NTFY_BEHIND_PROXY=true
    preserve_uploads
    docker compose --profile proxy up -d --build
    bash ./sync-ntfy-users.sh
    finish_docker_start
    docker compose --profile proxy logs -f
    ;;
  local)
    echo "[start-all] Starte lokal (Python VP + Node Kalender)..."
    setsid npm run dev:all &
    CHILD_PID=$!
    wait "$CHILD_PID"
    ;;
  *)
    echo "Nutzung: ./start-all.sh [docker|docker-proxy|local]"
    exit 1
    ;;
esac
