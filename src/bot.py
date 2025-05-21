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
        
        # 固定メッセージのViewを復元
        await restore_attendance_views()
        
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
async def on_message(message: discord.Message):
    """メッセージが送信された時の処理"""
    # Bot以外のメッセージは無視
    if message.author != bot.user:
        return
    
    # DMは無視
    if not message.guild:
        return
    
    # 勤怠管理チャンネルかどうかを確認して固定メッセージを更新
    await handle_attendance_channel_message(message)
    
    # コマンド処理を継続
    await bot.process_commands(message)

async def handle_attendance_channel_message(message: discord.Message):
    """勤怠管理チャンネルでのBot自身のメッセージ処理"""
    from src.database.repository import ChannelRepository, GuildRepository
    from src.views.attendance_view import refresh_attendance_message
    
    try:
        # チャンネルが勤怠管理チャンネルかどうかを確認
        channel_mapping = await ChannelRepository.get_by_channel_id(message.channel.id)
        if not channel_mapping:
            return
        
        # 送信されたメッセージが現在の固定メッセージと同じかチェック（無限ループ回避）
        if message.id == channel_mapping["pinned_message_id"]:
            return
        
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(message.guild.id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # 固定メッセージを最新位置に移動
        await refresh_attendance_message(
            channel=message.channel,
            old_message_id=channel_mapping["pinned_message_id"],
            guild_user_id=channel_mapping["guild_user_id"],
            locale=locale
        )
        
    except Exception as e:
        logger.error(f"Error handling attendance channel message: {str(e)}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """インタラクション（ボタンクリックなど）の処理"""
    if interaction.type == discord.InteractionType.component:
        await handle_component_interaction(interaction)

async def handle_component_interaction(interaction: discord.Interaction):
    """コンポーネント（ボタン、セレクトメニュー）のインタラクション処理"""
    from src.views.attendance_view import handle_attendance_interaction
    from src.views.confirm_view import handle_confirmation_interaction
    
    custom_id = interaction.data.get('custom_id', '')
    
    # 勤怠管理関連のインタラクション
    if custom_id.startswith('start_work_') or custom_id.startswith('end_work_') or custom_id.startswith('select_project_'):
        await handle_attendance_interaction(interaction)
    
    # 確認関連のインタラクション
    elif custom_id in ['confirm', 'ignore']:
        await handle_confirmation_interaction(interaction)

async def restore_attendance_views():
    """Bot再起動時に固定メッセージのViewを復元"""
    from src.database.repository import ChannelRepository, GuildRepository
    from src.views.attendance_view import restore_attendance_message
    
    try:
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            # 全てのチャンネルマッピングを取得
            rows = await conn.fetch('''
                SELECT cm.*, gs.locale
                FROM channel_mappings cm
                JOIN guild_users gu ON cm.guild_user_id = gu.id
                JOIN guild_settings gs ON gu.guild_id = gs.guild_id
            ''')
            
            for row in rows:
                try:
                    channel = bot.get_channel(row['channel_id'])
                    if channel:
                        await restore_attendance_message(
                            channel=channel,
                            message_id=row['pinned_message_id'],
                            guild_user_id=row['guild_user_id'],
                            locale=row['locale']
                        )
                        logger.info(f"Restored attendance view for channel {channel.name}")
                except Exception as e:
                    logger.error(f"Failed to restore view for channel {row['channel_id']}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error restoring attendance views: {str(e)}")

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