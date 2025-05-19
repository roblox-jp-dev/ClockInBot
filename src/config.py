import os
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# Discord Bot設定
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

# データベース設定
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'clockinbot'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
}

# Bot固有設定
DEFAULT_LOCALE = 'ja'
DEFAULT_CHECK_INTERVAL = 1800  # 30分
DEFAULT_TIMEOUT = 3600  # 1時間