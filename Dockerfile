FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Python実行時にカレントディレクトリをPYTHONPATHに追加
ENV PYTHONPATH=/app

# 実行コマンドの変更
CMD ["python", "-m", "src.bot"]