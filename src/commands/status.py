import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional

from ..database.repository import AttendanceRepository, UserRepository, ProjectRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.status')

class StatusCog(commands.Cog):
    """現在の勤務状態を確認するコマンド"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="status",
        description="現在の勤務状態を表示します"
    )
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction):
        """現在の勤務状態を表示するコマンド"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = interaction.guild_id
            user_id = interaction.user.id
            
            # ユーザー情報を取得
            guild_user = await UserRepository.get_guild_user(guild_id, user_id)
            if not guild_user:
                await interaction.followup.send(I18n.t("user.notFound", username=interaction.user.display_name))
                return
            
            # アクティブなセッションを取得
            active_session = await AttendanceRepository.get_active_session(guild_user["id"])
            
            if active_session:
                # プロジェクト情報を取得
                project = await ProjectRepository.get_project(active_session["project_id"])
                project_name = project["name"] if project else "Unknown"
                
                # 開始時間をフォーマット
                start_time = active_session["start_time"]
                start_time_str = start_time.strftime("%H:%M:%S")
                
                # 勤務中の場合は情報を表示
                message = I18n.t(
                    "status.working",
                    project=project_name,
                    start_time=start_time_str
                )
                
                # 勤務中のEmbed
                embed = discord.Embed(
                    title=I18n.t("embed.title"),
                    description=message,
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                
                # 経過時間を計算
                duration = datetime.now() - start_time
                hours, remainder = divmod(duration.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                embed.add_field(
                    name=I18n.t("embed.duration"),
                    value=f"{hours:02}:{minutes:02}:{seconds:02}",
                    inline=True
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                # 勤務していない場合のメッセージ
                message = I18n.t("status.notWorking")
                
                # 未勤務のEmbed
                embed = discord.Embed(
                    title=I18n.t("embed.title"),
                    description=message,
                    color=discord.Color.light_grey(),
                    timestamp=datetime.now()
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in status command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", message=str(e)), ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(StatusCog(bot))