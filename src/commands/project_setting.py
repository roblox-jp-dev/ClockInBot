import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, Any, List

from ..database.repository import ProjectRepository, UserRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.project_setting')

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
            
            # 操作用のViewを作成
            view = discord.ui.View()
            
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
            async def add_project_callback(interaction: discord.Interaction):
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
                
                # モーダルにフィールドを追加
                modal.add_item(name_input)
                modal.add_item(description_input)
                modal.add_item(check_interval_input)
                
                # モーダル送信時の処理
                async def on_add_submit(interaction: discord.Interaction):
                    try:
                        # 入力値を取得
                        name = name_input.value
                        description = description_input.value
                        
                        # 確認間隔を秒に変換
                        try:
                            check_interval = int(check_interval_input.value) * 60
                        except ValueError:
                            check_interval = 1800  # デフォルト30分
                        
                        # ユーザー情報を取得
                        guild_user = await UserRepository.get_guild_user(guild_id, user_id)
                        
                        # プロジェクトを作成
                        created_project = await ProjectRepository.create_project(
                            guild_id=guild_id,
                            name=name,
                            description=description,
                            created_by_user_id=guild_user["id"] if guild_user else None,
                            check_interval=check_interval,
                            require_confirmation=True,
                            require_modal=True
                        )
                        
                        await interaction.response.send_message(
                            I18n.t("project.created", name=name),
                            ephemeral=True
                        )
                    
                    except Exception as e:
                        logger.error(f"Error creating project: {str(e)}")
                        await interaction.response.send_message(
                            I18n.t("common.error", message=str(e)),
                            ephemeral=True
                        )
                
                modal.on_submit = on_add_submit
                await interaction.response.send_modal(modal)
            
            async def edit_project_callback(interaction: discord.Interaction):
                # 編集対象のプロジェクト選択メニューを表示
                active_projects = [p for p in projects if not p["is_archived"]]
                
                if not active_projects:
                    await interaction.response.send_message(
                        I18n.t("project.notFound"),
                        ephemeral=True
                    )
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
                        for project in active_projects
                    ]
                )
                
                # セレクトメニューのコールバック
                async def on_select(interaction: discord.Interaction):
                    project_id = int(select.values[0])
                    
                    # 選択されたプロジェクトを取得
                    project = next((p for p in projects if p["id"] == project_id), None)
                    
                    if not project:
                        await interaction.response.send_message(
                            I18n.t("project.notFound"),
                            ephemeral=True
                        )
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
                    
                    # モーダルにフィールドを追加
                    modal.add_item(name_input)
                    modal.add_item(description_input)
                    modal.add_item(check_interval_input)
                    
                    # モーダル送信時の処理
                    async def on_edit_submit(interaction: discord.Interaction):
                        try:
                            # 入力値を取得
                            name = name_input.value
                            description = description_input.value
                            
                            # 確認間隔を秒に変換
                            try:
                                check_interval = int(check_interval_input.value) * 60
                            except ValueError:
                                check_interval = 1800  # デフォルト30分
                            
                            # プロジェクトを更新
                            updated_project = await ProjectRepository.update_project(
                                project_id=project_id,
                                name=name,
                                description=description,
                                check_interval=check_interval
                            )
                            
                            await interaction.response.send_message(
                                I18n.t("project.updated", name=name),
                                ephemeral=True
                            )
                        
                        except Exception as e:
                            logger.error(f"Error updating project: {str(e)}")
                            await interaction.response.send_message(
                                I18n.t("common.error", message=str(e)),
                                ephemeral=True
                            )
                    
                    modal.on_submit = on_edit_submit
                    await interaction.response.send_modal(modal)
                
                select.callback = on_select
                
                # Viewを作成してセレクトメニューを追加
                view = discord.ui.View()
                view.add_item(select)
                
                await interaction.response.send_message(
                    "編集するプロジェクトを選択してください",
                    view=view,
                    ephemeral=True
                )
            
            async def archive_project_callback(interaction: discord.Interaction):
                # アーカイブ対象のプロジェクト選択メニューを表示
                active_projects = [p for p in projects if not p["is_archived"]]
                
                if not active_projects:
                    await interaction.response.send_message(
                        I18n.t("project.notFound"),
                        ephemeral=True
                    )
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
                        for project in active_projects
                    ]
                )
                
                # セレクトメニューのコールバック
                async def on_select(interaction: discord.Interaction):
                    project_id = int(select.values[0])
                    
                    # 選択されたプロジェクトを取得
                    project = next((p for p in projects if p["id"] == project_id), None)
                    
                    if not project:
                        await interaction.response.send_message(
                            I18n.t("project.notFound"),
                            ephemeral=True
                        )
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
                            
                            await interaction.response.send_message(
                                I18n.t("project.archived", name=project['name']),
                                ephemeral=True
                            )
                        
                        except Exception as e:
                            logger.error(f"Error archiving project: {str(e)}")
                            await interaction.response.send_message(
                                I18n.t("common.error", message=str(e)),
                                ephemeral=True
                            )
                    
                    # 「いいえ」ボタンのコールバック
                    async def on_no(interaction: discord.Interaction):
                        await interaction.response.send_message(
                            "アーカイブをキャンセルしました",
                            ephemeral=True
                        )
                    
                    yes_button.callback = on_yes
                    no_button.callback = on_no
                    
                    confirm_view.add_item(yes_button)
                    confirm_view.add_item(no_button)
                    
                    await interaction.response.send_message(
                        embed=embed,
                        view=confirm_view,
                        ephemeral=True
                    )
                
                select.callback = on_select
                
                # Viewを作成してセレクトメニューを追加
                view = discord.ui.View()
                view.add_item(select)
                
                await interaction.response.send_message(
                    "アーカイブするプロジェクトを選択してください",
                    view=view,
                    ephemeral=True
                )
            
            # ボタンにコールバックを設定
            add_button.callback = add_project_callback
            edit_button.callback = edit_project_callback
            archive_button.callback = archive_project_callback
            
            # Viewにボタンを追加
            view.add_item(add_button)
            view.add_item(edit_button)
            view.add_item(archive_button)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in project_setting command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", message=str(e)), ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(ProjectSettingCog(bot))