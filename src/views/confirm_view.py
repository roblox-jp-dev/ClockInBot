import discord
from discord import ui, Interaction, ButtonStyle
from datetime import datetime
from typing import Optional, Dict, Any

from ..database.repository import (
    AttendanceRepository, ProjectRepository, ConfirmationRepository
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
    
    @ui.button(label="確認する", style=ButtonStyle.primary, custom_id="confirm")
    async def confirm_button(self, interaction: Interaction, button: ui.Button):
        """確認ボタンのハンドラ"""
        # セッション情報を取得
        session = await AttendanceRepository.get_session(self.session_id)
        if not session or session.get("end_time"):
            await interaction.response.send_message(
                I18n.t("attendance.notStarted", self.locale),
                ephemeral=True
            )
            return
        
        # プロジェクト情報を取得
        project = await ProjectRepository.get_project(session["project_id"])
        
        if project and project.get("require_modal", True):
            # モーダルを表示する
            modal = ConfirmationModal(self.confirmation_id, self.locale)
            await interaction.response.send_modal(modal)
        else:
            # モーダルなしで直接応答
            updated = await ConfirmationRepository.respond_to_confirmation(
                self.confirmation_id,
                "Confirmed without summary"
            )
            
            if updated:
                await interaction.response.send_message(
                    I18n.t("common.success", self.locale),
                    ephemeral=True
                )
                
                # ボタンを無効化
                for child in self.children:
                    child.disabled = True
                
                await interaction.message.edit(view=self)
            else:
                await interaction.response.send_message(
                    I18n.t("common.error", self.locale, message="Could not update confirmation"),
                    ephemeral=True
                )
    
    @ui.button(label="無視する", style=ButtonStyle.secondary, custom_id="ignore")
    async def ignore_button(self, interaction: Interaction, button: ui.Button):
        """無視ボタンのハンドラ"""
        # 無視しても応答されたとしてマーク
        updated = await ConfirmationRepository.respond_to_confirmation(
            self.confirmation_id,
            "Ignored"
        )
        
        if updated:
            await interaction.response.send_message(
                I18n.t("common.success", self.locale),
                ephemeral=True
            )
            
            # ボタンを無効化
            for child in self.children:
                child.disabled = True
            
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message(
                I18n.t("common.error", self.locale, message="Could not update confirmation"),
                ephemeral=True
            )
    
    async def on_timeout(self):
        """タイムアウト時の処理"""
        # ボタンを無効化
        for child in self.children:
            child.disabled = True
        
        # もしメッセージがまだ存在するなら更新
        try:
            if self.message:
                await self.message.edit(view=self)
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
    
    # メッセージを送信（Ephemeral）
    try:
        # discordの仕様上、Ephemeralメッセージはウェブフックでのみ可能
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