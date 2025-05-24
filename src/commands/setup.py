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
        
        # 権限チェック
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                I18n.t("common.noPermission", locale="ja"),
                ephemeral=True
            )
            return
        
        # 応答を遅延させる（最大15分）
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        guild = interaction.guild
        user = interaction.user
        
        try:
            # 言語選択画面を表示
            await self._show_language_selection(interaction, guild.id, user.id)
        
        except Exception as e:
            logger.error(f"Error in setup command: {str(e)}")
            await interaction.followup.send(
                I18n.t("common.error", locale="ja", message=str(e)),
                ephemeral=True
            )
    
    async def _show_language_selection(self, interaction: discord.Interaction, guild_id: int, user_id: int):
        """言語選択画面を表示"""
        
        # 言語選択のEmbedを作成（日本語・英語両方で表記）
        embed = discord.Embed(
            title=I18n.t("setup.selectLanguage", locale="ja"),
            description=I18n.t("setup.welcome", locale="ja") + "\n" + I18n.t("setup.welcome", locale="en"),
            color=discord.Color.blue()
        )
        
        # 言語選択のオプション
        options = [
            discord.SelectOption(
                label=I18n.t("language.japanese", locale="ja"),
                value="ja",
                description="日本語"
            ),
            discord.SelectOption(
                label=I18n.t("language.english", locale="en"),
                value="en",
                description="English"
            )
        ]
        
        # セレクトメニューを作成
        select = discord.ui.Select(
            placeholder=I18n.t("setup.selectLanguage", locale="ja"),
            options=options
        )
        
        # カスタムIDを設定
        select.custom_id = f"setup_language_{guild_id}"
        
        # Viewを作成してセレクトメニューを追加
        view = discord.ui.View()
        view.add_item(select)
        
        # セレクトメニューのコールバック
        async def language_callback(interaction: discord.Interaction):
            selected_locale = select.values[0]
            
            # セットアップ進行メッセージ
            await interaction.response.send_message(
                I18n.t("setup.languageSet", locale=selected_locale),
                ephemeral=True
            )
            
            # カテゴリ選択画面に進む
            await self._show_category_selection(interaction, guild_id, user_id, selected_locale)
        
        select.callback = language_callback
        
        # メニューを送信
        await interaction.followup.send(
            embed=embed,
            view=view,
            ephemeral=True
        )
    
    async def _show_category_selection(self, interaction: discord.Interaction, guild_id: int, user_id: int, locale: str):
        """カテゴリ選択画面を表示"""
        
        guild = interaction.guild
        
        # カテゴリ選択またはカテゴリ作成のメニュー
        embed = discord.Embed(
            title=I18n.t("setup.categorySelection", locale),
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
                label=I18n.t("setup.createNewCategory", locale),
                value="create_new"
            )
        )
        
        # セレクトメニューを作成
        select = discord.ui.Select(
            placeholder=I18n.t("setup.selectCategory", locale),
            options=options
        )
        
        # カスタムIDを設定
        select.custom_id = f"setup_category_{guild_id}"
        
        # Viewを作成してセレクトメニューを追加
        view = discord.ui.View()
        view.add_item(select)
        
        # セレクトメニューのコールバック
        async def category_callback(interaction: discord.Interaction):
            if select.values[0] == "create_new":
                # 新規カテゴリ作成のモーダルを表示
                modal = discord.ui.Modal(title=I18n.t("setup.createNewCategory", locale))
                
                # カテゴリ名入力フィールド
                category_name = discord.ui.TextInput(
                    label=I18n.t("setup.categoryName", locale),
                    placeholder=I18n.t("setup.defaultCategoryName", locale),
                    default=I18n.t("setup.defaultCategoryName", locale),
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
                        guild_id,
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
                    guild_id,
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

async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))