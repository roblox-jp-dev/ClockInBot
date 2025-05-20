import asyncio
from datetime import datetime, timedelta, timezone
import discord
from typing import Dict, Any, List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..database.repository import (
    AttendanceRepository, ProjectRepository, UserRepository, ChannelRepository, GuildRepository,
    ConfirmationRepository
)
from ..database.models import Database
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
                    WHERE a.end_time IS NULL AND p.require_confirmation = true
                ''')
                
                for row in rows:
                    await self._process_session(row)
        
        except Exception as e:
            logger.error(f"Error in check_active_sessions: {str(e)}")
    
    async def _process_session(self, session_data: Dict[str, Any]):
        """個別セッションの確認処理"""
        session_id = session_data['session_id']
        start_time = session_data['start_time']
        check_interval = session_data['check_interval']
        default_timeout = session_data['default_timeout']
        user_id = session_data['user_id']
        locale = session_data['locale']
        channel_id = session_data['channel_id']
        
        # 現在時刻を取得（UTCで統一）
        now = datetime.now(timezone.utc)
        
        # start_timeがnaiveな場合はUTCとして扱う
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        
        # 経過時間を計算
        elapsed_seconds = (now - start_time).total_seconds()
        
        # 未応答の確認を取得
        pending_confirmations = await ConfirmationRepository.get_pending_confirmations(session_id)
        
        # 未応答の確認がある場合、自動終了をチェック
        if pending_confirmations:
            await self._check_timeout(session_id, pending_confirmations, default_timeout, now)
            return
        
        # 次回確認タイミングを計算
        next_confirmation_time = await self._calculate_next_confirmation_time(
            session_id, start_time, check_interval, now
        )
        
        # 確認送信が必要かチェック
        if now >= next_confirmation_time:
            await self._send_confirmation(session_id, user_id, channel_id, locale)
    
    async def _calculate_next_confirmation_time(
        self, 
        session_id: int, 
        start_time: datetime, 
        check_interval: int, 
        now: datetime
    ) -> datetime:
        """次回確認時刻を計算"""
        
        # セッションの全ての確認を取得
        all_confirmations = await ConfirmationRepository.get_session_confirmations(session_id)
        
        if not all_confirmations:
            # まだ確認がない場合、開始時間からcheck_interval後が最初の確認時刻
            return start_time + timedelta(seconds=check_interval)
        
        # 応答済みの確認のうち最新のものを取得
        responded_confirmations = [c for c in all_confirmations if c['responded']]
        
        if responded_confirmations:
            # 最後に応答した確認の応答時間を基準にする
            latest_response = max(responded_confirmations, key=lambda x: x['response_time'])
            last_response_time = latest_response['response_time']
            
            # response_timeがnaiveな場合はUTCとして扱う
            if last_response_time.tzinfo is None:
                last_response_time = last_response_time.replace(tzinfo=timezone.utc)
            
            # 最後の応答時間からcheck_interval後が次回確認時刻
            return last_response_time + timedelta(seconds=check_interval)
        else:
            # 未応答の確認がある場合、最初の確認からcheck_interval後
            # （ただし、この関数が呼ばれる時点では未応答確認は処理済みのはず）
            first_confirmation = min(all_confirmations, key=lambda x: x['prompt_time'])
            prompt_time = first_confirmation['prompt_time']
            
            if prompt_time.tzinfo is None:
                prompt_time = prompt_time.replace(tzinfo=timezone.utc)
            
            return prompt_time + timedelta(seconds=check_interval)
    
    async def _check_timeout(
        self, 
        session_id: int, 
        pending_confirmations: List[Dict[str, Any]], 
        default_timeout: int, 
        now: datetime
    ):
        """未応答確認のタイムアウトをチェック"""
        
        for confirmation in pending_confirmations:
            prompt_time = confirmation['prompt_time']
            
            # prompt_timeがnaiveな場合はUTCとして扱う
            if prompt_time.tzinfo is None:
                prompt_time = prompt_time.replace(tzinfo=timezone.utc)
            
            time_since_prompt = (now - prompt_time).total_seconds()
            
            # タイムアウトチェック
            if time_since_prompt > default_timeout:
                # 自動終了処理
                await AttendanceRepository.end_session(
                    session_id,
                    end_summary="自動終了: 応答なし",
                    status="auto"
                )
                
                logger.info(f"Auto ended session {session_id} due to no response (timeout: {default_timeout}s)")
                return
    
    async def _send_confirmation(
        self, 
        session_id: int, 
        user_id: int, 
        channel_id: int, 
        locale: str
    ):
        """確認リクエストを送信"""
        
        try:
            # 確認リクエストを送信
            confirmation = await send_confirmation_request(
                self.bot,
                session_id,
                user_id,
                channel_id,
                locale
            )
            
            if confirmation:
                logger.info(f"Sent confirmation request for session {session_id}")
            else:
                logger.warning(f"Failed to send confirmation request for session {session_id}")
        
        except Exception as e:
            logger.error(f"Error sending confirmation for session {session_id}: {str(e)}")

# グローバルインスタンス
scheduler = None

def setup_scheduler(bot: discord.Client):
    """スケジューラをセットアップ"""
    global scheduler
    scheduler = AttendanceScheduler(bot)
    return scheduler