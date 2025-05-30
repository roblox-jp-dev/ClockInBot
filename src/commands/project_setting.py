import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, Any, List

from ..database.repository import ProjectRepository, UserRepository, ProjectMemberRepository, GuildRepository
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

class ProjectCreationView(discord.ui.View):
    """プロジェクト作成用のView"""
    
    def __init__(self, guild_id: int, temp_project_data: Dict[str, Any]):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.temp_project_data = temp_project_data
    
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
        
        # 権限チェック
        if not interaction.user.guild_permissions.administrator:
            # サーバー設定から言語を取得
            guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
            locale = guild_settings["locale"] if guild_settings else "ja"
            await interaction.response.send_message(
                I18n.t("common.noPermission", locale),
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = interaction.guild_id
            user_id = interaction.user.id
            
            # プロジェクト設定のメインパネルを表示
            await self._show_main_panel(interaction, guild_id, user_id)
        
        except Exception as e:
            logger.error(f"Error in project_setting command: {str(e)}")
            # サーバー設定から言語を取得
            guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
            locale = guild_settings["locale"] if guild_settings else "ja"
            await interaction.followup.send(I18n.t("common.error", locale, message=str(e)), ephemeral=True)
    
    async def _show_main_panel(self, interaction: discord.Interaction, guild_id: int, user_id: int):
        """メインパネルを表示"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # プロジェクト一覧を取得（アーカイブ済みも含む）
        projects = await ProjectRepository.get_all_projects(guild_id, include_archived=True)
        
        # メインパネルのEmbedを作成
        embed = await self._create_main_panel_embed(projects, locale)
        
        # 操作用のViewを作成
        view = ProjectSettingView(guild_id)
        
        # 新規プロジェクト追加ボタン
        add_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=I18n.t("project.addNew", locale),
            custom_id="add_project",
            row=0
        )
        
        # プロジェクト編集セレクトメニュー
        active_projects = [p for p in projects if not p["is_archived"]]
        
        if active_projects:
            edit_select = self._create_project_select_menu(
                active_projects,
                "edit_project_select",
                I18n.t("project.editProject", locale),
                locale
            )
            edit_select.row = 1
            view.add_item(edit_select)
        
        # ボタンにコールバックを設定
        add_button.callback = lambda i: self._add_project_callback(i, guild_id, user_id)
        
        # Viewにボタンを追加
        view.add_item(add_button)
        
        # メッセージを送信してViewのmessage属性に設定
        message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = message
    
    async def _create_main_panel_embed(self, projects: List[Dict[str, Any]], locale: str) -> discord.Embed:
        """メインパネルのEmbedを作成"""
        embed = discord.Embed(
            title=I18n.t("project.settings", locale),
            description=I18n.t("project.managementDescription", locale),
            color=discord.Color.blue()
        )
        
        # 既存プロジェクトがある場合は一覧を表示
        if projects:
            active_projects = [p for p in projects if not p["is_archived"]]
            archived_projects = [p for p in projects if p["is_archived"]]
            
            if active_projects:
                active_text = "\n".join([f"・{p['name']}" for p in active_projects])
                embed.add_field(
                    name=I18n.t("project.activeProjects", locale),
                    value=active_text,
                    inline=False
                )
            
            if archived_projects:
                archived_text = "\n".join([f"・{p['name']}" for p in archived_projects])
                embed.add_field(
                    name=I18n.t("project.archivedProjects", locale),
                    value=archived_text,
                    inline=False
                )
        
        return embed
    
    def _create_project_select_menu(self, projects: List[Dict[str, Any]], custom_id: str, placeholder: str, locale: str):
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
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # プロジェクト情報を取得
        project = await ProjectRepository.get_project(project_id)
        if not project:
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("project.notFound", locale),
                    color=discord.Color.red()
                ),
                view=None
            )
            return
        
        # プロジェクトメンバー情報を取得
        members = await ProjectMemberRepository.get_project_members(project_id)
        
        # 詳細パネルのEmbedを作成
        embed = await self._create_project_detail_embed(project, members, locale)
        
        # 詳細パネルのViewを作成
        view = ProjectSettingView(interaction.guild_id)
        
        # 1段目：概要編集ボタン、タイミング設定ボタン
        edit_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=I18n.t("project.editInfo", locale),
            custom_id="edit_project_info",
            row=0
        )
        
        timing_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=I18n.t("project.editTiming", locale),
            custom_id="edit_timing",
            disabled=not project["require_confirmation"],
            row=0
        )
        
        # 2段目：定期確認切り替えボタン、要約入力切り替えボタン
        confirmation_style = discord.ButtonStyle.success if project["require_confirmation"] else discord.ButtonStyle.secondary
        confirmation_label = f"{I18n.t('project.confirmationToggle', locale)}: {I18n.t('project.on', locale) if project['require_confirmation'] else I18n.t('project.off', locale)}"
        confirmation_button = discord.ui.Button(
            style=confirmation_style,
            label=confirmation_label,
            custom_id="toggle_confirmation",
            row=1
        )
        
        modal_style = discord.ButtonStyle.success if project["require_modal"] else discord.ButtonStyle.secondary
        modal_label = f"{I18n.t('project.modalToggle', locale)}: {I18n.t('project.on', locale) if project['require_modal'] else I18n.t('project.off', locale)}"
        modal_button = discord.ui.Button(
            style=modal_style,
            label=modal_label,
            custom_id="toggle_modal",
            disabled=not project["require_confirmation"],
            row=1
        )
        
        # 3段目：メンバー管理用のUserSelect
        user_select = discord.ui.UserSelect(
            placeholder=I18n.t("project.addRemoveMembers", locale),
            min_values=1,
            max_values=25,
            custom_id=f"user_select_{project_id}",
            row=2
        )
        user_select.callback = self._user_select_callback
        
        # 4段目：アーカイブボタン
        archive_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=I18n.t("project.archive", locale),
            custom_id="archive_project",
            row=3
        )
        
        # ボタンコールバック設定
        edit_button.callback = lambda i: self._edit_project_info_callback(i, project)
        timing_button.callback = lambda i: self._edit_timing_callback(i, project)
        confirmation_button.callback = lambda i: self._toggle_confirmation_callback(i, project)
        modal_button.callback = lambda i: self._toggle_modal_callback(i, project)
        archive_button.callback = lambda i: self._archive_project_callback(i, project)
        
        # Viewにボタンを追加
        view.add_item(edit_button)
        view.add_item(timing_button)
        view.add_item(confirmation_button)
        view.add_item(modal_button)
        view.add_item(user_select)
        view.add_item(archive_button)
        
        # メッセージを更新
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message
    
    async def _create_project_detail_embed(self, project: Dict[str, Any], members: List[Dict[str, Any]], locale: str) -> discord.Embed:
        """プロジェクト詳細パネルのEmbedを作成"""
        embed = discord.Embed(
            title=f"📋 {I18n.t('project.settings', locale)}: {project['name']}",
            color=discord.Color.blue()
        )
        
        # プロジェクト情報
        embed.add_field(
            name=I18n.t("project.description", locale),
            value=project["description"] or I18n.t("common.notFound", locale),
            inline=False
        )
        
        # 設定情報
        if project["require_confirmation"]:
            check_interval_minutes = project["check_interval"] // 60
            timeout_minutes = project["default_timeout"] // 60
            
            settings_text = f"・{I18n.t('project.confirmationToggle', locale)}: {I18n.t('project.enabled', locale)}\n・{I18n.t('project.checkInterval', locale)}: {check_interval_minutes}分\n・{I18n.t('project.defaultTimeout', locale)}: {timeout_minutes}分"
            
            if project["require_modal"]:
                settings_text += f"\n・{I18n.t('project.modalToggle', locale)}: {I18n.t('project.required', locale)}"
            else:
                settings_text += f"\n・{I18n.t('project.modalToggle', locale)}: {I18n.t('project.optional', locale)}"
        else:
            settings_text = f"・{I18n.t('project.confirmationToggle', locale)}: {I18n.t('project.disabled', locale)}"
        
        embed.add_field(
            name=I18n.t("project.settingsContent", locale),
            value=settings_text,
            inline=False
        )
        
        # メンバー一覧
        if members:
            member_text = "\n".join([f"・{member['user_name']}" for member in members])
            embed.add_field(
                name=f"{I18n.t('project.members', locale)} ({len(members)}人)",
                value=member_text,
                inline=False
            )
        else:
            embed.add_field(
                name=f"{I18n.t('project.members', locale)} (0人)",
                value=I18n.t("project.noMembers", locale),
                inline=False
            )
        
        return embed
    
    async def _user_select_callback(self, interaction: discord.Interaction):
        """ユーザー選択のコールバック"""
        custom_id = interaction.data['custom_id']
        project_id = int(custom_id.split('_')[-1])
        selected_users = interaction.data['values']
        
        # 選択されたユーザーのguild_user_idを取得
        selected_guild_user_ids = []
        for user_id in selected_users:
            guild_user = await UserRepository.get_guild_user(interaction.guild_id, int(user_id))
            if guild_user:
                selected_guild_user_ids.append(guild_user["id"])
        
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
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        project = await ProjectRepository.get_project(project_id)
        
        embed = discord.Embed(
            title=f"{I18n.t('project.memberChanges', locale)}: {project['name']}",
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
                    name=I18n.t("project.membersToAdd", locale),
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
                    name=I18n.t("project.membersToRemove", locale),
                    value="\n".join([f"・{name}" for name in remove_users]),
                    inline=False
                )
        
        # 変更がない場合
        if not to_add and not to_remove:
            embed.description = I18n.t("project.noChanges", locale)
        
        # 確認用のViewを作成
        view = ProjectSettingView(interaction.guild_id)
        
        # 確認ボタン（変更がある場合のみ）
        if to_add or to_remove:
            confirm_button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=I18n.t("project.confirm", locale),
                custom_id="confirm_member_changes",
                row=0
            )
            confirm_button.callback = lambda i: self._confirm_member_changes(i, project_id, to_add, to_remove)
            view.add_item(confirm_button)
        
        # 戻るボタン
        back_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=I18n.t("project.back", locale),
            custom_id="back_to_project_detail",
            row=0
        )
        back_button.callback = lambda i: self._show_project_detail_panel(i, project_id)
        view.add_item(back_button)
        
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message
    
    async def _confirm_member_changes(self, interaction: discord.Interaction, project_id: int, to_add: List[int], to_remove: List[int]):
        """メンバー変更を実行"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
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
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("common.error", locale, message=str(e)),
                    color=discord.Color.red()
                ),
                view=None
            )
    
    async def _toggle_confirmation_callback(self, interaction: discord.Interaction, project: Dict[str, Any]):
        """定期確認の切り替えコールバック"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        try:
            new_value = not project["require_confirmation"]
            
            # 定期確認をオフにする場合は要約入力も強制的にオフ
            require_modal = project["require_modal"] if new_value else False
            
            await ProjectRepository.update_project(
                project_id=project["id"],
                require_confirmation=new_value,
                require_modal=require_modal
            )
            
            # 詳細画面を再表示
            await self._show_project_detail_panel(interaction, project["id"])
        
        except Exception as e:
            logger.error(f"Error toggling confirmation: {str(e)}")
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("common.error", locale, message=str(e)),
                    color=discord.Color.red()
                ),
                view=None
            )
    
    async def _toggle_modal_callback(self, interaction: discord.Interaction, project: Dict[str, Any]):
        """要約入力の切り替えコールバック"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        try:
            new_value = not project["require_modal"]
            
            await ProjectRepository.update_project(
                project_id=project["id"],
                require_modal=new_value
            )
            
            # 詳細画面を再表示
            await self._show_project_detail_panel(interaction, project["id"])
        
        except Exception as e:
            logger.error(f"Error toggling modal: {str(e)}")
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("common.error", locale, message=str(e)),
                    color=discord.Color.red()
                ),
                view=None
            )
    
    async def _edit_timing_callback(self, interaction: discord.Interaction, project: Dict[str, Any]):
        """タイミング設定編集のコールバック"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # タイミング設定編集用のモーダルを表示
        modal = discord.ui.Modal(title=f"{I18n.t('project.editTiming', locale)}: {project['name']}")
        
        # 確認間隔入力フィールド
        check_interval_input = discord.ui.TextInput(
            label=I18n.t("project.checkInterval", locale),
            default=str(project["check_interval"] // 60),
            required=True
        )
        
        # デフォルトタイムアウト入力フィールド
        default_timeout_input = discord.ui.TextInput(
            label=I18n.t("project.defaultTimeout", locale),
            default=str(project["default_timeout"] // 60),
            required=True
        )
        
        # モーダルにフィールドを追加
        modal.add_item(check_interval_input)
        modal.add_item(default_timeout_input)
        
        # モーダル送信時の処理
        async def on_timing_submit(interaction: discord.Interaction):
            try:
                # 確認間隔を秒に変換
                try:
                    check_interval = int(check_interval_input.value) * 60
                    if check_interval <= 0:
                        check_interval = 3600  # デフォルト60分
                except ValueError:
                    check_interval = 3600  # デフォルト60分
                
                # デフォルトタイムアウトを秒に変換
                try:
                    default_timeout = int(default_timeout_input.value) * 60
                    if default_timeout <= 0:
                        default_timeout = 900  # デフォルト15分
                except ValueError:
                    default_timeout = 900  # デフォルト15分
                
                # デフォルトタイムアウトが確認間隔より長い場合は調整
                if default_timeout > check_interval:
                    default_timeout = check_interval
                
                # プロジェクトを更新
                await ProjectRepository.update_project(
                    project_id=project["id"],
                    default_timeout=default_timeout,
                    check_interval=check_interval
                )
                
                # 詳細画面に戻る
                await self._show_project_detail_panel(interaction, project["id"])
            
            except Exception as e:
                logger.error(f"Error updating timing: {str(e)}")
                error_embed = discord.Embed(
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("common.error", locale, message=str(e)),
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
        
        modal.on_submit = on_timing_submit
        await interaction.response.send_modal(modal)
    
    async def _add_project_callback(self, interaction: discord.Interaction, guild_id: int, user_id: int):
        """新規プロジェクト追加のコールバック"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # 新規プロジェクト追加のモーダルを表示（名前と説明のみ）
        modal = discord.ui.Modal(title=I18n.t("project.creation", locale))
        
        # プロジェクト名入力フィールド
        name_input = discord.ui.TextInput(
            label=I18n.t("project.name", locale),
            placeholder=I18n.t("project.newProject", locale),
            required=True
        )
        
        # 説明入力フィールド
        description_input = discord.ui.TextInput(
            label=I18n.t("project.description", locale),
            placeholder=I18n.t("project.projectDescription", locale),
            style=discord.TextStyle.paragraph,
            required=False
        )
        
        # モーダルにフィールドを追加
        modal.add_item(name_input)
        modal.add_item(description_input)
        
        # モーダル送信時の処理
        async def on_basic_info_submit(interaction: discord.Interaction):
            try:
                # 一時的なプロジェクトデータを作成
                temp_project_data = {
                    "name": name_input.value,
                    "description": description_input.value,
                    "require_confirmation": True,  # デフォルト値
                    "require_modal": True,  # デフォルト値
                    "check_interval": 3600,  # デフォルト60分
                    "default_timeout": 900  # デフォルト15分
                }
                
                # プロジェクト作成プレビュー画面を表示
                await self._show_project_creation_preview(interaction, guild_id, user_id, temp_project_data)
            
            except Exception as e:
                logger.error(f"Error in basic info submit: {str(e)}")
                error_embed = discord.Embed(
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("common.error", locale, message=str(e)),
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
        
        modal.on_submit = on_basic_info_submit
        await interaction.response.send_modal(modal)
    
    async def _show_project_creation_preview(self, interaction: discord.Interaction, guild_id: int, user_id: int, temp_project_data: Dict[str, Any]):
        """プロジェクト作成プレビュー画面を表示"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # プレビューEmbedを作成
        embed = await self._create_project_creation_preview_embed(temp_project_data, locale)
        
        # プロジェクト作成用のViewを作成
        view = ProjectCreationView(guild_id, temp_project_data)
        
        # 1段目：概要編集ボタン、タイミング設定ボタン
        edit_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=I18n.t("project.editInfo", locale),
            custom_id="edit_creation_info",
            row=0
        )
        
        timing_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=I18n.t("project.editTiming", locale),
            custom_id="edit_creation_timing",
            disabled=not temp_project_data["require_confirmation"],
            row=0
        )
        
        # 2段目：定期確認切り替えボタン、要約入力切り替えボタン
        confirmation_style = discord.ButtonStyle.success if temp_project_data["require_confirmation"] else discord.ButtonStyle.secondary
        confirmation_label = f"{I18n.t('project.confirmationToggle', locale)}: {I18n.t('project.on', locale) if temp_project_data['require_confirmation'] else I18n.t('project.off', locale)}"
        confirmation_button = discord.ui.Button(
            style=confirmation_style,
            label=confirmation_label,
            custom_id="toggle_creation_confirmation",
            row=1
        )
        
        modal_style = discord.ButtonStyle.success if temp_project_data["require_modal"] else discord.ButtonStyle.secondary
        modal_label = f"{I18n.t('project.modalToggle', locale)}: {I18n.t('project.on', locale) if temp_project_data['require_modal'] else I18n.t('project.off', locale)}"
        modal_button = discord.ui.Button(
            style=modal_style,
            label=modal_label,
            custom_id="toggle_creation_modal",
            disabled=not temp_project_data["require_confirmation"],
            row=1
        )
        
        # 3段目：作成ボタン
        create_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=I18n.t("project.create", locale),
            custom_id="create_project",
            row=2
        )
        
        # ボタンコールバック設定
        edit_button.callback = lambda i: self._edit_creation_info_callback(i, temp_project_data)
        timing_button.callback = lambda i: self._edit_creation_timing_callback(i, guild_id, user_id, temp_project_data)
        confirmation_button.callback = lambda i: self._toggle_creation_confirmation_callback(i, guild_id, user_id, temp_project_data)
        modal_button.callback = lambda i: self._toggle_creation_modal_callback(i, guild_id, user_id, temp_project_data)
        create_button.callback = lambda i: self._create_project_callback(i, guild_id, user_id, temp_project_data)
        
        # Viewにボタンを追加
        view.add_item(edit_button)
        view.add_item(timing_button)
        view.add_item(confirmation_button)
        view.add_item(modal_button)
        view.add_item(create_button)
        
        # メッセージを更新
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message
    
    async def _create_project_creation_preview_embed(self, temp_project_data: Dict[str, Any], locale: str) -> discord.Embed:
        """プロジェクト作成プレビューのEmbedを作成"""
        embed = discord.Embed(
            title=f"📋 {I18n.t('project.creationPreview', locale)}: {temp_project_data['name']}",
            description=I18n.t("project.previewDescription", locale),
            color=discord.Color.orange()
        )
        
        # プロジェクト情報
        embed.add_field(
            name=I18n.t("project.description", locale),
            value=temp_project_data["description"] or I18n.t("common.notFound", locale),
            inline=False
        )
        
        # 設定情報
        if temp_project_data["require_confirmation"]:
            check_interval_minutes = temp_project_data["check_interval"] // 60
            timeout_minutes = temp_project_data["default_timeout"] // 60
            
            settings_text = f"・{I18n.t('project.confirmationToggle', locale)}: {I18n.t('project.enabled', locale)}\n・{I18n.t('project.checkInterval', locale)}: {check_interval_minutes}分\n・{I18n.t('project.defaultTimeout', locale)}: {timeout_minutes}分"
            
            if temp_project_data["require_modal"]:
                settings_text += f"\n・{I18n.t('project.modalToggle', locale)}: {I18n.t('project.required', locale)}"
            else:
                settings_text += f"\n・{I18n.t('project.modalToggle', locale)}: {I18n.t('project.optional', locale)}"
        else:
            settings_text = f"・{I18n.t('project.confirmationToggle', locale)}: {I18n.t('project.disabled', locale)}"
        
        embed.add_field(
            name=I18n.t("project.settingsContent", locale),
            value=settings_text,
            inline=False
        )
        
        return embed
    
    async def _edit_creation_info_callback(self, interaction: discord.Interaction, temp_project_data: Dict[str, Any]):
        """作成時の概要編集コールバック"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # 概要編集用のモーダルを表示
        modal = discord.ui.Modal(title=f"{I18n.t('project.editInfo', locale)}: {temp_project_data['name']}")
        
        # プロジェクト名入力フィールド（既存の値をデフォルトに）
        name_input = discord.ui.TextInput(
            label=I18n.t("project.name", locale),
            default=temp_project_data["name"],
            required=True
        )
        
        # 説明入力フィールド
        description_input = discord.ui.TextInput(
            label=I18n.t("project.description", locale),
            default=temp_project_data["description"] or "",
            style=discord.TextStyle.paragraph,
            required=False
        )
        
        # モーダルにフィールドを追加
        modal.add_item(name_input)
        modal.add_item(description_input)
        
        # モーダル送信時の処理
        async def on_edit_creation_submit(interaction: discord.Interaction):
            try:
                # 一時データを更新
                temp_project_data["name"] = name_input.value
                temp_project_data["description"] = description_input.value
                
                # プレビュー画面を再表示
                await self._show_project_creation_preview(interaction, interaction.guild_id, interaction.user.id, temp_project_data)
            
            except Exception as e:
                logger.error(f"Error updating creation info: {str(e)}")
                error_embed = discord.Embed(
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("common.error", locale, message=str(e)),
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
        
        modal.on_submit = on_edit_creation_submit
        await interaction.response.send_modal(modal)
    
    async def _toggle_creation_confirmation_callback(self, interaction: discord.Interaction, guild_id: int, user_id: int, temp_project_data: Dict[str, Any]):
        """作成時の定期確認切り替えコールバック"""
        # 定期確認を切り替え
        temp_project_data["require_confirmation"] = not temp_project_data["require_confirmation"]
        
        # 定期確認をオフにする場合は要約入力も強制的にオフ
        if not temp_project_data["require_confirmation"]:
            temp_project_data["require_modal"] = False
        
        # プレビュー画面を再表示
        await self._show_project_creation_preview(interaction, guild_id, user_id, temp_project_data)
    
    async def _toggle_creation_modal_callback(self, interaction: discord.Interaction, guild_id: int, user_id: int, temp_project_data: Dict[str, Any]):
        """作成時の要約入力切り替えコールバック"""
        # 要約入力を切り替え
        temp_project_data["require_modal"] = not temp_project_data["require_modal"]
        
        # プレビュー画面を再表示
        await self._show_project_creation_preview(interaction, guild_id, user_id, temp_project_data)
    
    async def _edit_creation_timing_callback(self, interaction: discord.Interaction, guild_id: int, user_id: int, temp_project_data: Dict[str, Any]):
        """作成時のタイミング設定編集コールバック"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # タイミング設定編集用のモーダルを表示
        modal = discord.ui.Modal(title=f"{I18n.t('project.editTiming', locale)}: {temp_project_data['name']}")
        
        # 確認間隔入力フィールド
        check_interval_input = discord.ui.TextInput(
            label=I18n.t("project.checkInterval", locale),
            default=str(temp_project_data["check_interval"] // 60),
            required=True
        )
        
        # デフォルトタイムアウト入力フィールド
        default_timeout_input = discord.ui.TextInput(
            label=I18n.t("project.defaultTimeout", locale),
            default=str(temp_project_data["default_timeout"] // 60),
            required=True
        )
        
        # モーダルにフィールドを追加
        modal.add_item(check_interval_input)
        modal.add_item(default_timeout_input)
        
        # モーダル送信時の処理
        async def on_creation_timing_submit(interaction: discord.Interaction):
            try:
                # 確認間隔を秒に変換
                try:
                    check_interval = int(check_interval_input.value) * 60
                    if check_interval <= 0:
                        check_interval = 3600  # デフォルト60分
                except ValueError:
                    check_interval = 3600  # デフォルト60分
                
                # デフォルトタイムアウトを秒に変換
                try:
                    default_timeout = int(default_timeout_input.value) * 60
                    if default_timeout <= 0:
                        default_timeout = 900  # デフォルト15分
                except ValueError:
                    default_timeout = 900  # デフォルト15分
                
                # デフォルトタイムアウトが確認間隔より長い場合は調整
                if default_timeout > check_interval:
                    default_timeout = check_interval
                
                # 一時データを更新
                temp_project_data["check_interval"] = check_interval
                temp_project_data["default_timeout"] = default_timeout
                
                # プレビュー画面を再表示
                await self._show_project_creation_preview(interaction, guild_id, user_id, temp_project_data)
            
            except Exception as e:
                logger.error(f"Error updating creation timing: {str(e)}")
                error_embed = discord.Embed(
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("common.error", locale, message=str(e)),
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
        
        modal.on_submit = on_creation_timing_submit
        await interaction.response.send_modal(modal)
    
    async def _create_project_callback(self, interaction: discord.Interaction, guild_id: int, user_id: int, temp_project_data: Dict[str, Any]):
        """プロジェクト作成実行コールバック"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        try:
            # ユーザー情報を取得
            guild_user = await UserRepository.get_guild_user(guild_id, user_id)
            
            # プロジェクトを作成
            created_project = await ProjectRepository.create_project(
                guild_id=guild_id,
                name=temp_project_data["name"],
                description=temp_project_data["description"],
                created_by_user_id=guild_user["id"] if guild_user else None,
                default_timeout=temp_project_data["default_timeout"],
                check_interval=temp_project_data["check_interval"],
                require_confirmation=temp_project_data["require_confirmation"],
                require_modal=temp_project_data["require_modal"]
            )
            
            # 成功メッセージのEmbedを作成
            success_embed = discord.Embed(
                title="✅ " + I18n.t("project.creationComplete", locale),
                description=I18n.t("project.created", locale, name=temp_project_data["name"]),
                color=discord.Color.green()
            )
            
            if temp_project_data["require_confirmation"]:
                success_embed.add_field(
                    name=I18n.t("project.settingsContent", locale),
                    value=f"・{I18n.t('project.checkInterval', locale)}: {temp_project_data['check_interval'] // 60}分\n・{I18n.t('project.defaultTimeout', locale)}: {temp_project_data['default_timeout'] // 60}分",
                    inline=False
                )
            else:
                success_embed.add_field(
                    name=I18n.t("project.settingsContent", locale),
                    value=f"・{I18n.t('project.confirmationToggle', locale)}: {I18n.t('project.disabled', locale)}",
                    inline=False
                )
            
            # 元のメッセージを編集
            await interaction.response.edit_message(embed=success_embed, view=None)
        
        except Exception as e:
            logger.error(f"Error creating project: {str(e)}")
            error_embed = discord.Embed(
                title="❌ " + I18n.t("common.error", locale),
                description=I18n.t("common.error", locale, message=str(e)),
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=error_embed, view=None)
    
    async def _edit_project_info_callback(self, interaction: discord.Interaction, project: Dict[str, Any]):
        """プロジェクト概要編集のコールバック"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # プロジェクト編集用のモーダルを表示
        modal = discord.ui.Modal(title=f"{I18n.t('project.editInfo', locale)}: {project['name']}")
        
        # プロジェクト名入力フィールド（既存の値をデフォルトに）
        name_input = discord.ui.TextInput(
            label=I18n.t("project.name", locale),
            default=project["name"],
            required=True
        )
        
        # 説明入力フィールド
        description_input = discord.ui.TextInput(
            label=I18n.t("project.description", locale),
            default=project["description"] or "",
            style=discord.TextStyle.paragraph,
            required=False
        )
        
        # モーダルにフィールドを追加
        modal.add_item(name_input)
        modal.add_item(description_input)
        
        # モーダル送信時の処理
        async def on_edit_submit(interaction: discord.Interaction):
            try:
                # 入力値を取得
                name = name_input.value
                description = description_input.value
                
                # プロジェクトを更新
                updated_project = await ProjectRepository.update_project(
                    project_id=project["id"],
                    name=name,
                    description=description
                )
                
                # 詳細画面に戻る
                await self._show_project_detail_panel(interaction, project["id"])
            
            except Exception as e:
                logger.error(f"Error updating project: {str(e)}")
                error_embed = discord.Embed(
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("common.error", locale, message=str(e)),
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
        
        modal.on_submit = on_edit_submit
        await interaction.response.send_modal(modal)
    
    async def _archive_project_callback(self, interaction: discord.Interaction, project: Dict[str, Any]):
        """プロジェクトアーカイブのコールバック"""
        # サーバー設定から言語を取得
        guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
        locale = guild_settings["locale"] if guild_settings else "ja"
        
        # 確認メッセージを表示
        embed = discord.Embed(
            title=I18n.t("project.archiveConfirm", locale, name=project['name']),
            description=I18n.t("project.archiveDescription", locale),
            color=discord.Color.orange()
        )
        
        # 確認用のViewを作成
        view = ProjectSettingView(interaction.guild_id)
        
        # 「はい」ボタン
        yes_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=I18n.t("project.archiveYes", locale),
            custom_id="confirm_archive",
            row=0
        )
        
        # 「いいえ」ボタン
        no_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=I18n.t("project.archiveNo", locale),
            custom_id="cancel_archive",
            row=0
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
                    title="🗂️ " + I18n.t("project.archiveComplete", locale),
                    description=I18n.t("project.archived", locale, name=project['name']),
                    color=discord.Color.green()
                )
                
                # 元のメッセージを編集
                await interaction.response.edit_message(embed=success_embed, view=None)
            
            except Exception as e:
                logger.error(f"Error archiving project: {str(e)}")
                error_embed = discord.Embed(
                    title="❌ " + I18n.t("common.error", locale),
                    description=I18n.t("common.error", locale, message=str(e)),
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