import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, Any
import asyncio

from ..database.repository import GuildRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.setup')

class SetupCog(commands.Cog):
    """初回セットアップおよび設定変更のためのコマンド"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="setup",
        description="勤怠管理Botの初回セットアップまたは設定変更を行います"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        """セットアップコマンド"""
        
        # 応答を遅延させる（最大15分）
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        guild = interaction.guild
        user = interaction.user
        locale = "ja"  # デフォルト言語
        
        try:
            # サーバー設定を確認
            guild_settings = await GuildRepository.get_guild_settings(guild.id)
            
            # セットアップ開始メッセージ
            await interaction.followup.send(I18n.t("setup.welcome", locale))
            
            # カテゴリ選択またはカテゴリ作成のメニュー
            embed = discord.Embed(
                title=I18n.t("setup.selectCategory", locale),
                description=I18n.t("setup.selectCategory", locale),
                color=discord.Color.blue()
            )
            
            # 既存のカテゴリの一覧を表示
            categories = [c for c in guild.categories]
            options = []
            
            # 最大25個までのカテゴリを選択肢に追加
            for i, category in enumerate(categories[:24]):
                options.append(
                    discord.SelectOption(
                        label=category.name,
                        value=str(category.id)
                    )
                )
            
            # 新規作成オプションを追加
            options.append(
                discord.SelectOption(
                    label="新規カテゴリを作成",
                    value="create_new"
                )
            )
            
            # セレクトメニューを作成
            select = discord.ui.Select(
                placeholder="カテゴリを選択",
                options=options
            )
            
            # カスタムIDを設定
            select.custom_id = f"setup_category_{guild.id}"
            
            # Viewを作成してセレクトメニューを追加
            view = discord.ui.View()
            view.add_item(select)
            
            # セレクトメニューのコールバック
            async def category_callback(interaction: discord.Interaction):
                if select.values[0] == "create_new":
                    # 新規カテゴリ作成のモーダルを表示
                    modal = discord.ui.Modal(title="カテゴリ作成")
                    
                    # カテゴリ名入力フィールド
                    category_name = discord.ui.TextInput(
                        label="カテゴリ名",
                        placeholder="勤怠管理",
                        default="勤怠管理",
                        required=True
                    )
                    
                    modal.add_item(category_name)
                    
                    # モーダル送信時の処理
                    async def on_modal_submit(interaction: discord.Interaction):
                        name = category_name.value
                        
                        # カテゴリを作成
                        category = await guild.create_category(name)
                        
                        # サーバー設定を保存または更新
                        await GuildRepository.create_guild_settings(
                            guild.id,
                            category.id,
                            locale
                        )
                        
                        await interaction.response.send_message(
                            I18n.t("setup.categoryCreated", locale, name=name),
                            ephemeral=True
                        )
                        
                        # セットアップ完了メッセージ
                        await interaction.followup.send(
                            I18n.t("setup.complete", locale),
                            ephemeral=True
                        )
                    
                    modal.on_submit = on_modal_submit
                    await interaction.response.send_modal(modal)
                
                else:
                    # 既存のカテゴリを選択
                    category_id = int(select.values[0])
                    
                    # サーバー設定を保存または更新
                    await GuildRepository.create_guild_settings(
                        guild.id,
                        category_id,
                        locale
                    )
                    
                    # 選択したカテゴリ名を取得
                    category = guild.get_channel(category_id)
                    category_name = category.name if category else "Unknown"
                    
                    await interaction.response.send_message(
                        I18n.t("setup.categoryCreated", locale, name=category_name),
                        ephemeral=True
                    )
                    
                    # セットアップ完了メッセージ
                    await interaction.followup.send(
                        I18n.t("setup.complete", locale),
                        ephemeral=True
                    )
            
            select.callback = category_callback
            
            # メニューを送信
            await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True
            )
        
        except Exception as e:
            logger.error(f"Error in setup command: {str(e)}")
            await interaction.followup.send(
                I18n.t("common.error", locale, message=str(e)),
                ephemeral=True
            )

def setup(bot: commands.Bot):
    bot.add_cog(SetupCog(bot))