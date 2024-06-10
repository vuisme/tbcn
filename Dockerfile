# Sử dụng Python 3.9
FROM python:3.9-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Sao chép file yêu cầu vào container
COPY requirements.txt requirements.txt

# Cài đặt các thư viện cần thiết
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép mã nguồn vào container
COPY bot.py bot.py

# Chạy bot
CMD ["python", "bot.py"]
