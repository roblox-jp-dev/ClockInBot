### README.md

# ClockInBot

[注意]まだ開発中です。バグだらけ。

Discord上で動作する勤怠管理Bot

## セットアップ

### 1. PostgreSQLの準備

以下のいずれかの方法でPostgreSQLを用意してください：

- ローカルでPostgreSQLサーバーを起動
- クラウドサービス (AWS RDS, Google Cloud SQL, Supabase等) を利用
- Dockerで単体のPostgreSQLを起動: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=password postgres:15`

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、以下を設定：

```env
DISCORD_TOKEN=your_discord_bot_token_here
DATABASE_URL=postgresql://username:password@hostname:port/database_name
```

### 3. Botの起動

```bash
# Dockerで起動
docker build -t clockinbot .
docker run --env-file .env clockinbot

# または直接実行
pip install -r requirements.txt
python -m src.bot
```

### 4. サーバーでの初期設定

1. BotをDiscordサーバーに招待
2. `/setup` コマンドでカテゴリを設定
3. `/user add` コマンドでユーザーを追加

## 環境変数

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `DISCORD_TOKEN` | Discord Bot Token | `MTIzNDU2Nzg5MA...` |
| `DATABASE_URL` | PostgreSQL接続URI | `postgresql://user:pass@host:5432/db` |
| `COMMAND_PREFIX` | コマンドプレフィックス (オプション) | `!` |
| `DEBUG` | デバッグモード (オプション) | `False` |

## ライセンス

[MITライセンス](LICENSE)

## 免責事項


## 作者

そば好き