### README.md

# ClockInBot

[注意]まだ開発中です。バグだらけ。
また、近日中にWebダッシュボードを作ります。

Discord上で動作する勤怠管理Bot

## 機能
- 複数サーバー対応。サーバーごとに独立したデータを持ちます。
- ユーザーごとに専用チャンネルが作成され、そこで勤怠記録ができます
- ボタンの押し忘れ防止のため、定期的に勤務中かを確認できる機能・反応がなかった場合に自動で終了する機能をつけています。
- 「プロジェクト」機能により、業務を分類することができます。プロジェクトごとにメンバーを設定できるので、非常に柔軟です。

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

## ライセンス

[MITライセンス](LICENSE)

## 注意
あくまで開発者（そば好き）が自分で使う用に作成したBotをついでに公開しただけのプロジェクトなので、エラーハンドリングやバリデーションチェックなどは最低限になっています。
そのため、フォークして自分なりに改造できる方、問題発生時に対処できる方におすすめです。

また、法務的に、会社の勤怠管理ツールとしては使用できません。趣味用で使う方におすすめです。

## 作者

そば好き