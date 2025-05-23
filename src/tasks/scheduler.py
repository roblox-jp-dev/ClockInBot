# src/tasks/scheduler.py
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
        self._processing_sessions = set()  # 処理中のセッションIDを記録
        self._check_lock = asyncio.Lock()  # 全体的な排他制御
    
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
        # 排他制御で重複実行を防ぐ
        async with self._check_lock:
            try:
                pool = Database.get_pool()
                async with pool.acquire() as conn:
                    rows = await conn.fetch('''
                        SELECT 
                            a.id as session_id, 
                            a.guild_user_id, 
                            a.project_id, 
                            a.start_time,
                            a.start_message_id,
                            a.end_time,
                            p.require_confirmation,
                            p.check_interval,
                            p.default_timeout,
                            u.user_id,
                            u.guild_id,
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
                        session_id = row['session_id']
                        
                        # 既に処理中のセッションはスキップ
                        if session_id in self._processing_sessions:
                            continue
                        
                        # セッションが既に終了していないか再確認
                        if row['end_time'] is not None:
                            continue
                        
                        # 処理中としてマーク
                        self._processing_sessions.add(session_id)
                        
                        try:
                            # セッション処理
                            await self._process_session(row)
                        finally:
                            # 処理完了後にマークを削除
                            self._processing_sessions.discard(session_id)
            
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
        
        try:
            # 処理開始時にセッションがまだアクティブか再確認
            current_session = await AttendanceRepository.get_session(session_id)
            if not current_session or current_session.get('end_time') is not None:
                logger.info(f"Session {session_id} already ended, skipping")
                return
            
            # 現在時刻を取得（UTCで統一）
            now = datetime.now(timezone.utc)
            
            # start_timeがnaiveな場合はUTCとして扱う
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            
            # 未応答の確認を取得
            pending_confirmations = await ConfirmationRepository.get_pending_confirmations(session_id)
            
            # 未応答の確認がある場合、自動終了をチェック（優先処理）
            if pending_confirmations:
                session_ended = await self._check_timeout(session_id, pending_confirmations, default_timeout, now, session_data)
                if session_ended:
                    logger.info(f"Session {session_id} auto-ended due to timeout")
                    return  # セッション終了済み
                
                # まだタイムアウトしていない場合は、新しい確認は送信しない
                logger.debug(f"Session {session_id} has pending confirmations, not sending new confirmation")
                return
            
            # セッションがまだアクティブか最終確認
            current_session = await AttendanceRepository.get_session(session_id)
            if not current_session or current_session.get('end_time') is not None:
                logger.info(f"Session {session_id} ended during processing, skipping")
                return
            
            # 次回確認タイミングを計算
            next_confirmation_time = await self._calculate_next_confirmation_time(
                session_id, start_time, check_interval, now
            )
            
            # 確認送信が必要かチェック
            if now >= next_confirmation_time:
                # 確認送信前に最終的なセッション状態チェック
                final_session = await AttendanceRepository.get_session(session_id)
                if final_session and final_session.get('end_time') is None:
                    logger.info(f"Sending confirmation for session {session_id}")
                    await self._send_confirmation(session_id, user_id, channel_id, locale)
                else:
                    logger.info(f"Session {session_id} ended before confirmation could be sent")
            else:
                logger.debug(f"Not time to send confirmation for session {session_id} yet. Next: {next_confirmation_time}, Now: {now}")
        
        except Exception as e:
            logger.error(f"Error processing session {session_id}: {str(e)}")
    
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
            next_time = start_time + timedelta(seconds=check_interval)
            logger.debug(f"No confirmations yet. Next confirmation time: {next_time}")
            return next_time
        
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
            next_time = last_response_time + timedelta(seconds=check_interval)
            logger.debug(f"Last response at {last_response_time}. Next confirmation time: {next_time}")
            return next_time
        else:
            # 未応答の確認のみある場合、最初の確認からcheck_interval後
            first_confirmation = min(all_confirmations, key=lambda x: x['prompt_time'])
            prompt_time = first_confirmation['prompt_time']
            
            if prompt_time.tzinfo is None:
                prompt_time = prompt_time.replace(tzinfo=timezone.utc)
            
            next_time = prompt_time + timedelta(seconds=check_interval)
            logger.debug(f"Only unresponded confirmations. First prompt at {prompt_time}. Next confirmation time: {next_time}")
            return next_time
    
    async def _check_timeout(
        self, 
        session_id: int, 
        pending_confirmations: List[Dict[str, Any]], 
        default_timeout: int, 
        now: datetime,
        session_data: Dict[str, Any]
    ) -> bool:
        """未応答確認のタイムアウトをチェック
        
        Returns:
            bool: セッションが自動終了された場合はTrue、まだ継続中の場合はFalse
        """
        
        for confirmation in pending_confirmations:
            prompt_time = confirmation['prompt_time']
            
            # prompt_timeがnaiveな場合はUTCとして扱う
            if prompt_time.tzinfo is None:
                prompt_time = prompt_time.replace(tzinfo=timezone.utc)
            
            time_since_prompt = (now - prompt_time).total_seconds()
            
            logger.debug(f"Checking timeout for confirmation {confirmation['id']}: {time_since_prompt}s since prompt (timeout: {default_timeout}s)")
            
            # タイムアウトチェック
            if time_since_prompt >= default_timeout:
                logger.info(f"Timeout detected! Auto-ending session {session_id}")
                
                # 自動終了前に最終的なセッション状態チェック
                current_session = await AttendanceRepository.get_session(session_id)
                if not current_session or current_session.get('end_time') is not None:
                    logger.info(f"Session {session_id} already ended, skipping auto-end")
                    return True
                
                # 自動終了処理（DB更新）
                updated_session = await AttendanceRepository.end_session(
                    session_id,
                    end_summary="自動終了: 応答なし",
                    status="auto"
                )
                
                if updated_session:
                    # UI更新処理を実行
                    await self._update_ui_for_auto_end(session_data, updated_session)
                    logger.info(f"Auto ended session {session_id} due to no response (timeout: {default_timeout}s)")
                else:
                    logger.warning(f"Failed to auto-end session {session_id}")
                
                return True  # セッションが終了したことを通知
        
        return False  # まだタイムアウトしていない
    
    async def _update_ui_for_auto_end(self, session_data: Dict[str, Any], updated_session: Dict[str, Any]):
        """自動終了時のUI更新処理"""
        try:
            channel_id = session_data['channel_id']
            guild_user_id = session_data['guild_user_id']
            locale = session_data['locale']
            start_message_id = session_data.get('start_message_id')
            
            if not channel_id:
                return
            
            # チャンネルを取得
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            # 1. 勤怠状況の固定メッセージを更新
            channel_mapping = await ChannelRepository.get_channel_mapping(guild_user_id)
            if channel_mapping:
                await self._update_attendance_status_message(
                    channel, 
                    channel_mapping["pinned_message_id"], 
                    guild_user_id, 
                    locale
                )
            
            # 2. 勤務開始メッセージを完了メッセージに更新
            if start_message_id:
                await self._update_start_message_to_auto_completion(
                    channel,
                    start_message_id,
                    updated_session,
                    session_data,
                    locale
                )
            
            # 3. 未回答の確認メッセージを削除
            await self._cleanup_pending_confirmation_messages(session_data['session_id'], channel)
            
        except Exception as e:
            logger.error(f"Error updating UI for auto end: {str(e)}")
    
    async def _update_attendance_status_message(
        self, 
        channel: discord.TextChannel, 
        message_id: int, 
        guild_user_id: int, 
        locale: str
    ):
        """勤怠状況の固定メッセージを更新"""
        try:
            from ..views.attendance_view import update_attendance_message
            await update_attendance_message(channel, message_id, guild_user_id, locale)
        except Exception as e:
            logger.error(f"Error updating attendance status message: {str(e)}")
    
    async def _update_start_message_to_auto_completion(
        self,
        channel: discord.TextChannel,
        start_message_id: int,
        session: Dict[str, Any],
        session_data: Dict[str, Any],
        locale: str
    ):
        """勤務開始メッセージを自動終了完了メッセージに更新"""
        try:
            # プロジェクト情報を取得
            project = await ProjectRepository.get_project(session["project_id"])
            
            # 勤務時間を計算
            duration = session["end_time"] - session["start_time"]
            hours, remainder = divmod(int(duration.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = f"{hours:02}:{minutes:02}:{seconds:02}"
            
            # 自動完了のEmbedを作成
            embed = await self._create_auto_completion_embed(session, project, duration_str, locale)
            
            # メッセージを取得して更新（既存のコメントEmbedsは保持）
            try:
                start_message = await channel.fetch_message(start_message_id)
                
                # 既存のコメントEmbedsを保持
                existing_embeds = start_message.embeds.copy()
                
                # 最初のEmbedを自動完了Embedに置き換え
                if existing_embeds:
                    existing_embeds[0] = embed
                else:
                    existing_embeds = [embed]
                
                await start_message.edit(embeds=existing_embeds)
            except discord.NotFound:
                # メッセージが見つからない場合は何もしない
                pass
                
        except Exception as e:
            logger.error(f"Error updating start message to auto completion: {str(e)}")
    
    async def _create_auto_completion_embed(
        self,
        session: Dict[str, Any],
        project: Optional[Dict[str, Any]],
        duration_str: str,
        locale: str = "ja"
    ) -> discord.Embed:
        """自動終了完了Embedを作成"""
        
        embed = discord.Embed(
            title="⚠️ 自動終了",
            description="応答がないため自動的に勤務を終了しました",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # プロジェクト名
        project_name = project["name"] if project else "Unknown"
        embed.add_field(
            name="📋 プロジェクト",
            value=project_name,
            inline=True
        )
        
        # 勤務時間
        embed.add_field(
            name="⏱️ 勤務時間",
            value=duration_str,
            inline=True
        )
        
        # 勤務期間（開始時間と終了時間）
        start_time = session["start_time"]
        end_time = session["end_time"]
        
        start_timestamp = int(start_time.timestamp())
        end_timestamp = int(end_time.timestamp())
        
        embed.add_field(
            name="📅 勤務期間",
            value=f"<t:{start_timestamp}:t> ～ <t:{end_timestamp}:t>",
            inline=False
        )
        
        # 終了理由
        embed.add_field(
            name="📝 終了理由",
            value=session.get("end_summary", "自動終了: 応答なし"),
            inline=False
        )
        
        return embed
    
    async def _cleanup_pending_confirmation_messages(self, session_id: int, channel: discord.TextChannel):
        """未回答の確認メッセージを削除"""
        try:
            # 未回答の確認を取得
            pending_confirmations = await ConfirmationRepository.get_pending_confirmations(session_id)
            
            # 各確認メッセージを削除
            for confirmation in pending_confirmations:
                message_id = confirmation.get('message_id')
                if message_id:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.delete()
                        logger.info(f"Deleted pending confirmation message {message_id} for session {session_id}")
                    except discord.NotFound:
                        # メッセージが既に削除されている場合は無視
                        logger.debug(f"Confirmation message {message_id} already deleted")
                    except discord.Forbidden:
                        # 削除権限がない場合
                        logger.warning(f"No permission to delete confirmation message {message_id}")
                    except Exception as e:
                        logger.error(f"Error deleting confirmation message {message_id}: {str(e)}")
                else:
                    logger.debug(f"No message_id recorded for confirmation {confirmation['id']}")
                    
        except Exception as e:
            logger.error(f"Error cleaning up confirmation messages: {str(e)}")
    
    async def _send_confirmation(
        self, 
        session_id: int, 
        user_id: int, 
        channel_id: int, 
        locale: str
    ):
        """確認リクエストを送信"""
        
        try:
            # 送信前に最終的なセッション状態チェック
            session = await AttendanceRepository.get_session(session_id)
            if not session or session.get('end_time') is not None:
                logger.info(f"Session {session_id} ended before confirmation could be sent")
                return
            
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