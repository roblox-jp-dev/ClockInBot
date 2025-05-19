import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from typing import List, Dict, Any

from ..database.repository import AttendanceRepository, UserRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.today')

class TodayCog(commands.Cog):
    """本日の勤務時間を表示するコマンド"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="today",
        description="本日の勤務時間合計を表示します"
    )
    @app_commands.guild_only()
    async def today(self, interaction: discord.Interaction):
        """本日の勤務時間を表示するコマンド"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = interaction.guild_id
            user_id = interaction.user.id
            
            # ユーザー情報を取得
            guild_user = await UserRepository.get_guild_user(guild_id, user_id)
            if not guild_user:
                await interaction.followup.send(I18n.t("user.notFound", username=interaction.user.display_name))
                return
            
            # 今日のセッションを取得
            today_sessions = await AttendanceRepository.get_today_sessions(guild_user["id"])
            
            # 今日の日付をフォーマット
            today = datetime.now().strftime("%Y/%m/%d")
            
            # 今日の勤務記録がない場合
            if not today_sessions:
                embed = discord.Embed(
                    title=I18n.t("today.summary", date=today),
                    description=I18n.t("today.noRecord"),
                    color=discord.Color.light_grey(),
                    timestamp=datetime.now()
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # 合計時間を計算
            total_seconds = 0
            records = []
            
            for session in today_sessions:
                start_time = session["start_time"]
                # 終了時間がない場合は現在時刻を使用
                end_time = session["end_time"] if session["end_time"] else datetime.now()
                
                duration = end_time - start_time
                total_seconds += duration.total_seconds()
                
                # 個別のセッション情報をフォーマット
                start_str = start_time.strftime("%H:%M")
                end_str = end_time.strftime("%H:%M") if session["end_time"] else "進行中"
                
                hours, remainder = divmod(int(duration.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                duration_str = f"{hours:02}:{minutes:02}"
                
                project_name = session.get("project_name", "Unknown")
                
                record = f"{start_str}～{end_str} ({duration_str}) - {project_name}"
                records.append(record)
            
            # 合計時間をフォーマット
            total_hours, remainder = divmod(int(total_seconds), 3600)
            total_minutes, _ = divmod(remainder, 60)
            
            # 表示用Embedを作成
            embed = discord.Embed(
                title=I18n.t("today.summary", date=today),
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # 合計時間を表示
            embed.add_field(
                name=I18n.t("today.total", hours=total_hours, minutes=total_minutes),
                value="\n".join(records),
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in today command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", message=str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TodayCog(bot))