import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Dict, Any

from ..database.repository import ProjectRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.project_list')

class ProjectListCog(commands.Cog):
    """プロジェクト一覧を表示するコマンド"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="project_list",
        description="サーバー内のプロジェクト一覧を表示します"
    )
    @app_commands.guild_only()
    async def project_list(self, interaction: discord.Interaction, include_archived: bool = False):
        """プロジェクト一覧を表示するコマンド"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = interaction.guild_id
            
            # プロジェクト一覧を取得
            projects = await ProjectRepository.get_all_projects(guild_id, include_archived)
            
            if not projects:
                await interaction.followup.send(I18n.t("project.notFound"))
                return
            
            # プロジェクト一覧のEmbedを作成
            embed = discord.Embed(
                title=I18n.t("project.list"),
                color=discord.Color.blue()
            )
            
            # プロジェクト情報をフィールドとして追加
            for project in projects:
                name = project["name"]
                description = project["description"] or "説明なし"
                
                # アーカイブ済みの場合はタイトルに表示
                if project["is_archived"]:
                    name = f"📁 {name} (アーカイブ済み)"
                
                # 確認設定情報
                settings = []
                if project["require_confirmation"]:
                    interval_minutes = project["check_interval"] // 60
                    settings.append(f"確認間隔: {interval_minutes}分")
                else:
                    settings.append("確認なし")
                
                if project["require_modal"]:
                    settings.append("要約入力あり")
                else:
                    settings.append("要約入力なし")
                
                # 設定情報をフォーマット
                settings_text = "・" + "\n・".join(settings)
                
                # フィールドとして追加
                embed.add_field(
                    name=name,
                    value=f"{description}\n\n{settings_text}",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in project_list command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", message=str(e)), ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(ProjectListCog(bot))