#!/usr/bin/env bash
# Purpose: Provision an EC2 Ubuntu host to run the "Aegis" Discord bot as a service.
# Usage: sudo bash bootstrap-aegis.sh
set -Eeuo pipefail

# ======= Configurable bits =======
BOT_UNIX_USER="aegis"
APP_DIR="/home/${BOT_UNIX_USER}/app"
SERVICE_NAME="aegis-bot"
PYBIN="${APP_DIR}/.venv/bin/python"
REPO_URL="https://github.com/your-username/aegis-discord-bot.git"  # TODO: set your repo URL
BOT_ENTRY="bot.py"
USE_UFW=false  # set to true to enable a simple local firewall
# =================================

log() { echo -e "[Aegis bootstrap] $*"; }

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Please run as root (sudo bash bootstrap-aegis.sh)."
    exit 1
  fi
}

install_base() {
  log "Updating apt and installing base packages..."
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
  apt-get install -y git python3-venv python3-pip
}

create_user_and_dirs() {
  if ! id -u "${BOT_UNIX_USER}" >/dev/null 2>&1; then
    log "Creating user ${BOT_UNIX_USER}..."
    useradd -m -s /bin/bash "${BOT_UNIX_USER}"
  else
    log "User ${BOT_UNIX_USER} already exists."
  fi

  log "Creating app dir ${APP_DIR}..."
  mkdir -p "${APP_DIR}"
  chown -R "${BOT_UNIX_USER}:${BOT_UNIX_USER}" "${APP_DIR}"
}

fetch_app_code() {
  if [[ -n "${REPO_URL}" ]]; then
    log "Cloning bot repo: ${REPO_URL}"
    sudo -u "${BOT_UNIX_USER}" -H bash -lc "cd '${APP_DIR}' && git clone '${REPO_URL}' ."
  else
    log "No REPO_URL set. You can upload your files later to ${APP_DIR} (bot.py, etc.)."
  fi
}

setup_python_venv() {
  log "Creating Python venv and installing deps..."
  sudo -u "${BOT_UNIX_USER}" -H bash -lc "cd '${APP_DIR}' && python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip"
  if [[ -f "${APP_DIR}/requirements.txt" ]]; then
    sudo -u "${BOT_UNIX_USER}" -H bash -lc "cd '${APP_DIR}' && source .venv/bin/activate && pip install -r requirements.txt"
  else
    sudo -u "${BOT_UNIX_USER}" -H bash -lc "cd '${APP_DIR}' && source .venv/bin/activate && pip install discord.py python-dotenv"
  fi
}

write_env_skeleton() {
  if [[ ! -f "${APP_DIR}/.env" ]]; then
    log "Creating .env placeholder..."
    cat > "${APP_DIR}/.env" <<'ENV'
DISCORD_TOKEN=REPLACE_ME
# Optional: uncomment to speed up command sync to one server during testing
# GUILD_ID=123456789012345678
ENV
    chown "${BOT_UNIX_USER}:${BOT_UNIX_USER}" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
  else
    log ".env already exists; leaving as-is."
  fi
}

write_systemd_unit() {
  log "Writing systemd unit ${SERVICE_NAME}.service ..."
  cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=Aegis (STFC) Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
User=${BOT_UNIX_USER}
Group=${BOT_UNIX_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${PYBIN} ${APP_DIR}/${BOT_ENTRY}
Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=10
LimitNOFILE=65535

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=${APP_DIR}

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
}

enable_firewall_if_requested() {
  if [[ "${USE_UFW}" == "true" ]]; then
    log "Enabling uncomplicated firewall (UFW) for SSH only..."
    apt-get install -y ufw
    ufw allow OpenSSH
    yes | ufw enable || true
  else
    log "Skipping UFW (set USE_UFW=true to enable)."
  fi
}

start_service() {
  if [[ ! -f "${APP_DIR}/${BOT_ENTRY}" ]]; then
    log "WARNING: ${APP_DIR}/${BOT_ENTRY} not found. Start will likely fail."
    log "Upload your bot files to ${APP_DIR} and then run: systemctl restart ${SERVICE_NAME}"
  fi

  log "Enabling and starting ${SERVICE_NAME}..."
  systemctl enable "${SERVICE_NAME}"
  systemctl start "${SERVICE_NAME}"
  sleep 2
  systemctl --no-pager --full status "${SERVICE_NAME}" || true
  log "Tail logs with: journalctl -u ${SERVICE_NAME} -f"
}

main() {
  require_root
  install_base
  create_user_and_dirs
  fetch_app_code
  setup_python_venv
  write_env_skeleton
  write_systemd_unit
  enable_firewall_if_requested
  start_service

  log "Done. Next steps:"
  cat <<'NEXT'
1) Edit your token in /home/aegis/app/.env  (DISCORD_TOKEN=...)
2) If you didn't clone a repo, upload bot.py (and any files) to /home/aegis/app
3) Restart the service: sudo systemctl restart aegis-bot
4) Watch logs: sudo journalctl -u aegis-bot -f
NEXT
}

main "$@"
