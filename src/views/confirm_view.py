import discord
from discord import ui, Interaction, ButtonStyle
from datetime import datetime
from typing import Optional, Dict, Any

from ..database.repository import (
    AttendanceRepository, ProjectRepository, ConfirmationRepository, ChannelRepository
)
from ..utils.i18n import I18n

class ConfirmationModal(ui.Modal):
    """確認リクエストの応答用モーダル"""
    
    def __init__(self, confirmation_id: int, locale: str):
        super().__init__(title=I18n.t("modal.summary", locale))
        
        self.confirmation_id = confirmation_id
        self.locale = locale
        
        # 要約入力フィールド
        self.summary = ui.TextInput(
            label=I18n.t("modal.summary", locale),
            placeholder=I18n.t("modal.summaryPlaceholder", locale),
            style=discord.TextStyle.paragraph,
            required=False
        )
        
        self.add_item(self.summary)
    
    async def on_submit(self, interaction: Interaction):
        # 確認リクエストに応答
        updated = await ConfirmationRepository.respond_to_confirmation(
            self.confirmation_id,
            self.summary.value
        )
        
        if updated:
            await interaction.response.send_message(
                I18n.t("common.success", self.locale),
                ephemeral=True
            )
            
            # ボタンを無効化
            await disable_confirmation_message(interaction.message)
        else:
            await interaction.response.send_message(
                I18n.t("common.error", self.locale, message="Could not update confirmation"),
                ephemeral=True
            )

class ConfirmationView(ui.View):
    """定期確認用のView"""
    
    def __init__(self, confirmation_id: int, session_id: int, locale: str = "ja"):
        super().__init__(timeout=600)  # 10分でタイムアウト
        self.confirmation_id = confirmation_id
        self.session_id = session_id
        self.locale = locale
        
        # ボタンを追加
        confirm_button = ui.Button(
            label="確認する",
            style=ButtonStyle.primary,
            custom_id="confirm"
        )
        
        ignore_button = ui.Button(
            label="無視する",
            style=ButtonStyle.secondary,
            custom_id="ignore"
        )
        
        self.add_item(confirm_button)
        self.add_item(ignore_button)
    
    async def on_timeout(self):
        """タイムアウト時の処理"""
        # ボタンを無効化
        for child in self.children:
            child.disabled = True
        
        # もしメッセージがまだ存在するなら更新
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except:
            pass

async def handle_confirmation_interaction(interaction: discord.Interaction):
    """確認リクエストのインタラクション処理"""
    custom_id = interaction.data.get('custom_id', '')
    
    if custom_id == "confirm":
        await handle_confirm_button(interaction)
    elif custom_id == "ignore":
        await handle_ignore_button(interaction)

async def get_confirmation_info_from_channel(channel_id: int) -> Optional[Dict[str, Any]]:
    """チャンネルIDから確認情報を取得"""
    
    # チャンネルマッピングからguild_user_idを取得
    channel_mapping = await ChannelRepository.get_by_channel_id(channel_id)
    if not channel_mapping:
        return None
    
    guild_user_id = channel_mapping["guild_user_id"]
    
    # アクティブなセッションを取得
    active_session = await AttendanceRepository.get_active_session(guild_user_id)
    if not active_session:
        return None
    
    # 最新の未回答確認を取得
    pending_confirmations = await ConfirmationRepository.get_pending_confirmations(active_session["id"])
    if not pending_confirmations:
        return None
    
    # 最新の確認を取得
    latest_confirmation = max(pending_confirmations, key=lambda x: x['prompt_time'])
    
    return {
        "confirmation": latest_confirmation,
        "session": active_session,
        "guild_user_id": guild_user_id
    }

