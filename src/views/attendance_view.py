import discord
from discord import ui, Interaction, ButtonStyle
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from ..database.repository import AttendanceRepository, ProjectRepository, UserRepository, ChannelRepository
from ..utils.i18n import I18n

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
            self.add_item(end_button)
        else:
            # 勤務していない場合は「勤務開始」ボタンのみ
            start_button = ui.Button(
                custom_id=f"start_work_{self.guild_user_id}",
                label=I18n.t("button.startWork", self.locale),
                style=ButtonStyle.success
            )
            self.add_item(start_button)

async def handle_attendance_interaction(interaction: discord.Interaction):
    """勤怠管理のインタラクション処理"""
    custom_id = interaction.data.get('custom_id', '')
    
    if custom_id.startswith('start_work_'):
        await handle_start_work(interaction)
    elif custom_id.startswith('end_work_'):
        await handle_end_work(interaction)
    elif custom_id.startswith('select_project_'):
        await handle_project_selection(interaction)

async def handle_start_work(interaction: discord.Interaction):
    """勤務開始ボタンの処理"""
    await interaction.response.defer(ephemeral=True)
    
    # チャンネルからユーザー情報を取得
    channel_mapping = await ChannelRepository.get_by_channel_id(interaction.channel_id)
    if not channel_mapping:
        await interaction.followup.send("エラー: チャンネルが見つかりません", ephemeral=True)
        return
    
    guild_user_id = channel_mapping["guild_user_id"]
    
    # サーバー設定から言語を取得
    from ..database.repository import GuildRepository
    guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
    locale = guild_settings["locale"] if guild_settings else "ja"
    
    # アクティブなセッションをチェック
    active_session = await AttendanceRepository.get_active_session(guild_user_id)
    if active_session:
        # 既に勤務中の場合はエラー
        await interaction.followup.send(I18n.t("attendance.alreadyStarted", locale), ephemeral=True)
        return
    
    # プロジェクト一覧を取得
    projects = await ProjectRepository.get_all_projects(interaction.guild_id)
    
    if not projects:
        await interaction.followup.send(I18n.t("project.notFound", locale), ephemeral=True)
        return
    
    # プロジェクト選択のセレクトメニューを作成
    options = [
        discord.SelectOption(
            label=project["name"],
            value=str(project["id"]),
            description=project["description"][:100] if project["description"] else None
        )
        for project in projects[:25]  # 最大25個
    ]
    
    select = ui.Select(
        placeholder=I18n.t("modal.project", locale),
        options=options,
        custom_id=f"select_project_{guild_user_id}"
    )
    
    # Viewを作成してセレクトメニューを追加
    view = ui.View()
    view.add_item(select)
    
    await interaction.followup.send(
        "勤務するプロジェクトを選択してください：",
        view=view,
        ephemeral=True
    )

async def handle_project_selection(interaction: discord.Interaction):
    """プロジェクト選択の処理"""
    await interaction.response.defer(ephemeral=True)
    
    # セレクトメニューの値を取得
    project_id = int(interaction.data['values'][0])
    
    # チャンネルからユーザー情報を取得
    channel_mapping = await ChannelRepository.get_by_channel_id(interaction.channel_id)
    if not channel_mapping:
        await interaction.followup.send("エラー: チャンネルが見つかりません", ephemeral=True)
        return
    
    guild_user_id = channel_mapping["guild_user_id"]
    
    # サーバー設定から言語を取得
    from ..database.repository import GuildRepository
    guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
    locale = guild_settings["locale"] if guild_settings else "ja"
    
    # プロジェクト情報を取得
    project = await ProjectRepository.get_project(project_id)
    
    # 勤務開始を記録
    session = await AttendanceRepository.start_session(guild_user_id, project_id)
    
    # 固定メッセージを更新
    await update_attendance_message(
        interaction.channel,
        channel_mapping["pinned_message_id"],
        guild_user_id,
        locale
    )
    
    # 確認メッセージを送信（5秒後に削除）
    user = interaction.user
    await interaction.followup.send(
        I18n.t("attendance.start", locale, username=user.display_name, project=project["name"]),
        ephemeral=True,
        delete_after=5
    )

