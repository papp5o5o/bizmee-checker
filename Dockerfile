FROM mcr.microsoft.com/playwright/python:v1.63.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# --timeout を伸ばす: Renderのコールドスタート(~50秒)+Chromium起動+ページ読込を
# デフォルトの30秒では収まらないことがあり、超えるとworkerごと強制終了され
# 接続が切れる（エラーが出ないまま固まったように見える原因になりうる）
CMD ["gunicorn", "-b", "0.0.0.0:10000", "--timeout", "120", "--workers", "1", "main:app"]
