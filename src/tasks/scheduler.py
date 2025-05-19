import asyncio
from datetime import datetime, timedelta
import discord
from typing import Dict, Any, List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..database.repository import (
    AttendanceRepository, ProjectRepository, UserRepository, ChannelRepository, GuildRepository
)
from ..views.confirm_view import send_confirmation_request
from ..utils.logger import setup_logger

logger = setup_logger('scheduler')

class AttendanceScheduler:
    """勤怠確認処理のスケジューラ"""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.running = False
    
    def start(self):
        """スケジューラを開始"""
        if self.running:
            return
        
        # 勤怠確認処理を1分ごとに実行
        self.scheduler.add_job(
            self._check_active_sessions,
            IntervalTrigger(minutes=1),
            id='check_active_sessions',
            replace_existing=True
        )
        
        self.scheduler.start()
        self.running = True
        logger.info("Attendance scheduler started")
    
    def stop(self):
        """スケジューラを停止"""
        if not self.running:
            return
        
        self.scheduler.shutdown()
        self.running = False
        logger.info("Attendance scheduler stopped")
    
    async def _check_active_sessions(self):
        """アクティブなセッションを確認し、必要に応じて確認メッセージを送信"""
        try:
            # データベースからアクティブなセッションを取得
            # 実際の実装では全てのアクティブセッションを取得する必要がある
            
            # 以下のようなクエリを実行する形になる
            # SELECT a.*, p.*, g.*, u.*, c.*
            # FROM attendance_sessions a
            # JOIN projects p ON a.project_id = p.id
            # JOIN guild_users u ON a.guild_user_id = u.id
            # JOIN guild_settings g ON u.guild_id = g.guild_id
            # LEFT JOIN channel_mappings c ON u.id = c.guild_user_id
            # WHERE a.end_time IS NULL
            
            # デモ実装のため、ここではダミーデータを使用
            pool = Database.get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT 
                        a.id as session_id, 
                        a.guild_user_id, 
                        a.project_id, 
                        a.start_time,
                        p.require_confirmation,
                        p.check_interval,
                        p.default_timeout,
                        u.user_id,
                        g.locale,
                        c.channel_id
                    FROM attendance_sessions a
                    JOIN projects p ON a.project_id = p.id
                    JOIN guild_users u ON a.guild_user_id = u.id
                    JOIN guild_settings g ON u.guild_id = g.guild_id
                    LEFT JOIN channel_mappings c ON u.id = c.guild_user_id
                    WHERE a.end_time IS NULL
                ''')
                
                for row in rows:
                    session_id = row['session_id']
                    guild_user_id = row['guild_user_id']
                    project_id = row['project_id']
                    start_time = row['start_time']
                    require_confirmation = row['require_confirmation']
                    check_interval = row['check_interval']
                    default_timeout = row['default_timeout']
                    user_id = row['user_id']
                    locale = row['locale']
                    channel_id = row['channel_id']
                    
                    # 現在時刻と開始時刻の差を計算
                    now = datetime.now()
                    elapsed = now - start_time
                    
                    # 確認が必要な場合のみ処理
                    if require_confirmation:
                        # 経過時間がチェック間隔を超えた場合に確認
                        if elapsed.total_seconds() % check_interval < 60:  # 1分以内なら確認
                            # 最後の確認から十分時間が経過しているか確認
                            last_confirmations = await ConfirmationRepository.get_pending_confirmations(session_id)
                            
                            if not last_confirmations:
                                # まだ確認がない場合は確認を送信
                                await send_confirmation_request(
                                    self.bot,
                                    session_id,
                                    user_id,
                                    channel_id,
                                    locale
                                )
                            else:
                                # 最後の確認から一定時間経過した場合、自動終了
                                last_confirmation = last_confirmations[0]
                                time_since_last = now - last_confirmation['prompt_time']
                                
                                if time_since_last.total_seconds() > default_timeout:
                                    # 自動終了処理
                                    await AttendanceRepository.end_session(
                                        session_id,
                                        end_summary="自動終了: 応答なし",
                                        status="auto"
                                    )
                                    
                                    logger.info(f"Auto ended session {session_id} for user {user_id} due to no response")
        
        except Exception as e:
            logger.error(f"Error in check_active_sessions: {str(e)}")

# グローバルインスタンス
scheduler = None

def setup_scheduler(bot: discord.Client):
    """スケジューラをセットアップ"""
    global scheduler
    scheduler = AttendanceScheduler(bot)
    return scheduler