async def handle_end_work(interaction: discord.Interaction):
    """勤務終了ボタンの処理"""
    # チャンネルからユーザー情報を取得
    channel_mapping = await ChannelRepository.get_by_channel_id(interaction.channel_id)
    if not channel_mapping:
        await interaction.response.send_message("エラー: チャンネルが見つかりません", ephemeral=True)
        return
    
    guild_user_id = channel_mapping["guild_user_id"]
    
    # サーバー設定から言語を取得
    from ..database.repository import GuildRepository
    guild_settings = await GuildRepository.get_guild_settings(interaction.guild_id)
    locale = guild_settings["locale"] if guild_settings else "ja"
    
    # アクティブなセッションをチェック
    active_session = await AttendanceRepository.get_active_session(guild_user_id)
    if not active_session:
        # 勤務していない場合はエラー
        await interaction.response.send_message(
            I18n.t("attendance.notStarted", locale), 
            ephemeral=True
        )
        return
    
    # プロジェクト情報を取得
    project = await ProjectRepository.get_project(active_session["project_id"])
    
    # 勤務終了時に要約を求めるかどうかをチェック
    require_modal = project.get("require_modal", True) if project else True
    
    end_summary = None
    
    if require_modal:
        # 要約入力モーダルを表示（defer しない）
        modal = EndWorkSummaryModal(locale)
        await interaction.response.send_modal(modal)
        
        # モーダルの入力を待機
        await modal.wait()
        
        # 入力された要約を取得
        end_summary = modal.summary_value
    else:
        # モーダルが不要な場合はdeferを実行
        await interaction.response.defer(ephemeral=True)
    
    # 勤務終了を記録
    updated_session = await AttendanceRepository.end_session(
        active_session["id"],
        end_summary=end_summary
    )
    
    if not updated_session:
        error_msg = I18n.t("common.error", locale, message="Failed to end session")
        if require_modal:
            await interaction.followup.send(error_msg, ephemeral=True)
        else:
            await interaction.followup.send(error_msg, ephemeral=True)
        return
    
    # 勤務時間を計算
    duration = updated_session["end_time"] - updated_session["start_time"]
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    duration_str = f"{hours:02}:{minutes:02}:{seconds:02}"
    
    # 固定メッセージを更新
    await update_attendance_message(
        interaction.channel,
        channel_mapping["pinned_message_id"],
        guild_user_id,
        locale
    )
    
    # 勤務終了の埋め込みメッセージを送信（全員に見える）
    await send_work_completion_message(
        interaction.channel,
        interaction.user,
        updated_session,
        project,
        duration_str,
        locale
    )
    
    # 確認メッセージを送信（5秒後に削除）
    user = interaction.user
    success_msg = I18n.t("attendance.end", locale, username=user.display_name, duration=duration_str)
    
    if require_modal:
        await interaction.followup.send(success_msg, ephemeral=True, delete_after=5)
    else:
        await interaction.followup.send(success_msg, ephemeral=True, delete_after=5)

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
        timestamp=datetime.now(timezone.utc)
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
        
        # 開始時間を表示（タイムスタンプとして）
        start_time = active_session["start_time"]
        # タイムスタンプに変換（Unixエポック秒）
        start_timestamp = int(start_time.timestamp())
        embed.add_field(
            name=I18n.t("embed.startTime", locale),
            value=f"<t:{start_timestamp}:t>",
            inline=True
        )
    
    return embed

async def update_attendance_message(
    channel: discord.TextChannel,
    current_message_id: int,
    guild_user_id: int,
    locale: str = "ja"
):
    """固定メッセージのローテーション更新"""
    
    try:
        # 現在の固定メッセージを取得
        current_message = await channel.fetch_message(current_message_id)
        
        # 新しいEmbedとViewを作成
        new_embed = await create_attendance_embed(guild_user_id, locale)
        active_session = await AttendanceRepository.get_active_session(guild_user_id)
        new_view = AttendanceView(guild_user_id, locale)
        new_view.update_buttons(is_working=bool(active_session))
        
        # 現在のメッセージの内容で新しいメッセージを送信
        old_message = await channel.send(
            embed=current_message.embeds[0] if current_message.embeds else None,
            view=None  # 古いViewは無効化
        )
        
        # 現在のメッセージを新しい内容で編集
        await current_message.edit(embed=new_embed, view=new_view)
        
        # channel_mappingsのpinned_message_idはそのまま（current_message_idを維持）
        
    except discord.NotFound:
        # メッセージが見つからない場合は新規作成
        await create_or_update_attendance_message(channel, guild_user_id, None, locale)

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
    
    # 新しいメッセージを送信（ピン留めしない）
    message = await channel.send(embed=embed, view=view)
    
    return message

async def restore_attendance_message(
    channel: discord.TextChannel,
    message_id: int,
    guild_user_id: int,
    locale: str = "ja"
):
    """Bot再起動時に勤怠メッセージのViewを復元"""
    try:
        message = await channel.fetch_message(message_id)
        
        # 現在の状態に基づいてViewを作成
        active_session = await AttendanceRepository.get_active_session(guild_user_id)
        view = AttendanceView(guild_user_id, locale)
        view.update_buttons(is_working=bool(active_session))
        
        # メッセージのViewを更新
        await message.edit(view=view)
        
    except discord.NotFound:
        # メッセージが見つからない場合は何もしない
        pass

async def send_work_completion_message(
    channel: discord.TextChannel,
    user: discord.User,
    session: Dict[str, Any],
    project: Optional[Dict[str, Any]],
    duration_str: str,
    locale: str = "ja"
):
    """勤務終了時の埋め込みメッセージを送信"""
    
    embed = discord.Embed(
        title="🎯 勤務完了",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    
    # ユーザー情報
    embed.set_author(
        name=user.display_name,
        icon_url=user.avatar.url if user.avatar else user.default_avatar.url
    )
    
    # プロジェクト名
    project_name = project["name"] if project else "Unknown"
    embed.add_field(
        name="📋 プロジェクト",
        value=project_name,
        inline=True
    )
    
    # 勤務時間
    embed.add_field(
        name="⏱️ 勤務時間",
        value=duration_str,
        inline=True
    )
    
    # 勤務期間（開始時間と終了時間）
    start_time = session["start_time"]
    end_time = session["end_time"]
    
    start_timestamp = int(start_time.timestamp())
    end_timestamp = int(end_time.timestamp())
    
    embed.add_field(
        name="📅 勤務期間",
        value=f"<t:{start_timestamp}:t> ～ <t:{end_timestamp}:t>",
        inline=False
    )
    
    # 業務内容（要約がある場合）
    if session.get("end_summary"):
        embed.add_field(
            name="📝 業務内容",
            value=session["end_summary"],
            inline=False
        )
    
    await channel.send(embed=embed)