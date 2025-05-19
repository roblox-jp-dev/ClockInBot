import asyncio
import os
import discord
from discord.ext import commands
import logging
from typing import Dict, Any, List, Optional
import importlib

# Change from relative imports to absolute imports
from src.config import DISCORD_TOKEN, COMMAND_PREFIX, DEBUG, DB_CONFIG
from src.database.models import Database
from src.utils.logger import setup_logger
from src.utils.i18n import I18n
from src.tasks.scheduler import setup_scheduler
from src.views.attendance_view import handle_start_work_button, handle_end_work_button

# ロガーの設定
logger = setup_logger('bot', DEBUG)

# Botのインテント設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Botの初期化
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# コマンドモジュール一覧
COMMAND_MODULES = [
    'src.commands.setup',
    'src.commands.status',
    'src.commands.today',
    'src.commands.project_list',
    'src.commands.project_setting',
    'src.commands.log',
    'src.commands.export',
    'src.commands.user_add',
    'src.commands.user_remove',
]

@bot.event
async def on_ready():
    """Botの準備完了時に呼び出される"""
    logger.info(f'Bot logged in as {bot.user.name} ({bot.user.id})')
    
    try:
        # データベース接続プールの作成
        await Database.create_pool(DB_CONFIG)
        logger.info("Database connection pool created")
        
        # 言語ファイルの読み込み
        I18n.load_locales()
        logger.info("Locales loaded")
        
        # スケジューラの設定と開始
        scheduler = setup_scheduler(bot)
        scheduler.start()
        logger.info("Scheduler started")
        
        # コマンドの読み込み
        for module in COMMAND_MODULES:
            try:
                await bot.load_extension(module)
                logger.info(f"Loaded extension: {module}")
            except Exception as e:
                logger.error(f"Failed to load extension {module}: {str(e)}")
        
        # スラッシュコマンドの同期
        try:
            synced = await bot.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {str(e)}")
        
        logger.info("Bot is ready!")
    
    except Exception as e:
        logger.critical(f"Failed to initialize bot: {str(e)}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """インタラクション（ボタンクリックなど）の処理"""
    # ボタンクリックの処理
    if interaction.type == discord.InteractionType.component:
        # カスタムIDを取得
        custom_id = interaction.data.get("custom_id", "")
        
        # 勤務開始ボタンの処理
        if custom_id.startswith("start_work_"):
            await handle_start_work_button(interaction)
        
        # 勤務終了ボタンの処理
        elif custom_id.startswith("end_work_"):
            await handle_end_work_button(interaction)
        
        # その他のボタンはdiscord.pyのイベントハンドラで処理

@bot.event
async def on_guild_join(guild: discord.Guild):
    """Botがサーバーに追加された時の処理"""
    logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
    
    # 管理者にDMでセットアップ手順を送信
    try:
        owner = guild.owner
        if owner:
            await owner.send(
                f"{bot.user.name}をサーバー「{guild.name}」に追加していただきありがとうございます。\n"
                f"セットアップを開始するには、サーバー内で `/setup` コマンドを実行してください。"
            )
    except Exception as e:
        logger.error(f"Failed to send welcome DM: {str(e)}")

@bot.event
async def on_command_error(ctx, error):
    """コマンドエラーのハンドリング"""
    if isinstance(error, commands.CommandNotFound):
        return
    
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("このコマンドを実行する権限がありません。")
        return
    
    logger.error(f"Command error: {str(error)}")
    await ctx.send(f"エラーが発生しました: {str(error)}")

@bot.event
async def on_disconnect():
    """Bot切断時の処理"""
    logger.warning("Bot disconnected")

@bot.event
async def on_resumed():
    """Bot再開時の処理"""
    logger.info("Bot resumed")

async def main():
    """メイン関数"""
    # データベースプールが閉じられる前にBotが終了するのを防ぐ
    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        # Bot終了時にデータベース接続を閉じる
        await Database.close_pool()

if __name__ == "__main__":
    asyncio.run(main())