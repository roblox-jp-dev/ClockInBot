import discord
from discord import ui, Interaction, ButtonStyle
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from ..database.repository import AttendanceRepository, ProjectRepository, UserRepository, ChannelRepository
from ..utils.i18n import I18n

class ProjectSelectView(ui.View):
    """プロジェクト選択用のView"""
    
    def __init__(self, projects: List[Dict[str, Any]], locale: str):
        super().__init__(timeout=300)  # 5分でタイムアウト
        self.locale = locale
        self.selected_project_id = None
        
        # プロジェクト選択のセレクトメニュー
        options = [
            discord.SelectOption(
                label=project["name"],
                value=str(project["id"]),
                description=project["description"][:100] if project["description"] else None
            )
            for project in projects[:25]  # 最大25個
        ]
        
        self.project_select = ui.Select(
            placeholder=I18n.t("modal.project", locale),
            options=options
        )
        self.project_select.callback = self.select_callback
        self.add_item(self.project_select)
    
    async def select_callback(self, interaction: Interaction):
        """プロジェクト選択時のコールバック"""
        self.selected_project_id = int(self.project_select.values[0])
        await interaction.response.defer()

class EndWorkSummaryModal(ui.Modal):
    """勤務終了時の要約入力モーダル"""
    
    def __init__(self, locale: str):
        super().__init__(title=I18n.t("modal.summary", locale))
        
        self.locale = locale
        self.summary_value = None
        
        # 要約入力フィールド
        self.summary = ui.TextInput(
            label=I18n.t("modal.summary", locale),
            placeholder=I18n.t("modal.summaryPlaceholder", locale),
            style=discord.TextStyle.paragraph,
            required=False
        )
        
        self.add_item(self.summary)
    
    async def on_submit(self, interaction: Interaction):
        self.summary_value = self.summary.value
        await interaction.response.defer()

class AttendanceView(ui.View):
    """勤怠管理の固定メッセージに表示するView"""
    
    def __init__(self, guild_user_id: int, locale: str = "ja"):
        super().__init__(timeout=None)
        self.guild_user_id = guild_user_id
        self.locale = locale
        
        # 初期状態では「勤務開始」ボタンのみ表示
        self.update_buttons(is_working=False)
    
    def update_buttons(self, is_working: bool):
        """状態に応じてボタンを更新"""
        # 既存のボタンを全て削除
        self.clear_items()
        
        if is_working:
            # 勤務中の場合は「勤務終了」ボタンのみ
            end_button = ui.Button(
                custom_id=f"end_work_{self.guild_user_id}",
                label=I18n.t("button.endWork", self.locale),
                style=ButtonStyle.danger
            )
            end_button.callback = self.handle_end_work
            self.add_item(end_button)
        else:
            # 勤務していない場合は「勤務開始」ボタンのみ
            start_button = ui.Button(
                custom_id=f"start_work_{self.guild_user_id}",
                label=I18n.t("button.startWork", self.locale),
                style=ButtonStyle.success
            )
            start_button.callback = self.handle_start_work
            self.add_item(start_button)
    
    async def handle_start_work(self, interaction: Interaction):
        """勤務開始ボタンの処理"""
        await interaction.response.defer(ephemeral=True)
        
        # チャンネルからユーザー情報を取得
        channel_mapping = await ChannelRepository.get_by_channel_id(interaction.channel_id)
        if not channel_mapping:
            await interaction.followup.send(I18n.t("common.error", self.locale, message="Channel not found"), ephemeral=True)
            return
        
        guild_user_id = channel_mapping["guild_user_id"]
        
        # アクティブなセッションをチェック
        active_session = await AttendanceRepository.get_active_session(guild_user_id)
        if active_session:
            # 既に勤務中の場合はエラー
            await interaction.followup.send(I18n.t("attendance.alreadyStarted", self.locale), ephemeral=True)
            return
        
        # プロジェクト一覧を取得
        projects = await ProjectRepository.get_all_projects(interaction.guild_id)
        
        if not projects:
            await interaction.followup.send(I18n.t("project.notFound", self.locale), ephemeral=True)
            return
        
        # プロジェクト選択Viewを表示
        project_view = ProjectSelectView(projects, self.locale)
        await interaction.followup.send(
            "勤務するプロジェクトを選択してください：",
            view=project_view,
            ephemeral=True
        )
        
        # プロジェクト選択を待機
        await project_view.wait()
        
        if project_view.selected_project_id is None:
            return  # タイムアウトまたはキャンセル
        
        # プロジェクト情報を取得
        project = await ProjectRepository.get_project(project_view.selected_project_id)
        
        # 勤務開始を記録
        session = await AttendanceRepository.start_session(guild_user_id, project_view.selected_project_id)
        
        # 固定メッセージを更新
        channel = interaction.channel
        pinned_message = await channel.fetch_message(channel_mapping["pinned_message_id"])
        
        # Embedを更新
        embed = await create_attendance_embed(guild_user_id, self.locale)
        
        # Viewを更新（勤務中状態に）
        view = AttendanceView(guild_user_id, self.locale)
        view.update_buttons(is_working=True)
        
        await pinned_message.edit(embed=embed, view=view)
        
        # 確認メッセージを送信
        user = interaction.user
        try:
            await interaction.edit_original_response(
                content=I18n.t("attendance.start", self.locale, username=user.display_name, project=project["name"]),
                view=None
            )
        except:
            # 編集に失敗した場合は新しいメッセージを送信
            await interaction.followup.send(
                I18n.t("attendance.start", self.locale, username=user.display_name, project=project["name"]),
                ephemeral=True
            )
    
    async def handle_end_work(self, interaction: Interaction):
        """勤務終了ボタンの処理"""
        await interaction.response.defer(ephemeral=True)
        
        # チャンネルからユーザー情報を取得
        channel_mapping = await ChannelRepository.get_by_channel_id(interaction.channel_id)
        if not channel_mapping:
            await interaction.followup.send(I18n.t("common.error", self.locale, message="Channel not found"), ephemeral=True)
            return
        
        guild_user_id = channel_mapping["guild_user_id"]
        
        # アクティブなセッションをチェック
        active_session = await AttendanceRepository.get_active_session(guild_user_id)
        if not active_session:
            # 勤務していない場合はエラー
            await interaction.followup.send(I18n.t("attendance.notStarted", self.locale), ephemeral=True)
            return
        
        # プロジェクト情報を取得
        project = await ProjectRepository.get_project(active_session["project_id"])
        
        # 勤務終了時に要約を求めるかどうかをチェック
        require_modal = project.get("require_modal", True) if project else True
        
        end_summary = None
        
        if require_modal:
            # 要約入力モーダルを表示
            modal = EndWorkSummaryModal(self.locale)
            await interaction.followup.send("作業内容の要約を入力してください：", ephemeral=True)
            await interaction.response.send_modal(modal)
            
            # モーダルの入力を待機
            await modal.wait()
            
            # 入力された要約を取得
            end_summary = modal.summary_value
        
        # 勤務終了を記録
        updated_session = await AttendanceRepository.end_session(
            active_session["id"],
            end_summary=end_summary
        )
        
        # 勤務時間を計算
        duration = updated_session["end_time"] - updated_session["start_time"]
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_str = f"{hours:02}:{minutes:02}:{seconds:02}"
        
        # 固定メッセージを更新
        channel = interaction.channel
        pinned_message = await channel.fetch_message(channel_mapping["pinned_message_id"])
        
        # Embedを更新
        embed = await create_attendance_embed(guild_user_id, self.locale)
        
        # Viewを更新（未勤務状態に）
        view = AttendanceView(guild_user_id, self.locale)
        view.update_buttons(is_working=False)
        
        await pinned_message.edit(embed=embed, view=view)
        
        # 確認メッセージを送信
        user = interaction.user
        await interaction.followup.send(
            I18n.t("attendance.end", self.locale, username=user.display_name, duration=duration_str),
            ephemeral=True
        )

