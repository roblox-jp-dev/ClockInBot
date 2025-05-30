# src/database/models.py
from datetime import datetime
import asyncpg
from typing import Optional, List, Dict, Any, Union

class Database:
    """データベース接続とスキーマ初期化を処理するクラス"""
    
    _pool: Optional[asyncpg.Pool] = None
    
    @classmethod
    async def create_pool(cls, config: Dict[str, str]) -> None:
        """データベース接続プールを作成"""
        cls._pool = await asyncpg.create_pool(**config)
        await cls._init_tables()
    
    @classmethod
    async def close_pool(cls) -> None:
        """データベース接続プールを閉じる"""
        if cls._pool:
            await cls._pool.close()
    
    @classmethod
    async def _init_tables(cls) -> None:
        """必要なテーブルの作成"""
        async with cls._pool.acquire() as conn:
            # guild_settings テーブル作成
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id           BIGINT       PRIMARY KEY,
                    category_id        BIGINT       NOT NULL,
                    locale             TEXT         NOT NULL DEFAULT 'ja',
                    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            ''')
            
            # guild_users テーブル作成
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS guild_users (
                    id                  BIGSERIAL    PRIMARY KEY,
                    guild_id            BIGINT       NOT NULL REFERENCES guild_settings(guild_id) ON DELETE CASCADE,
                    user_id             BIGINT       NOT NULL,
                    user_name           TEXT         NOT NULL,
                    joined_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
                    UNIQUE (guild_id, user_id)
                )
            ''')
            
            # projects テーブル作成（ON DELETE SET NULLに修正）
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id                        BIGSERIAL    PRIMARY KEY,
                    guild_id                  BIGINT       NOT NULL REFERENCES guild_settings(guild_id) ON DELETE CASCADE,
                    name                      TEXT         NOT NULL,
                    description               TEXT,
                    created_by_user_id        BIGINT       REFERENCES guild_users(id) ON DELETE SET NULL,
                    default_timeout           INT          NOT NULL DEFAULT 3600,
                    check_interval            INT          NOT NULL DEFAULT 1800,
                    require_confirmation      BOOLEAN      NOT NULL DEFAULT true,
                    require_modal             BOOLEAN      NOT NULL DEFAULT true,
                    is_archived               BOOLEAN      NOT NULL DEFAULT false,
                    created_at                TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            ''')
            
            # project_members テーブル作成（新規追加）
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS project_members (
                    id                   BIGSERIAL    PRIMARY KEY,
                    project_id           BIGINT       NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    guild_user_id        BIGINT       NOT NULL REFERENCES guild_users(id) ON DELETE CASCADE,
                    added_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
                    UNIQUE (project_id, guild_user_id)
                )
            ''')
            
            # channel_mappings テーブル作成
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS channel_mappings (
                    id                   BIGSERIAL    PRIMARY KEY,
                    guild_user_id        BIGINT       NOT NULL REFERENCES guild_users(id) ON DELETE CASCADE,
                    channel_id           BIGINT       NOT NULL,
                    pinned_message_id    BIGINT       NOT NULL,
                    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
                    UNIQUE (guild_user_id)
                )
            ''')
            
            # attendance_sessions テーブル作成
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS attendance_sessions (
                    id                   BIGSERIAL    PRIMARY KEY,
                    guild_user_id        BIGINT       NOT NULL REFERENCES guild_users(id) ON DELETE CASCADE,
                    project_id           BIGINT       REFERENCES projects(id),
                    start_time           TIMESTAMPTZ  NOT NULL,
                    end_time             TIMESTAMPTZ,
                    end_summary          TEXT,
                    start_message_id     BIGINT,
                    status               TEXT         NOT NULL
                                        CHECK (status IN ('manual','auto'))
                                        DEFAULT 'manual',
                    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            ''')
            
            # confirmations テーブル作成（message_idカラムを追加）
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS confirmations (
                    id                   BIGSERIAL    PRIMARY KEY,
                    session_id           BIGINT       NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
                    prompt_time          TIMESTAMPTZ  NOT NULL,
                    responded            BOOLEAN      NOT NULL DEFAULT false,
                    response_time        TIMESTAMPTZ,
                    summary              TEXT,
                    message_id           BIGINT,
                    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            ''')
            
            # 既存のテーブルにカラムを追加（マイグレーション）
            await conn.execute('''
                ALTER TABLE attendance_sessions ADD COLUMN IF NOT EXISTS start_message_id BIGINT
            ''')
            
            # confirmationsテーブルにmessage_idカラムを追加（マイグレーション）
            await conn.execute('''
                ALTER TABLE confirmations ADD COLUMN IF NOT EXISTS message_id BIGINT
            ''')

            # インデックス作成
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_attendance_sessions_guild_user_id
                ON attendance_sessions(guild_user_id)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_attendance_sessions_start_time
                ON attendance_sessions(start_time)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_confirmations_session_id
                ON confirmations(session_id)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_project_members_project_id
                ON project_members(project_id)
            ''')

    @classmethod
    def get_pool(cls) -> asyncpg.Pool:
        """データベース接続プールの取得"""
        if cls._pool is None:
            raise Exception("Database connection pool not initialized")
        return cls._pool