async def handle_confirm_button(interaction: discord.Interaction):
    """確認ボタンのハンドラ"""
    
    # チャンネルIDから確認情報を取得
    confirmation_info = await get_confirmation_info_from_channel(interaction.channel_id)
    if not confirmation_info:
        await interaction.response.send_message(
            "確認対象が見つかりません",
            ephemeral=True
        )
        return
    
    confirmation = confirmation_info["confirmation"]
    session = confirmation_info["session"]
    
    # サーバー設定から言語を取得
    from ..database.repository import GuildRepository
    guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
    locale = guild_settings["locale"] if guild_settings else "ja"
    
    # プロジェクト情報を取得
    project = await ProjectRepository.get_project(session["project_id"])
    
    if project and project.get("require_modal", True):
        # モーダルを表示する
        modal = ConfirmationModal(confirmation["id"], locale)
        await interaction.response.send_modal(modal)
    else:
        # モーダルなしで直接応答
        updated = await ConfirmationRepository.respond_to_confirmation(
            confirmation["id"],
            "Confirmed without summary"
        )
        
        if updated:
            await interaction.response.send_message(
                I18n.t("common.success", locale),
                ephemeral=True
            )
            
            # ボタンを無効化
            await disable_confirmation_message(interaction.message)
        else:
            await interaction.response.send_message(
                I18n.t("common.error", locale, message="Could not update confirmation"),
                ephemeral=True
            )

async def handle_ignore_button(interaction: discord.Interaction):
    """無視ボタンのハンドラ"""
    
    # チャンネルIDから確認情報を取得
    confirmation_info = await get_confirmation_info_from_channel(interaction.channel_id)
    if not confirmation_info:
        await interaction.response.send_message(
            "確認対象が見つかりません",
            ephemeral=True
        )
        return
    
    confirmation = confirmation_info["confirmation"]
    
    # サーバー設定から言語を取得
    from ..database.repository import GuildRepository
    guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
    locale = guild_settings["locale"] if guild_settings else "ja"
    
    # 無視しても応答されたとしてマーク
    updated = await ConfirmationRepository.respond_to_confirmation(
        confirmation["id"],
        "Ignored"
    )
    
    if updated:
        await interaction.response.send_message(
            I18n.t("common.success", locale),
            ephemeral=True
        )
        
        # ボタンを無効化
        await disable_confirmation_message(interaction.message)
    else:
        await interaction.response.send_message(
            I18n.t("common.error", locale, message="Could not update confirmation"),
            ephemeral=True
        )

async def disable_confirmation_message(message: discord.Message):
    """確認メッセージのボタンを無効化"""
    try:
        # 新しいViewを作成（ボタンを無効化）
        view = ui.View()
        
        disabled_confirm_button = ui.Button(
            label="確認済み",
            style=ButtonStyle.secondary,
            disabled=True,
            custom_id="confirm_disabled"
        )
        
        disabled_ignore_button = ui.Button(
            label="処理済み",
            style=ButtonStyle.secondary,
            disabled=True,
            custom_id="ignore_disabled"
        )
        
        view.add_item(disabled_confirm_button)
        view.add_item(disabled_ignore_button)
        
        await message.edit(view=view)
    except:
        pass

async def send_confirmation_request(
    bot: discord.Client,
    session_id: int,
    user_id: int,
    channel_id: int,
    locale: str = "ja"
) -> Optional[Dict[str, Any]]:
    """確認リクエストを送信"""
    
    # 確認リクエストをデータベースに記録
    confirmation = await ConfirmationRepository.create_confirmation(session_id)
    
    # チャンネルを取得
    channel = bot.get_channel(channel_id)
    if not channel:
        return None
    
    # ユーザーを取得
    user = bot.get_user(user_id)
    if not user:
        return None
    
    # 確認メッセージ用のEmbed作成
    embed = discord.Embed(
        title=I18n.t("attendance.confirmation", locale),
        description=I18n.t("attendance.confirmation", locale),
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    # Viewを作成
    view = ConfirmationView(confirmation["id"], session_id, locale)
    
    # メッセージを送信
    try:
        message = await channel.send(
            content=user.mention,
            embed=embed,
            view=view,
            delete_after=600  # 10分後に自動削除
        )
        
        # Viewのメッセージを設定
        view.message = message
        
        return confirmation
    except Exception as e:
        print(f"Failed to send confirmation: {str(e)}")
        return None