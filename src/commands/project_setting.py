import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, Any, List

from ..database.repository import ProjectRepository, UserRepository, ProjectMemberRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.project_setting')

class ProjectSettingView(discord.ui.View):
    """プロジェクト設定用のView（5分でタイムアウト）"""
    
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)  # 5分でタイムアウト
        self.guild_id = guild_id
    
    async def on_timeout(self):
        """タイムアウト時にメッセージを削除"""
        try:
            if hasattr(self, 'message'):
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
            
            # プロジェクト設定のメインパネルを表示
            await self._show_main_panel(interaction, guild_id, user_id)
        
        except Exception as e:
            logger.error(f"Error in project_setting command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", message=str(e)), ephemeral=True)
    
    async def _show_main_panel(self, interaction: discord.Interaction, guild_id: int, user_id: int):
        """メインパネルを表示"""
        # プロジェクト一覧を取得（アーカイブ済みも含む）
        projects = await ProjectRepository.get_all_projects(guild_id, include_archived=True)
        
        # メインパネルのEmbedを作成
        embed = await self._create_main_panel_embed(projects)
        
        # 操作用のViewを作成
        view = ProjectSettingView(guild_id)
        
        # 新規プロジェクト追加ボタン
        add_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="新規プロジェクト追加",
            custom_id="add_project"
        )
        
        # プロジェクト編集セレクトメニュー
        active_projects = [p for p in projects if not p["is_archived"]]
        
        if active_projects:
            edit_select = self._create_project_select_menu(
                active_projects,
                "edit_project_select",
                "編集するプロジェクトを選択"
            )
            view.add_item(edit_select)
        
        # ボタンにコールバックを設定
        add_button.callback = lambda i: self._add_project_callback(i, guild_id, user_id)
        
        # Viewにボタンを追加
        view.add_item(add_button)
        
        # メッセージを送信してViewのmessage属性に設定
        message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = message
    
    async def _create_main_panel_embed(self, projects: List[Dict[str, Any]]) -> discord.Embed:
        """メインパネルのEmbedを作成"""
        embed = discord.Embed(
            title="プロジェクト設定",
            description="新規プロジェクトの追加や既存プロジェクトの編集ができます",
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
    
    def _create_project_select_menu(self, projects: List[Dict[str, Any]], custom_id: str, placeholder: str):
        """プロジェクト選択セレクトメニューを作成"""
        options = [
            discord.SelectOption(
                label=project["name"],
                value=str(project["id"]),
                description=project["description"][:100] if project["description"] else None
            )
            for project in projects[:25]  # 最大25個
        ]
        
        select = discord.ui.Select(
            custom_id=custom_id,
            placeholder=placeholder,
            options=options
        )
        
        select.callback = self._project_select_callback
        return select
    
    async def _project_select_callback(self, interaction: discord.Interaction):
        """プロジェクト選択のコールバック"""
        custom_id = interaction.data['custom_id']
        project_id = int(interaction.data['values'][0])
        
        if custom_id == "edit_project_select":
            await self._show_project_detail_panel(interaction, project_id)
    
    async def _show_project_detail_panel(self, interaction: discord.Interaction, project_id: int):
        """プロジェクト詳細設定パネルを表示"""
        # プロジェクト情報を取得
        project = await ProjectRepository.get_project(project_id)
        if not project:
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="❌ エラー",
                    description=I18n.t("project.notFound"),
                    color=discord.Color.red()
                ),
                view=None
            )
            return
        
        # プロジェクトメンバー情報を取得
        members = await ProjectMemberRepository.get_project_members(project_id)
        
        # 詳細パネルのEmbedを作成
        embed = await self._create_project_detail_embed(project, members)
        
        # 詳細パネルのViewを作成
        view = ProjectSettingView(interaction.guild_id)
        
        # 概要編集ボタン
        edit_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="概要編集",
            custom_id="edit_project_info"
        )
        
        # アーカイブボタン
        archive_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="プロジェクトアーカイブ",
            custom_id="archive_project"
        )
        
        # 戻るボタン
        back_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="戻る",
            custom_id="back_to_main"
        )
        
        # メンバー管理セレクトメニュー
        guild_users = await UserRepository.get_all_guild_users(interaction.guild_id)
        if guild_users:
            member_select = self._create_member_select_menu(guild_users, project_id)
            view.add_item(member_select)
        
        # ボタンコールバック設定
        edit_button.callback = lambda i: self._edit_project_info_callback(i, project)
        archive_button.callback = lambda i: self._archive_project_callback(i, project)
        back_button.callback = lambda i: self._back_to_main_callback(i)
        
        view.add_item(edit_button)
        view.add_item(archive_button)
        view.add_item(back_button)
        
        # メッセージを更新
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message
    
    async def _create_project_detail_embed(self, project: Dict[str, Any], members: List[Dict[str, Any]]) -> discord.Embed:
        """プロジェクト詳細パネルのEmbedを作成"""
        embed = discord.Embed(
            title=f"📋 プロジェクト設定: {project['name']}",
            color=discord.Color.blue()
        )
        
        # プロジェクト情報
        embed.add_field(
            name="説明",
            value=project["description"] or "なし",
            inline=False
        )
        
        # 設定情報
        check_interval_minutes = project["check_interval"] // 60
        timeout_minutes = project["default_timeout"] // 60
        
        settings_text = f"・確認間隔: {check_interval_minutes}分\n・タイムアウト: {timeout_minutes}分"
        if project["require_confirmation"]:
            settings_text += "\n・定期確認: 有効"
        else:
            settings_text += "\n・定期確認: 無効"
        
        if project["require_modal"]:
            settings_text += "\n・要約入力: 必須"
        else:
            settings_text += "\n・要約入力: 任意"
        
        embed.add_field(
            name="設定",
            value=settings_text,
            inline=False
        )
        
        # メンバー一覧
        if members:
            member_text = "\n".join([f"・{member['user_name']}" for member in members])
            embed.add_field(
                name=f"メンバー ({len(members)}人)",
                value=member_text,
                inline=False
            )
        else:
            embed.add_field(
                name="メンバー (0人)",
                value="メンバーがいません",
                inline=False
            )
        
        return embed
    
    def _create_member_select_menu(self, guild_users: List[Dict[str, Any]], project_id: int):
        """メンバー管理セレクトメニューを作成"""
        options = [
            discord.SelectOption(
                label=user["user_name"],
                value=str(user["id"]),
                description=f"User ID: {user['user_id']}"
            )
            for user in guild_users[:25]  # 最大25個
        ]
        
        select = discord.ui.Select(
            custom_id=f"member_select_{project_id}",
            placeholder="メンバーを追加/削除",
            options=options
        )
        
        select.callback = self._member_select_callback
        return select
    
    async def _member_select_callback(self, interaction: discord.Interaction):
        """メンバー選択のコールバック"""
        custom_id = interaction.data['custom_id']
        project_id = int(custom_id.split('_')[-1])
        selected_guild_user_ids = [int(x) for x in interaction.data['values']]
        
        # 選択されたユーザーを分類
        to_add = []
        to_remove = []
        
        for guild_user_id in selected_guild_user_ids:
            is_member = await ProjectMemberRepository.is_project_member(project_id, guild_user_id)
            if is_member:
                to_remove.append(guild_user_id)
            else:
                to_add.append(guild_user_id)
        
        # 確認画面を表示
        await self._show_member_confirmation(interaction, project_id, to_add, to_remove)
    
    async def _show_member_confirmation(self, interaction: discord.Interaction, project_id: int, to_add: List[int], to_remove: List[int]):
        """メンバー変更確認画面を表示"""
        project = await ProjectRepository.get_project(project_id)
        
        embed = discord.Embed(
            title=f"メンバー変更確認: {project['name']}",
            color=discord.Color.orange()
        )
        
        # 追加するメンバー
        if to_add:
            add_users = []
            for guild_user_id in to_add:
                user_info = await UserRepository.get_all_guild_users(interaction.guild_id)
                user = next((u for u in user_info if u['id'] == guild_user_id), None)
                if user:
                    add_users.append(user['user_name'])
            
            if add_users:
                embed.add_field(
                    name="追加するメンバー",
                    value="\n".join([f"・{name}" for name in add_users]),
                    inline=False
                )
        
        # 削除するメンバー
        if to_remove:
            remove_users = []
            for guild_user_id in to_remove:
                user_info = await UserRepository.get_all_guild_users(interaction.guild_id)
                user = next((u for u in user_info if u['id'] == guild_user_id), None)
                if user:
                    remove_users.append(user['user_name'])
            
            if remove_users:
                embed.add_field(
                    name="削除するメンバー",
                    value="\n".join([f"・{name}" for name in remove_users]),
                    inline=False
                )
        
        # 変更がない場合
        if not to_add and not to_remove:
            embed.description = "変更はありません"
        
        # 確認用のViewを作成
        view = ProjectSettingView(interaction.guild_id)
        
        # 確認ボタン（変更がある場合のみ）
        if to_add or to_remove:
            confirm_button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="確認",
                custom_id="confirm_member_changes"
            )
            confirm_button.callback = lambda i: self._confirm_member_changes(i, project_id, to_add, to_remove)
            view.add_item(confirm_button)
        
        # 戻るボタン
        back_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="戻る",
            custom_id="back_to_project_detail"
        )
        back_button.callback = lambda i: self._show_project_detail_panel(i, project_id)
        view.add_item(back_button)
        
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message
    
    async def _confirm_member_changes(self, interaction: discord.Interaction, project_id: int, to_add: List[int], to_remove: List[int]):
        """メンバー変更を実行"""
        try:
            # メンバーを追加
            for guild_user_id in to_add:
                await ProjectMemberRepository.add_project_member(project_id, guild_user_id)
            
            # メンバーを削除
            for guild_user_id in to_remove:
                await ProjectMemberRepository.remove_project_member(project_id, guild_user_id)
            
            # 成功メッセージを表示して詳細画面に戻る
            await self._show_project_detail_panel(interaction, project_id)
        
        except Exception as e:
            logger.error(f"Error updating project members: {str(e)}")
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="❌ エラー",
                    description=I18n.t("common.error", message=str(e)),
                    color=discord.Color.red()
                ),
                view=None
            )
    
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
                if check_interval > default_timeout:
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
    
    async def _edit_project_info_callback(self, interaction: discord.Interaction, project: Dict[str, Any]):
        """プロジェクト概要編集のコールバック"""
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
                if check_interval > default_timeout:
                    default_timeout = check_interval
                
                # プロジェクトを更新
                updated_project = await ProjectRepository.update_project(
                    project_id=project["id"],
                    name=name,
                    description=description,
                    default_timeout=default_timeout,
                    check_interval=check_interval
                )
                
                # 詳細画面に戻る
                await self._show_project_detail_panel(interaction, project["id"])
            
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
    
    async def _archive_project_callback(self, interaction: discord.Interaction, project: Dict[str, Any]):
        """プロジェクトアーカイブのコールバック"""
        # 確認メッセージを表示
        embed = discord.Embed(
            title=f"プロジェクト「{project['name']}」をアーカイブしますか？",
            description="アーカイブされたプロジェクトは新規勤務登録には使用できなくなりますが、履歴からは参照可能です。",
            color=discord.Color.orange()
        )
        
        # 確認用のViewを作成
        view = ProjectSettingView(interaction.guild_id)
        
        # 「はい」ボタン
        yes_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="はい、アーカイブします",
            custom_id="confirm_archive"
        )
        
        # 「いいえ」ボタン
        no_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="いいえ、戻ります",
            custom_id="cancel_archive"
        )
        
        # 「はい」ボタンのコールバック
        async def on_yes(interaction: discord.Interaction):
            try:
                # プロジェクトをアーカイブ
                await ProjectRepository.update_project(
                    project_id=project["id"],
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
            await self._show_project_detail_panel(interaction, project["id"])
        
        yes_button.callback = on_yes
        no_button.callback = on_no
        
        view.add_item(yes_button)
        view.add_item(no_button)
        
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message
    
    async def _back_to_main_callback(self, interaction: discord.Interaction):
        """メインパネルに戻るコールバック"""
        await self._show_main_panel(interaction, interaction.guild_id, interaction.user.id)

async def setup(bot: commands.Bot):
    await bot.add_cog(ProjectSettingCog(bot))