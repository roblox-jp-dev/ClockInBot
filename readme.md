### README.md

# ClockInBot

Discord上で動作する勤怠管理Botです。プロジェクト別の作業時間記録、定期確認機能、レポート出力などの機能を備えています。

## 特徴

- Discord UIのみで完結する勤怠管理
- プロジェクトごとの作業時間記録
- 定期的な作業確認機能
- CSVエクスポート機能
- マルチサーバー対応

## 必要環境

- Python 3.8以上
- PostgreSQL 12以上
- Docker（オプション）

## インストール方法

### Dockerを使用する場合

1. リポジトリをクローン
   ```
   git clone https://github.com/yourusername/clockinbot.git
   cd clockinbot
   ```

2. 環境変数ファイルを設定
   ```
   cp .env.example .env
   # .envファイルを編集し、必要な設定を行う
   ```

3. Dockerコンテナを起動
   ```
   docker-compose up -d
   ```

### 手動インストール

1. リポジトリをクローン
   ```
   git clone https://github.com/yourusername/clockinbot.git
   cd clockinbot
   ```

2. 必要なパッケージをインストール
   ```
   pip install -r requirements.txt
   ```

3. 環境変数を設定
   ```
   cp .env.example .env
   # .envファイルを編集し、必要な設定を行う
   ```

4. PostgreSQLデータベースを準備

5. Botを実行
   ```
   python -m src.bot
   ```

## 使い方

### 初期設定

1. Botをサーバーに招待する
2. サーバー内で `/setup` コマンドを実行し、画面の指示に従う
3. `/user_add` コマンドでユーザーを追加する

### 主なコマンド

- `/setup` - Botの初期設定を行う（管理者のみ）
- `/user_add <ユーザー>` - ユーザーを追加する（管理者のみ）
- `/user_remove <ユーザー>` - ユーザーを削除する（管理者のみ）
- `/project_list` - プロジェクト一覧を表示する
- `/project_setting` - プロジェクトの管理を行う（管理者のみ）
- `/status` - 現在の勤務状況を表示する
- `/today` - 今日の勤務記録を表示する
- `/log [limit] [offset]` - 過去の勤務記録を表示する
- `/export [period]` - 勤務記録をCSVでエクスポートする

## ライセンス

[MITライセンス](LICENSE)

## 作者

そば好き
```