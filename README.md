# Deadline Discord Bot

課題やテストの期限を、Discordのフォームとボタンで登録できるBotです。

## できること

- `/add` で課題・テストをフォーム登録
- 通知タイミングを選択
- `/list` で一覧表示
- `/done` で完了
- `/delete` で削除
- 期限前にDiscordへ自動通知

## 1. Discord Botを作る

1. https://discord.com/developers/applications を開く
2. `New Application` を押す
3. 好きな名前を入れる
4. 左メニューの `Bot` を開く
5. `Reset Token` または `View Token` でTokenをコピーする

TokenはBotのパスワードです。人に見せないでください。

## 2. Botをサーバーに招待する

1. Developer Portalで左メニューの `OAuth2` を開く
2. `URL Generator` を開く
3. `SCOPES` で以下を選ぶ
   - `bot`
   - `applications.commands`
4. `BOT PERMISSIONS` で以下を選ぶ
   - `Send Messages`
   - `Use Slash Commands`
   - `Embed Links`
5. 下に出たURLを開いて、自分のDiscordサーバーに招待する

## 3. ローカルで動かす

```bash
cd ~/Documents/deadline-discord-bot
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

初回だけ `.env` を作ります。

```bash
cp .env.example .env
open -e .env
```

`.env` の中をこうします。

```env
DISCORD_TOKEN=コピーしたBotのToken
```

ターミナルに以下のように出れば成功です。

```text
Bot名 としてログインしました
```

## 4. Discordで使う

Discordで以下を入力します。

```text
/add
```

フォームに入力して、通知タイミングを選んで、登録します。

使えるコマンド:

```text
/add
/list
/done
/delete
```

期限は以下の形式で入力できます。

```text
2026-07-10 23:59
2026/07/10 23:59
07/10 23:59
```

## 5. PCを閉じても動かす

PCを閉じても動かすには、Renderなどのクラウドに置きます。

### GitHubに上げる

GitHubで `deadline-discord-bot` というリポジトリを作ってから、以下を実行します。

```bash
cd ~/Documents/deadline-discord-bot
git init
git add bot.py requirements.txt .gitignore .env.example render.yaml README.md
git commit -m "Initial Discord deadline bot"
git branch -M main
git remote add origin https://github.com/あなたの名前/deadline-discord-bot.git
git push -u origin main
```

### Renderに置く

1. https://dashboard.render.com を開く
2. `New +` を押す
3. `Blueprint` を選ぶ
4. GitHubの `deadline-discord-bot` を選ぶ
5. 作成する
6. RenderのEnvironmentに以下を追加する

```text
DISCORD_TOKEN = Discord BotのToken
```

`render.yaml` により、BotはBackground Workerとして起動します。
SQLiteの保存先は `/var/data/deadlines.db` です。

## 6. Oracle Cloud Always Freeで動かす

Oracle Cloudの無料VMを使う場合は、UbuntuのVMを作ってSSH接続したあと、以下を実行します。

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/aketi2718/deadline-discord-bot.git
cd deadline-discord-bot
cp .env.example .env
nano .env
```

`.env` にBot Tokenを入れます。

```env
DISCORD_TOKEN=Discord BotのToken
```

保存したら、セットアップします。

```bash
bash scripts/setup_oracle_ubuntu.sh
```

ログを見るには:

```bash
sudo journalctl -u deadline-discord-bot -f
```

止めるには:

```bash
sudo systemctl stop deadline-discord-bot
```

再起動するには:

```bash
sudo systemctl restart deadline-discord-bot
```

## よくあるエラー

### `/add` が出てこない

Botを再起動して数分待ってください。

```bash
control + C
python bot.py
```

### `.env に DISCORD_TOKEN を設定してください` と出る

`.env` がないか、Tokenが入っていません。

```bash
cp .env.example .env
open -e .env
```

### `ModuleNotFoundError` と出る

必要なライブラリが入っていません。

```bash
source .venv/bin/activate
pip install -r requirements.txt
```
