import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from ..database.repository import AttendanceRepository, UserRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.log')

class LogCog(commands.Cog):
    """過去の勤怠ログを表示するコマンド"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="log",
        description="過去の勤怠ログを表示します"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        limit="表示する履歴の数（最大50、デフォルト: 10）",
        offset="スキップする履歴の数（デフォルト: 0）"
    )
    async def log(self, interaction: discord.Interaction, limit: int = 10, offset: int = 0):
        """過去の勤怠ログを表示するコマンド"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = interaction.guild.id
            user_id = interaction.user.id
            
            # リミットの範囲を制限
            if limit > 50:
                limit = 50
            elif limit < 1:
                limit = 1
            
            # オフセットの範囲を制限
            if offset < 0:
                offset = 0
            
            # ユーザー情報を取得
            guild_user = await UserRepository.get_guild_user(guild_id, user_id)
            if not guild_user:
                await interaction.followup.send(I18n.t("user.notFound", username=interaction.user.display_name))
                return
            
            # セッション履歴を取得
            sessions = await AttendanceRepository.get_sessions(guild_user["id"], limit, offset)
            
            if not sessions:
                await interaction.followup.send(I18n.t("log.noRecord"))
                return
            
            # 履歴表示用のEmbedを作成
            embed = discord.Embed(
                title=I18n.t("log.title", limit=limit),
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # 履歴をフォーマット
            session_logs = []
            
            for session in sessions:
                start_time = session["start_time"]
                end_time = session["end_time"] if session["end_time"] else datetime.now()
                
                # 日付と時刻をフォーマット
                start_str = start_time.strftime("%Y/%m/%d %H:%M")
                end_str = end_time.strftime("%H:%M") if session["end_time"] else "進行中"
                
                # 勤務時間を計算
                duration = end_time - start_time
                hours, remainder = divmod(int(duration.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                duration_str = f"{hours:02}:{minutes:02}"
                
                # プロジェクト名
                project_name = session.get("project_name", "Unknown")
                
                # 履歴行を作成
                log_line = I18n.t(
                    "log.format",
                    start=start_str,
                    end=end_str,
                    duration=duration_str,
                    project=project_name
                )
                
                # 自動終了の場合はマーク
                if session.get("status") == "auto":
                    log_line += " (自動終了)"
                
                session_logs.append(log_line)
            
            # 履歴をフィールドとして追加
            embed.description = "\n".join(session_logs)
            
            # ページネーション情報を追加
            if offset > 0 or len(sessions) >= limit:
                embed.set_footer(text=f"Page: {offset // limit + 1} (Offset: {offset}, Limit: {limit})")
            
            # ページ送りボタンを作成
            view = discord.ui.View()
            
            # 前ページボタン
            prev_button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="前のページ",
                disabled=offset <= 0,
                custom_id=f"log_prev_{offset}_{limit}"
            )
            
            # 次ページボタン
            next_button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="次のページ",
                disabled=len(sessions) < limit,
                custom_id=f"log_next_{offset}_{limit}"
            )
            
            # ボタンコールバック
            async def prev_callback(interaction: discord.Interaction):
                new_offset = max(0, offset - limit)
                await self.log(interaction, limit, new_offset)
            
            async def next_callback(interaction: discord.Interaction):
                new_offset = offset + limit
                await self.log(interaction, limit, new_offset)
            
            prev_button.callback = prev_callback
            next_button.callback = next_callback
            
            view.add_item(prev_button)
            view.add_item(next_button)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in log command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", message=str(e)))

def setup(bot: commands.Bot):
    bot.add_cog(LogCog(bot))