async def create_attendance_embed(
    guild_user_id: int,
    locale: str = "ja",
    user_data: Dict[str, Any] = None
) -> discord.Embed:
    """勤怠状況を表示するEmbedを作成"""
    
    # アクティブなセッションを取得
    active_session = await AttendanceRepository.get_active_session(guild_user_id)
    
    embed = discord.Embed(
        title=I18n.t("embed.title", locale),
        color=discord.Color.green() if active_session else discord.Color.light_grey(),
        timestamp=datetime.now()
    )
    
    # 勤務中かどうかを表示
    embed.add_field(
        name=I18n.t("embed.status", locale),
        value=I18n.t("embed.working", locale) if active_session else I18n.t("embed.notWorking", locale),
        inline=False
    )
    
    if active_session:
        # プロジェクト情報を取得
        project = await ProjectRepository.get_project(active_session["project_id"])
        
        # プロジェクト名を表示
        embed.add_field(
            name=I18n.t("embed.project", locale),
            value=project["name"] if project else "Unknown",
            inline=True
        )
        
        # 開始時間を表示
        start_time = active_session["start_time"]
        embed.add_field(
            name=I18n.t("embed.startTime", locale),
            value=start_time.strftime("%H:%M:%S"),
            inline=True
        )
        
        # 経過時間を計算して表示
        duration = datetime.now() - start_time
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        embed.add_field(
            name=I18n.t("embed.duration", locale),
            value=f"{hours:02}:{minutes:02}:{seconds:02}",
            inline=True
        )
    
    return embed

# 削除: handle_start_work_button と handle_end_work_button 関数は不要（Viewに統合）

async def create_or_update_attendance_message(
    channel: discord.TextChannel,
    guild_user_id: int,
    pinned_message_id: Optional[int] = None,
    locale: str = "ja"
):
    """勤怠管理用の固定メッセージを作成または更新"""
    
    # Embedを作成
    embed = await create_attendance_embed(guild_user_id, locale)
    
    # アクティブなセッションをチェック
    active_session = await AttendanceRepository.get_active_session(guild_user_id)
    
    # Viewを作成
    view = AttendanceView(guild_user_id, locale)
    view.update_buttons(is_working=bool(active_session))
    
    if pinned_message_id:
        try:
            # 既存のメッセージを取得して更新
            message = await channel.fetch_message(pinned_message_id)
            await message.edit(embed=embed, view=view)
            return message
        except discord.NotFound:
            # メッセージが見つからない場合は新規作成
            pass
    
    # 新しいメッセージを送信
    message = await channel.send(embed=embed, view=view)
    
    # メッセージをピン止め
    await message.pin()
    
    return message