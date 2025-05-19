import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logger(name: str, debug: bool = False) -> logging.Logger:
    """アプリケーション用のロガーをセットアップする"""
    
    # ログディレクトリの作成
    os.makedirs('logs', exist_ok=True)
    
    # ロガーの設定
    logger = logging.getLogger(name)
    
    # ログレベルの設定
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # ハンドラーが既に設定されていたら追加しない
    if logger.handlers:
        return logger
    
    # ファイルハンドラーの設定
    file_handler = RotatingFileHandler(
        'logs/bot.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(file_handler)
    
    # コンソールハンドラーの設定
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(console_handler)
    
    return logger