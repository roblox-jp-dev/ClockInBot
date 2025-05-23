# src/views/confirm_view.py
import discord
from discord import ui, Interaction, ButtonStyle
from datetime import datetime, timezone
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
        try:
            print(f"[DEBUG] Modal submitted with confirmation_id: {self.confirmation_id}")
            print(f"[DEBUG] Summary value: '{self.summary.value}'")
            
            # 確認リクエストに応答
            updated = await ConfirmationRepository.respond_to_confirmation(
                self.confirmation_id,
                self.summary.value
            )
            
            print(f"[DEBUG] Database update result: {updated}")
            
            if updated:
                # 応答を送信（先にレスポンスを返す）
                await interaction.response.send_message(
                    "✅ 勤務状況の確認が完了しました",
                    ephemeral=True,
                    delete_after=3
                )
                
                # 勤務開始メッセージにコメントを追加（レスポンス後に実行）
                try:
                    await self._add_comment_to_start_message(interaction)
                    print("[DEBUG] Comment added successfully")
                except Exception as e:
                    print(f"[DEBUG] Error adding comment: {str(e)}")
                    import traceback
                    traceback.print_exc()
                
                # 確認メッセージを削除
                try:
                    await interaction.message.delete()
                    print("[DEBUG] Confirmation message deleted")
                except Exception as e:
                    print(f"[DEBUG] Error deleting confirmation message: {str(e)}")
            else:
                await interaction.response.send_message(
                    I18n.t("common.error", self.locale, message="Could not update confirmation"),
                    ephemeral=True
                )
                print("[DEBUG] Failed to update confirmation in database")
                
        except Exception as e:
            print(f"[DEBUG] Error in modal submit: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # エラー時の応答
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "エラーが発生しました。もう一度お試しください。",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "エラーが発生しました。もう一度お試しください。",
                        ephemeral=True
                    )
            except:
                pass
    
    async def _add_comment_to_start_message(self, interaction: Interaction):
        """勤務開始メッセージにコメントを追加"""
        try:
            # 入力内容が空の場合は何もしない
            if not self.summary.value or not self.summary.value.strip():
                print("[DEBUG] No summary to add, skipping comment addition")
                return
            
            # チャンネルIDから確認情報を取得
            confirmation_info = await get_confirmation_info_from_channel(interaction.channel_id)
            if not confirmation_info:
                print("[DEBUG] Could not get confirmation info from channel")
                return
            
            session = confirmation_info["session"]
            start_message_id = session.get("start_message_id")
            
            if not start_message_id:
                print("[DEBUG] No start_message_id found in session")
                return
            
            print(f"[DEBUG] Adding comment to message {start_message_id}: '{self.summary.value}'")
            
            # 勤務開始メッセージを取得
            try:
                start_message = await interaction.channel.fetch_message(start_message_id)
                print(f"[DEBUG] Found start message with {len(start_message.embeds)} embeds")
            except discord.NotFound:
                print("[DEBUG] Start message not found")
                return
            except Exception as e:
                print(f"[DEBUG] Error fetching start message: {str(e)}")
                return
            
            # 現在の時刻を取得
            now = datetime.now(timezone.utc)
            timestamp = int(now.timestamp())
            
            # 元のEmbedの色を取得
            original_color = discord.Color.green()  # デフォルト
            if start_message.embeds:
                original_color = start_message.embeds[0].color or discord.Color.green()
            
            # コメント用の新しいEmbedを作成
            comment_embed = discord.Embed(
                description=f"<t:{timestamp}:t> - {self.summary.value.strip()}",
                color=original_color
            )
            
            # 既存のEmbedsを取得してコメントEmbedを追加
            existing_embeds = start_message.embeds.copy()
            existing_embeds.append(comment_embed)
            
            print(f"[DEBUG] Updating message with {len(existing_embeds)} embeds")
            
            # メッセージを更新
            await start_message.edit(embeds=existing_embeds)
            print("[DEBUG] Successfully updated start message with comment")
            
        except Exception as e:
            print(f"[DEBUG] Error in _add_comment_to_start_message: {str(e)}")
            import traceback
            traceback.print_exc()

class ConfirmationView(ui.View):
    """定期確認用のView（確認ボタンのみ）"""
    
    def __init__(self, confirmation_id: int, session_id: int, locale: str = "ja"):
        super().__init__(timeout=600)  # 10分でタイムアウト
        self.confirmation_id = confirmation_id
        self.session_id = session_id
        self.locale = locale
        
        # 確認ボタンのみ追加
        confirm_button = ui.Button(
            label="確認する",
            style=ButtonStyle.primary,
            custom_id="confirm"
        )
        
        self.add_item(confirm_button)
    
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

