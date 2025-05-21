from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Union
import asyncpg
from .models import Database

class GuildRepository:
    """サーバー設定に関するデータベース操作"""
    
    @staticmethod
    async def get_guild_settings(guild_id: int) -> Optional[Dict[str, Any]]:
        """サーバー設定を取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM guild_settings WHERE guild_id = $1',
                guild_id
            )
            return dict(row) if row else None
    
    @staticmethod
    async def create_guild_settings(guild_id: int, category_id: int, locale: str = 'ja') -> Dict[str, Any]:
        """サーバー設定を作成"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                INSERT INTO guild_settings (guild_id, category_id, locale)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id) DO UPDATE
                SET category_id = $2, locale = $3
                RETURNING *
                ''',
                guild_id, category_id, locale
            )
            return dict(row)
    
    @staticmethod
    async def update_locale(guild_id: int, locale: str) -> bool:
        """サーバーの言語設定を更新"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE guild_settings SET locale = $1 WHERE guild_id = $2',
                locale, guild_id
            )
            return 'UPDATE' in result

class UserRepository:
    """ユーザー管理に関するデータベース操作"""
    
    @staticmethod
    async def get_guild_user(guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """ギルド内のユーザー情報を取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM guild_users WHERE guild_id = $1 AND user_id = $2',
                guild_id, user_id
            )
            return dict(row) if row else None
    
    @staticmethod
    async def create_guild_user(guild_id: int, user_id: int, user_name: str) -> Dict[str, Any]:
        """ギルド内のユーザーを作成または更新"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                INSERT INTO guild_users (guild_id, user_id, user_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, user_id) DO UPDATE
                SET user_name = $3
                RETURNING *
                ''',
                guild_id, user_id, user_name
            )
            return dict(row)
    
    @staticmethod
    async def remove_guild_user(guild_id: int, user_id: int) -> bool:
        """ギルド内のユーザーを削除"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM guild_users WHERE guild_id = $1 AND user_id = $2',
                guild_id, user_id
            )
            return 'DELETE' in result
    
    @staticmethod
    async def get_all_guild_users(guild_id: int) -> List[Dict[str, Any]]:
        """ギルド内のすべてのユーザーを取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT * FROM guild_users WHERE guild_id = $1',
                guild_id
            )
            return [dict(row) for row in rows]

