#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/deadline-discord-bot}"
SERVICE_NAME="${SERVICE_NAME:-deadline-discord-bot}"

if [ ! -f "$APP_DIR/bot.py" ]; then
  echo "bot.py が見つかりません: $APP_DIR"
  echo "先に git clone してから実行してください。"
  exit 1
fi

if [ ! -f "$APP_DIR/.env" ]; then
  echo ".env が見つかりません。"
  echo "先に $APP_DIR/.env に DISCORD_TOKEN を設定してください。"
  exit 1
fi

sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

cd "$APP_DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

sudo tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null <<EOF
[Unit]
Description=Discord deadline reminder bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "セットアップ完了。状態確認:"
sudo systemctl status "$SERVICE_NAME" --no-pager
