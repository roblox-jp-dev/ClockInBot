import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from ..database.repository import UserRepository, ChannelRepository, GuildRepository
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
        
        # 権限チェック
        if not interaction.user.guild_permissions.administrator:
            # サーバー設定から言語を取得（権限エラー時はデフォルト言語で取得を試行）
            try:
                guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
                locale = guild_settings["locale"] if guild_settings else "ja"
            except:
                locale = "ja"
            
            await interaction.response.send_message(
                I18n.t("common.noPermission", locale),
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = interaction.guild.id
            
            # サーバー設定から言語を取得
            guild_settings = await GuildRepository.get_guild_settings(guild_id)
            if not guild_settings:
                await interaction.followup.send(I18n.t("setup.notConfigured", locale="ja"))
                return
                
            locale = guild_settings["locale"]
            
            # ユーザーが登録されているか確認
            guild_user = await UserRepository.get_guild_user(guild_id, user.id)
            if not guild_user:
                await interaction.followup.send(I18n.t("user.notFound", locale, username=user.display_name))
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
            
            await interaction.followup.send(I18n.t("user.removed", locale, username=user.display_name))
        
        except Exception as e:
            logger.error(f"Error in user_remove command: {str(e)}")
            # エラー時のデフォルト言語
            locale = "ja"
            try:
                guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
                if guild_settings:
                    locale = guild_settings["locale"]
            except:
                pass
            
            await interaction.followup.send(I18n.t("common.error", locale, message=str(e)))

async def setup(bot: commands.Bot):
    await bot.add_cog(UserRemoveCog(bot))