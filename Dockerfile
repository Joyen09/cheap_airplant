FROM python:3.12-slim

WORKDIR /app

# 先裝相依（利用 layer 快取）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再複製程式碼
COPY . .

# 模式 B：持續掛著、即時回覆
CMD ["python", "main.py"]
