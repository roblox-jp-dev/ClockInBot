import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, Any, List

from ..database.repository import ProjectRepository, UserRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.project_setting')

class ProjectSettingView(discord.ui.View):
    """プロジェクト設定用のView（5分でタイムアウト）"""
    
    def __init__(self, guild_id: int, projects: List[Dict[str, Any]]):
        super().__init__(timeout=300)  # 5分でタイムアウト
        self.guild_id = guild_id
        self.projects = projects
    
    async def on_timeout(self):
        """タイムアウト時にメッセージを削除"""
        try:
            # 全てのボタンを無効化
            for child in self.children:
                child.disabled = True
            
            # メッセージを編集して削除通知
            if hasattr(self, 'message'):
                embed = discord.Embed(
                    title="⏰ タイムアウト",
                    description="プロジェクト設定パネルは5分間の無操作により自動削除されました。",
                    color=discord.Color.orange()
                )
                await self.message.edit(embed=embed, view=self)
                
                # 3秒後に完全削除
                import asyncio
                await asyncio.sleep(3)
                await self.message.delete()
        except Exception as e:
            logger.error(f"Error during timeout cleanup: {str(e)}")

class ProjectSettingCog(commands.Cog):
    """プロジェクト設定を管理するコマンド"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="project_setting",
        description="プロジェクトの追加/編集/アーカイブを行います"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def project_setting(self, interaction: discord.Interaction):
        """プロジェクト設定パネルを表示するコマンド"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = interaction.guild_id
            user_id = interaction.user.id
            
            # プロジェクト一覧を取得（アーカイブ済みも含む）
            projects = await ProjectRepository.get_all_projects(guild_id, include_archived=True)
            
            # プロジェクト設定パネルのEmbedを作成
            embed = await self._create_project_panel_embed(projects)
            
            # 操作用のViewを作成
            view = ProjectSettingView(guild_id, projects)
            
            # 新規プロジェクト追加ボタン
            add_button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="新規プロジェクト追加",
                custom_id="add_project"
            )
            
            # 編集ボタン
            edit_button = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="プロジェクト編集",
                custom_id="edit_project"
            )
            
            # アーカイブボタン
            archive_button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="プロジェクトアーカイブ",
                custom_id="archive_project"
            )
            
            # ボタンにコールバックを設定
            add_button.callback = lambda i: self._add_project_callback(i, guild_id, user_id)
            edit_button.callback = lambda i: self._edit_project_callback(i, projects)
            archive_button.callback = lambda i: self._archive_project_callback(i, projects)
            
            # Viewにボタンを追加
            view.add_item(add_button)
            view.add_item(edit_button)
            view.add_item(archive_button)
            
            # メッセージを送信してViewのmessage属性に設定
            message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            view.message = message
        
        except Exception as e:
            logger.error(f"Error in project_setting command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", message=str(e)), ephemeral=True)
    
    async def _create_project_panel_embed(self, projects: List[Dict[str, Any]]) -> discord.Embed:
        """プロジェクト設定パネルのEmbedを作成"""
        embed = discord.Embed(
            title="プロジェクト設定",
            description="下記のボタンからプロジェクトの追加/編集/アーカイブが行えます",
            color=discord.Color.blue()
        )
        
        # 既存プロジェクトがある場合は一覧を表示
        if projects:
            active_projects = [p for p in projects if not p["is_archived"]]
            archived_projects = [p for p in projects if p["is_archived"]]
            
            if active_projects:
                active_text = "\n".join([f"・{p['name']}" for p in active_projects])
                embed.add_field(
                    name="アクティブなプロジェクト",
                    value=active_text,
                    inline=False
                )
            
            if archived_projects:
                archived_text = "\n".join([f"・{p['name']}" for p in archived_projects])
                embed.add_field(
                    name="アーカイブ済みプロジェクト",
                    value=archived_text,
                    inline=False
                )
        
        return embed
    
    async def _add_project_callback(self, interaction: discord.Interaction, guild_id: int, user_id: int):
        """新規プロジェクト追加のコールバック"""
        # 新規プロジェクト追加のモーダルを表示
        modal = discord.ui.Modal(title="新規プロジェクト追加")
        
        # プロジェクト名入力フィールド
        name_input = discord.ui.TextInput(
            label="プロジェクト名",
            placeholder="新規プロジェクト",
            required=True
        )
        
        # 説明入力フィールド
        description_input = discord.ui.TextInput(
            label="説明",
            placeholder="プロジェクトの説明",
            style=discord.TextStyle.paragraph,
            required=False
        )
        
        # 確認間隔入力フィールド
        check_interval_input = discord.ui.TextInput(
            label="確認間隔（分）",
            placeholder="30",
            default="30",
            required=True
        )
        
        # デフォルトタイムアウト入力フィールド
        default_timeout_input = discord.ui.TextInput(
            label="デフォルトタイムアウト（分）",
            placeholder="60",
            default="60",
            required=True
        )
        
        # モーダルにフィールドを追加
        modal.add_item(name_input)
        modal.add_item(description_input)
        modal.add_item(check_interval_input)
        modal.add_item(default_timeout_input)
        
        # モーダル送信時の処理
        async def on_add_submit(interaction: discord.Interaction):
            try:
                # 入力値を取得
                name = name_input.value
                description = description_input.value
                
                # 確認間隔を秒に変換
                try:
                    check_interval = int(check_interval_input.value) * 60
                    if check_interval <= 0:
                        check_interval = 1800  # デフォルト30分
                except ValueError:
                    check_interval = 1800  # デフォルト30分
                
                # デフォルトタイムアウトを秒に変換
                try:
                    default_timeout = int(default_timeout_input.value) * 60
                    if default_timeout <= 0:
                        default_timeout = 3600  # デフォルト60分
                except ValueError:
                    default_timeout = 3600  # デフォルト60分
                
                # デフォルトタイムアウトが確認間隔より長い場合は調整
                if check_interval < default_timeout:
                    default_timeout = check_interval
                
                # ユーザー情報を取得
                guild_user = await UserRepository.get_guild_user(guild_id, user_id)
                
                # プロジェクトを作成
                created_project = await ProjectRepository.create_project(
                    guild_id=guild_id,
                    name=name,
                    description=description,
                    created_by_user_id=guild_user["id"] if guild_user else None,
                    default_timeout=default_timeout,
                    check_interval=check_interval,
                    require_confirmation=True,
                    require_modal=True
                )
                
                # 成功メッセージのEmbedを作成
                success_embed = discord.Embed(
                    title="✅ プロジェクト作成完了",
                    description=I18n.t("project.created", name=name),
                    color=discord.Color.green()
                )
                
                success_embed.add_field(
                    name="設定内容",
                    value=f"・確認間隔: {check_interval // 60}分\n・タイムアウト: {default_timeout // 60}分",
                    inline=False
                )
                
                # 元のメッセージを編集
                await interaction.response.edit_message(embed=success_embed, view=None)
            
            except Exception as e:
                logger.error(f"Error creating project: {str(e)}")
                error_embed = discord.Embed(
                    title="❌ エラー",
                    description=I18n.t("common.error", message=str(e)),
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
        
        modal.on_submit = on_add_submit
        await interaction.response.send_modal(modal)
    
    async def _edit_project_callback(self, interaction: discord.Interaction, projects: List[Dict[str, Any]]):
        """プロジェクト編集のコールバック"""
        # 編集対象のプロジェクト選択メニューを表示
        active_projects = [p for p in projects if not p["is_archived"]]
        
        if not active_projects:
            error_embed = discord.Embed(
                title="❌ エラー",
                description=I18n.t("project.notFound"),
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=error_embed, view=None)
            return
        
        # プロジェクト選択のセレクトメニュー
        select = discord.ui.Select(
            placeholder="編集するプロジェクトを選択",
            options=[
                discord.SelectOption(
                    label=project["name"],
                    value=str(project["id"]),
                    description=project["description"][:100] if project["description"] else None
                )
                for project in active_projects[:25]  # 最大25個
            ]
        )
        
        # セレクトメニューのコールバック
        async def on_select(interaction: discord.Interaction):
            project_id = int(select.values[0])
            
            # 選択されたプロジェクトを取得
            project = next((p for p in projects if p["id"] == project_id), None)
            
            if not project:
                error_embed = discord.Embed(
                    title="❌ エラー",
                    description=I18n.t("project.notFound"),
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
                return
            
            # プロジェクト編集用のモーダルを表示
            modal = discord.ui.Modal(title=f"プロジェクト編集: {project['name']}")
            
            # プロジェクト名入力フィールド（既存の値をデフォルトに）
            name_input = discord.ui.TextInput(
                label="プロジェクト名",
                default=project["name"],
                required=True
            )
            
            # 説明入力フィールド
            description_input = discord.ui.TextInput(
                label="説明",
                default=project["description"] or "",
                style=discord.TextStyle.paragraph,
                required=False
            )
            
            # 確認間隔入力フィールド
            check_interval_input = discord.ui.TextInput(
                label="確認間隔（分）",
                default=str(project["check_interval"] // 60),
                required=True
            )
            
            # デフォルトタイムアウト入力フィールド
            default_timeout_input = discord.ui.TextInput(
                label="デフォルトタイムアウト（分）",
                default=str(project["default_timeout"] // 60),
                required=True
            )
            
            # モーダルにフィールドを追加
            modal.add_item(name_input)
            modal.add_item(description_input)
            modal.add_item(check_interval_input)
            modal.add_item(default_timeout_input)
            
            # モーダル送信時の処理
            async def on_edit_submit(interaction: discord.Interaction):
                try:
                    # 入力値を取得
                    name = name_input.value
                    description = description_input.value
                    
                    # 確認間隔を秒に変換
                    try:
                        check_interval = int(check_interval_input.value) * 60
                        if check_interval <= 0:
                            check_interval = 1800  # デフォルト30分
                    except ValueError:
                        check_interval = 1800  # デフォルト30分
                    
                    # デフォルトタイムアウトを秒に変換
                    try:
                        default_timeout = int(default_timeout_input.value) * 60
                        if default_timeout <= 0:
                            default_timeout = 3600  # デフォルト60分
                    except ValueError:
                        default_timeout = 3600  # デフォルト60分
                    
                    # デフォルトタイムアウトが確認間隔より長い場合は調整
                    if check_interval < default_timeout:
                        default_timeout = check_interval
                    
                    # プロジェクトを更新
                    updated_project = await ProjectRepository.update_project(
                        project_id=project_id,
                        name=name,
                        description=description,
                        default_timeout=default_timeout,
                        check_interval=check_interval
                    )
                    
                    # 成功メッセージのEmbedを作成
                    success_embed = discord.Embed(
                        title="✅ プロジェクト更新完了",
                        description=I18n.t("project.updated", name=name),
                        color=discord.Color.green()
                    )
                    
                    success_embed.add_field(
                        name="更新内容",
                        value=f"・確認間隔: {check_interval // 60}分\n・タイムアウト: {default_timeout // 60}分",
                        inline=False
                    )
                    
                    # 元のメッセージを編集
                    await interaction.response.edit_message(embed=success_embed, view=None)
                
                except Exception as e:
                    logger.error(f"Error updating project: {str(e)}")
                    error_embed = discord.Embed(
                        title="❌ エラー",
                        description=I18n.t("common.error", message=str(e)),
                        color=discord.Color.red()
                    )
                    await interaction.response.edit_message(embed=error_embed, view=None)
            
            modal.on_submit = on_edit_submit
            await interaction.response.send_modal(modal)
        
        select.callback = on_select
        
        # Viewを作成してセレクトメニューを追加
        view = discord.ui.View()
        view.add_item(select)
        
        # プロジェクト選択のEmbedを作成
        select_embed = discord.Embed(
            title="📝 プロジェクト編集",
            description="編集するプロジェクトを選択してください",
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(embed=select_embed, view=view)
    
    async def _archive_project_callback(self, interaction: discord.Interaction, projects: List[Dict[str, Any]]):
        """プロジェクトアーカイブのコールバック"""
        # アーカイブ対象のプロジェクト選択メニューを表示
        active_projects = [p for p in projects if not p["is_archived"]]
        
        if not active_projects:
            error_embed = discord.Embed(
                title="❌ エラー",
                description=I18n.t("project.notFound"),
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=error_embed, view=None)
            return
        
        # プロジェクト選択のセレクトメニュー
        select = discord.ui.Select(
            placeholder="アーカイブするプロジェクトを選択",
            options=[
                discord.SelectOption(
                    label=project["name"],
                    value=str(project["id"]),
                    description=project["description"][:100] if project["description"] else None
                )
                for project in active_projects[:25]  # 最大25個
            ]
        )
        
        # セレクトメニューのコールバック
        async def on_select(interaction: discord.Interaction):
            project_id = int(select.values[0])
            
            # 選択されたプロジェクトを取得
            project = next((p for p in projects if p["id"] == project_id), None)
            
            if not project:
                error_embed = discord.Embed(
                    title="❌ エラー",
                    description=I18n.t("project.notFound"),
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
                return
            
            # 確認メッセージを表示
            embed = discord.Embed(
                title=f"プロジェクト「{project['name']}」をアーカイブしますか？",
                description="アーカイブされたプロジェクトは新規勤務登録には使用できなくなりますが、履歴からは参照可能です。",
                color=discord.Color.orange()
            )
            
            # 確認用のViewを作成
            confirm_view = discord.ui.View()
            
            # 「はい」ボタン
            yes_button = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="はい、アーカイブします",
                custom_id="confirm_archive"
            )
            
            # 「いいえ」ボタン
            no_button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="いいえ、キャンセルします",
                custom_id="cancel_archive"
            )
            
            # 「はい」ボタンのコールバック
            async def on_yes(interaction: discord.Interaction):
                try:
                    # プロジェクトをアーカイブ
                    updated_project = await ProjectRepository.update_project(
                        project_id=project_id,
                        is_archived=True
                    )
                    
                    # 成功メッセージのEmbedを作成
                    success_embed = discord.Embed(
                        title="🗂️ アーカイブ完了",
                        description=I18n.t("project.archived", name=project['name']),
                        color=discord.Color.green()
                    )
                    
                    # 元のメッセージを編集
                    await interaction.response.edit_message(embed=success_embed, view=None)
                
                except Exception as e:
                    logger.error(f"Error archiving project: {str(e)}")
                    error_embed = discord.Embed(
                        title="❌ エラー",
                        description=I18n.t("common.error", message=str(e)),
                        color=discord.Color.red()
                    )
                    await interaction.response.edit_message(embed=error_embed, view=None)
            
            # 「いいえ」ボタンのコールバック
            async def on_no(interaction: discord.Interaction):
                cancel_embed = discord.Embed(
                    title="❌ キャンセル",
                    description="アーカイブをキャンセルしました",
                    color=discord.Color.grey()
                )
                await interaction.response.edit_message(embed=cancel_embed, view=None)
            
            yes_button.callback = on_yes
            no_button.callback = on_no
            
            confirm_view.add_item(yes_button)
            confirm_view.add_item(no_button)
            
            await interaction.response.edit_message(embed=embed, view=confirm_view)
        
        select.callback = on_select
        
        # Viewを作成してセレクトメニューを追加
        view = discord.ui.View()
        view.add_item(select)
        
        # プロジェクト選択のEmbedを作成
        select_embed = discord.Embed(
            title="🗂️ プロジェクトアーカイブ",
            description="アーカイブするプロジェクトを選択してください",
            color=discord.Color.orange()
        )
        
        await interaction.response.edit_message(embed=select_embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(ProjectSettingCog(bot))