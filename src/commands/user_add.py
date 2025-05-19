import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from ..database.repository import UserRepository, ChannelRepository, GuildRepository
from ..utils.i18n import I18n
from ..views.attendance_view import create_or_update_attendance_message
from ..utils.logger import setup_logger

logger = setup_logger('commands.user_add')

class UserAddCog(commands.Cog):
    """ユーザーをBotに追加するコマンド"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="user_add",
        description="勤怠管理Botにユーザーを追加します"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        user="追加するユーザー"
    )
    async def user_add(self, interaction: discord.Interaction, user: discord.User):
        """ユーザーを追加するコマンド"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild = interaction.guild
            guild_id = guild.id
            
            # サーバー設定を取得
            guild_settings = await GuildRepository.get_guild_settings(guild_id)
            if not guild_settings:
                await interaction.followup.send("サーバー設定が見つかりません。`/setup` コマンドでセットアップしてください。")
                return
            
            category_id = guild_settings["category_id"]
            locale = guild_settings["locale"]
            
            # カテゴリを取得
            category = guild.get_channel(category_id)
            if not category:
                await interaction.followup.send("勤怠管理用カテゴリが見つかりません。`/setup` コマンドで再設定してください。")
                return
            
            # ユーザーが既に登録されているか確認
            existing_user = await UserRepository.get_guild_user(guild_id, user.id)
            if existing_user:
                await interaction.followup.send(I18n.t("user.alreadyExists", locale, username=user.display_name))
                return
            
            # ユーザーを登録
            guild_user = await UserRepository.create_guild_user(
                guild_id=guild_id,
                user_id=user.id,
                user_name=user.display_name
            )
            
            # ユーザー専用チャンネルを作成
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            channel_name = f"勤怠-{user.display_name}"
            channel = await category.create_text_channel(channel_name, overwrites=overwrites)
            
            # 勤怠管理用の固定メッセージを作成
            message = await create_or_update_attendance_message(
                channel=channel,
                guild_user_id=guild_user["id"],
                locale=locale
            )
            
            # チャンネルマッピングを登録
            await ChannelRepository.create_channel_mapping(
                guild_user_id=guild_user["id"],
                channel_id=channel.id,
                pinned_message_id=message.id
            )
            
            await interaction.followup.send(I18n.t("user.added", locale, username=user.display_name))
        
        except Exception as e:
            logger.error(f"Error in user_add command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", locale="ja", message=str(e)))

def setup(bot: commands.Bot):
    bot.add_cog(UserAddCog(bot))