async def get_confirmation_info_from_channel(channel_id: int) -> Optional[Dict[str, Any]]:
    """チャンネルIDから確認情報を取得"""
    
    try:
        print(f"[DEBUG] Getting confirmation info from channel {channel_id}")
        
        # チャンネルマッピングからguild_user_idを取得
        channel_mapping = await ChannelRepository.get_by_channel_id(channel_id)
        if not channel_mapping:
            print("[DEBUG] No channel mapping found")
            return None
        
        guild_user_id = channel_mapping["guild_user_id"]
        print(f"[DEBUG] Found guild_user_id: {guild_user_id}")
        
        # アクティブなセッションを取得
        active_session = await AttendanceRepository.get_active_session(guild_user_id)
        if not active_session:
            print("[DEBUG] No active session found")
            return None
        
        print(f"[DEBUG] Found active session: {active_session['id']}")
        
        # セッションのすべての確認を取得（応答済みも含む）
        all_confirmations = await ConfirmationRepository.get_session_confirmations(active_session["id"])
        print(f"[DEBUG] Found {len(all_confirmations)} total confirmations")
        
        # 未回答の確認を取得
        pending_confirmations = await ConfirmationRepository.get_pending_confirmations(active_session["id"])
        print(f"[DEBUG] Found {len(pending_confirmations)} pending confirmations")
        
        if not pending_confirmations:
            print("[DEBUG] No pending confirmations")
            return None
        
        # 最新の確認を取得
        latest_confirmation = max(pending_confirmations, key=lambda x: x['prompt_time'])
        print(f"[DEBUG] Latest confirmation ID: {latest_confirmation['id']}")
        
        return {
            "confirmation": latest_confirmation,
            "session": active_session,
            "guild_user_id": guild_user_id
        }
        
    except Exception as e:
        print(f"[DEBUG] Error in get_confirmation_info_from_channel: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

async def handle_confirm_button(interaction: discord.Interaction):
    """確認ボタンのハンドラ"""
    
    try:
        print(f"[DEBUG] Confirm button pressed in channel {interaction.channel_id}")
        
        # チャンネルIDから確認情報を取得
        confirmation_info = await get_confirmation_info_from_channel(interaction.channel_id)
        if not confirmation_info:
            await interaction.response.send_message(
                "確認対象が見つかりません",
                ephemeral=True
            )
            print("[DEBUG] No confirmation info found")
            return
        
        confirmation = confirmation_info["confirmation"]
        session = confirmation_info["session"]
        
        print(f"[DEBUG] Processing confirmation {confirmation['id']} for session {session['id']}")
        
        # サーバー設定から言語を取得
        from ..database.repository import GuildRepository
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # プロジェクト情報を取得
        project = await ProjectRepository.get_project(session["project_id"])
        
        if project and project.get("require_modal", True):
            print("[DEBUG] Showing modal for confirmation")
            # モーダルを表示する
            modal = ConfirmationModal(confirmation["id"], locale)
            await interaction.response.send_modal(modal)
        else:
            print("[DEBUG] Processing confirmation without modal")
            # モーダルなしで直接応答
            updated = await ConfirmationRepository.respond_to_confirmation(
                confirmation["id"],
                "Confirmed without summary"
            )
            
            if updated:
                # 完了メッセージを送信
                await interaction.response.send_message(
                    "✅ 勤務状況の確認が完了しました",
                    ephemeral=True,
                    delete_after=3
                )
                
                # 確認メッセージを削除
                try:
                    await interaction.message.delete()
                    print("[DEBUG] Confirmation message deleted (no modal)")
                except Exception as e:
                    print(f"[DEBUG] Error deleting confirmation message: {str(e)}")
            else:
                await interaction.response.send_message(
                    I18n.t("common.error", locale, message="Could not update confirmation"),
                    ephemeral=True
                )
                print("[DEBUG] Failed to update confirmation without modal")
                
    except Exception as e:
        print(f"[DEBUG] Error in handle_confirm_button: {str(e)}")
        import traceback
        traceback.print_exc()
        
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "エラーが発生しました。もう一度お試しください。",
                    ephemeral=True
                )
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
    
    try:
        print(f"[DEBUG] Sending confirmation request for session {session_id}")
        
        # 確認リクエストをデータベースに記録
        confirmation = await ConfirmationRepository.create_confirmation(session_id)
        print(f"[DEBUG] Created confirmation with id {confirmation['id']}")
        
        # チャンネルを取得
        channel = bot.get_channel(channel_id)
        if not channel:
            print("[DEBUG] Channel not found")
            return None
        
        # ユーザーを取得
        user = bot.get_user(user_id)
        if not user:
            print("[DEBUG] User not found")
            return None
        
        # 確認メッセージ用のEmbed作成
        embed = discord.Embed(
            title="⏰ 勤務状況確認",
            description="引き続き勤務中ですか？\n下のボタンを押して勤務状況を確認してください。",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Viewを作成（確認ボタンのみ）
        view = ConfirmationView(confirmation["id"], session_id, locale)
        
        # メッセージを送信
        message = await channel.send(
            content=user.mention,
            embed=embed,
            view=view,
            delete_after=600  # 10分後に自動削除
        )
        
        # Viewのメッセージを設定
        view.message = message
        
        print(f"[DEBUG] Confirmation message sent with id {message.id}")
        return confirmation
        
    except Exception as e:
        print(f"[DEBUG] Failed to send confirmation: {str(e)}")
        import traceback
        traceback.print_exc()
        return None