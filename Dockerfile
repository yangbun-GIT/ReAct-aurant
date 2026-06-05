FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8765 \
    WEB_AUTO_LOGIN=true

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8765

CMD ["python", "web_dashboard.py", "--host", "0.0.0.0", "--port", "8765"]
