import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from ..database.repository import UserRepository, ChannelRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.user_remove')

class UserRemoveCog(commands.Cog):
    """ユーザーをBotから削除するコマンド"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="user_remove",
        description="勤怠管理Botからユーザーを削除します"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        user="削除するユーザー"
    )
    async def user_remove(self, interaction: discord.Interaction, user: discord.User):
        """ユーザーを削除するコマンド"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = interaction.guild.id
            
            # ユーザーが登録されているか確認
            guild_user = await UserRepository.get_guild_user(guild_id, user.id)
            if not guild_user:
                await interaction.followup.send(I18n.t("user.notFound", username=user.display_name))
                return
            
            # チャンネルマッピングを取得
            channel_mapping = await ChannelRepository.get_channel_mapping(guild_user["id"])
            
            # チャンネルを削除
            if channel_mapping:
                channel = interaction.guild.get_channel(channel_mapping["channel_id"])
                if channel:
                    try:
                        await channel.delete()
                        logger.info(f"Deleted channel {channel.name} for user {user.display_name}")
                    except discord.Forbidden:
                        logger.warning(f"No permission to delete channel {channel.name}")
                    except discord.NotFound:
                        logger.warning(f"Channel {channel_mapping['channel_id']} not found")
                    except Exception as e:
                        logger.error(f"Error deleting channel: {str(e)}")
            
            # ユーザーを削除（カスケード削除でチャンネルマッピングや勤怠記録も削除される）
            await UserRepository.remove_guild_user(guild_id, user.id)
            
            await interaction.followup.send(I18n.t("user.removed", username=user.display_name))
        
        except Exception as e:
            logger.error(f"Error in user_remove command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", message=str(e)))

async def setup(bot: commands.Bot):
    await bot.add_cog(UserRemoveCog(bot))