class ChannelRepository:
    """チャンネルマッピングに関するデータベース操作"""
    
    @staticmethod
    async def get_channel_mapping(guild_user_id: int) -> Optional[Dict[str, Any]]:
        """ユーザーのチャンネルマッピングを取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM channel_mappings WHERE guild_user_id = $1',
                guild_user_id
            )
            return dict(row) if row else None
    
    @staticmethod
    async def create_channel_mapping(guild_user_id: int, channel_id: int, pinned_message_id: int) -> Dict[str, Any]:
        """ユーザーのチャンネルマッピングを作成または更新"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                INSERT INTO channel_mappings (guild_user_id, channel_id, pinned_message_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_user_id) DO UPDATE
                SET channel_id = $2, pinned_message_id = $3
                RETURNING *
                ''',
                guild_user_id, channel_id, pinned_message_id
            )
            return dict(row)
    
    @staticmethod
    async def get_by_channel_id(channel_id: int) -> Optional[Dict[str, Any]]:
        """チャンネルIDからマッピングを取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM channel_mappings WHERE channel_id = $1',
                channel_id
            )
            return dict(row) if row else None

class ProjectRepository:
    """プロジェクト管理に関するデータベース操作"""
    
    @staticmethod
    async def get_project(project_id: int) -> Optional[Dict[str, Any]]:
        """プロジェクト情報を取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM projects WHERE id = $1',
                project_id
            )
            return dict(row) if row else None
    
    @staticmethod
    async def get_all_projects(guild_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
        """ギルド内のすべてのプロジェクトを取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            if include_archived:
                rows = await conn.fetch(
                    'SELECT * FROM projects WHERE guild_id = $1 ORDER BY created_at DESC',
                    guild_id
                )
            else:
                rows = await conn.fetch(
                    'SELECT * FROM projects WHERE guild_id = $1 AND is_archived = false ORDER BY created_at DESC',
                    guild_id
                )
            return [dict(row) for row in rows]
    
    @staticmethod
    async def create_project(
        guild_id: int, 
        name: str,
        description: str = None,
        created_by_user_id: int = None,
        default_timeout: int = 3600,
        check_interval: int = 1800,
        require_confirmation: bool = True,
        require_modal: bool = True
    ) -> Dict[str, Any]:
        """プロジェクトを作成"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                INSERT INTO projects (
                    guild_id, name, description, created_by_user_id,
                    default_timeout, check_interval, require_confirmation, require_modal
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                ''',
                guild_id, name, description, created_by_user_id,
                default_timeout, check_interval, require_confirmation, require_modal
            )
            return dict(row)
    
    @staticmethod
    async def update_project(
        project_id: int,
        name: str = None,
        description: str = None,
        default_timeout: int = None,
        check_interval: int = None,
        require_confirmation: bool = None,
        require_modal: bool = None,
        is_archived: bool = None
    ) -> Optional[Dict[str, Any]]:
        """プロジェクトを更新"""
        pool = Database.get_pool()
        
        # 更新するフィールドと値を準備
        updates = []
        params = [project_id]
        param_idx = 2
        
        if name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(name)
            param_idx += 1
        
        if description is not None:
            updates.append(f"description = ${param_idx}")
            params.append(description)
            param_idx += 1
        
        if default_timeout is not None:
            updates.append(f"default_timeout = ${param_idx}")
            params.append(default_timeout)
            param_idx += 1
        
        if check_interval is not None:
            updates.append(f"check_interval = ${param_idx}")
            params.append(check_interval)
            param_idx += 1
        
        if require_confirmation is not None:
            updates.append(f"require_confirmation = ${param_idx}")
            params.append(require_confirmation)
            param_idx += 1
        
        if require_modal is not None:
            updates.append(f"require_modal = ${param_idx}")
            params.append(require_modal)
            param_idx += 1
        
        if is_archived is not None:
            updates.append(f"is_archived = ${param_idx}")
            params.append(is_archived)
            param_idx += 1
        
        if not updates:
            return None
        
        update_query = f'''
            UPDATE projects
            SET {', '.join(updates)}
            WHERE id = $1
            RETURNING *
        '''
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(update_query, *params)
            return dict(row) if row else None

