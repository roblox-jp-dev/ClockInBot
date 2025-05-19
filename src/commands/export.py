import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import io
import csv
from typing import Optional, List, Dict, Any

from ..database.repository import AttendanceRepository, UserRepository
from ..utils.i18n import I18n
from ..utils.logger import setup_logger

logger = setup_logger('commands.export')

class ExportCog(commands.Cog):
    """勤怠データをCSVでエクスポートするコマンド"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="export",
        description="勤怠データをCSVでエクスポートします"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        period="エクスポートする期間（日数、デフォルト: 30）"
    )
    async def export(self, interaction: discord.Interaction, period: int = 30):
        """勤怠データをCSVでエクスポートするコマンド"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = interaction.guild.id
            user_id = interaction.user.id
            
            # 期間の範囲を制限
            if period > 365:
                period = 365
            elif period < 1:
                period = 1
            
            # 日付範囲を計算
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period)
            
            # ユーザー情報を取得
            guild_user = await UserRepository.get_guild_user(guild_id, user_id)
            if not guild_user:
                await interaction.followup.send(I18n.t("user.notFound", username=interaction.user.display_name))
                return
            
            # 指定期間のセッション履歴を取得
            sessions = await AttendanceRepository.get_sessions_by_date_range(
                guild_user["id"],
                start_date,
                end_date
            )
            
            if not sessions:
                await interaction.followup.send(I18n.t("log.noRecord"))
                return
            
            # CSVファイルを生成
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            
            # ヘッダー行
            writer.writerow([
                "開始日時", "終了日時", "プロジェクト", "勤務時間（時間）", "勤務時間（分）", "勤務時間（秒）", "状態", "要約"
            ])
            
            # データ行
            for session in sessions:
                start_time = session["start_time"]
                end_time = session["end_time"] if session["end_time"] else datetime.now()
                
                # 勤務時間を計算
                duration = end_time - start_time
                total_seconds = int(duration.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                # プロジェクト名
                project_name = session.get("project_name", "Unknown")
                
                # 状態
                status = "自動終了" if session.get("status") == "auto" else "手動終了"
                if not session.get("end_time"):
                    status = "進行中"
                
                # 行を書き込み
                writer.writerow([
                    start_time.strftime("%Y/%m/%d %H:%M:%S"),
                    end_time.strftime("%Y/%m/%d %H:%M:%S") if session.get("end_time") else "進行中",
                    project_name,
                    hours,
                    minutes,
                    seconds,
                    status,
                    session.get("end_summary", "")
                ])
            
            # バッファをファイルとして送信
            buffer.seek(0)
            
            # 生成したCSVファイルをDiscord上で送信
            file = discord.File(
                fp=io.BytesIO(buffer.getvalue().encode('utf-8-sig')),  # BOMあり
                filename=f"attendance_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.csv"
            )
            
            await interaction.followup.send(
                I18n.t("export.complete"),
                file=file,
                ephemeral=True
            )
        
        except Exception as e:
            logger.error(f"Error in export command: {str(e)}")
            await interaction.followup.send(I18n.t("common.error", message=str(e)))

async def setup(bot: commands.Bot):
    await bot.add_cog(ExportCog(bot))