class AttendanceRepository:
    """勤怠管理に関するデータベース操作"""
    
    @staticmethod
    async def get_active_session(guild_user_id: int) -> Optional[Dict[str, Any]]:
        """ユーザーのアクティブなセッションを取得（end_timeがNull）"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT * FROM attendance_sessions 
                WHERE guild_user_id = $1 AND end_time IS NULL
                ''',
                guild_user_id
            )
            return dict(row) if row else None
    
    @staticmethod
    async def start_session(guild_user_id: int, project_id: int) -> Dict[str, Any]:
        """新しい勤怠セッションを開始"""
        pool = Database.get_pool()
        now = datetime.now()
        async with pool.acquire() as conn:
            # アクティブなセッションがある場合は自動終了
            active_session = await AttendanceRepository.get_active_session(guild_user_id)
            if active_session:
                await AttendanceRepository.end_session(
                    active_session['id'], 
                    end_summary="自動終了: 新しいセッション開始のため"
                )
            
            # 新しいセッションを作成
            row = await conn.fetchrow(
                '''
                INSERT INTO attendance_sessions (guild_user_id, project_id, start_time)
                VALUES ($1, $2, $3)
                RETURNING *
                ''',
                guild_user_id, project_id, now
            )
            return dict(row)
    
    @staticmethod
    async def end_session(session_id: int, end_summary: str = None, status: str = 'manual') -> Optional[Dict[str, Any]]:
        """勤怠セッションを終了"""
        pool = Database.get_pool()
        now = datetime.now()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                UPDATE attendance_sessions
                SET end_time = $1, end_summary = $2, status = $3
                WHERE id = $4 AND end_time IS NULL
                RETURNING *
                ''',
                now, end_summary, status, session_id
            )
            return dict(row) if row else None
    
    @staticmethod
    async def update_session_message_id(session_id: int, message_id: int) -> bool:
        """セッションに開始メッセージIDを記録"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE attendance_sessions SET start_message_id = $1 WHERE id = $2',
                message_id, session_id
            )
            return 'UPDATE' in result
    
    @staticmethod
    async def get_today_sessions(guild_user_id: int) -> List[Dict[str, Any]]:
        """ユーザーの今日のセッションを取得"""
        pool = Database.get_pool()
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT a.*, p.name as project_name
                FROM attendance_sessions a
                LEFT JOIN projects p ON a.project_id = p.id
                WHERE a.guild_user_id = $1
                  AND a.start_time >= $2
                  AND a.start_time < $3
                ORDER BY a.start_time
                ''',
                guild_user_id, today, tomorrow
            )
            return [dict(row) for row in rows]
    
    @staticmethod
    async def get_sessions(guild_user_id: int, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """ユーザーのセッション履歴を取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT a.*, p.name as project_name
                FROM attendance_sessions a
                LEFT JOIN projects p ON a.project_id = p.id
                WHERE a.guild_user_id = $1
                ORDER BY a.start_time DESC
                LIMIT $2 OFFSET $3
                ''',
                guild_user_id, limit, offset
            )
            return [dict(row) for row in rows]
    
    @staticmethod
    async def get_sessions_by_date_range(
        guild_user_id: int, 
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """指定期間のセッション履歴を取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT a.*, p.name as project_name
                FROM attendance_sessions a
                LEFT JOIN projects p ON a.project_id = p.id
                WHERE a.guild_user_id = $1
                  AND a.start_time >= $2
                  AND a.start_time < $3
                ORDER BY a.start_time
                ''',
                guild_user_id, start_date, end_date
            )
            return [dict(row) for row in rows]
    
    @staticmethod
    async def get_session(session_id: int) -> Optional[Dict[str, Any]]:
        """指定IDのセッションを取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM attendance_sessions WHERE id = $1',
                session_id
            )
            return dict(row) if row else None

class ConfirmationRepository:
    """確認処理に関するデータベース操作"""
    
    @staticmethod
    async def create_confirmation(session_id: int) -> Dict[str, Any]:
        """新しい確認リクエストを作成"""
        pool = Database.get_pool()
        now = datetime.now()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                INSERT INTO confirmations (session_id, prompt_time)
                VALUES ($1, $2)
                RETURNING *
                ''',
                session_id, now
            )
            return dict(row)
    
    @staticmethod
    async def respond_to_confirmation(confirmation_id: int, summary: str) -> Optional[Dict[str, Any]]:
        """確認リクエストに応答"""
        pool = Database.get_pool()
        now = datetime.now()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                UPDATE confirmations
                SET responded = true, response_time = $1, summary = $2
                WHERE id = $3 AND responded = false
                RETURNING *
                ''',
                now, summary, confirmation_id
            )
            return dict(row) if row else None
    
    @staticmethod
    async def get_pending_confirmations(session_id: int) -> List[Dict[str, Any]]:
        """未応答の確認リクエストを取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT * FROM confirmations
                WHERE session_id = $1 AND responded = false
                ORDER BY prompt_time DESC
                ''',
                session_id
            )
            return [dict(row) for row in rows]
    
    @staticmethod
    async def get_session_confirmations(session_id: int) -> List[Dict[str, Any]]:
        """セッションの全ての確認リクエストを取得"""
        pool = Database.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT * FROM confirmations
                WHERE session_id = $1
                ORDER BY prompt_time
                ''',
                session_id
            )
            return [dict(row) for row in rows]