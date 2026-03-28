FROM python:3.12-slim

WORKDIR /app

# Verhindert Python-Stdout-Pufferung → Logs erscheinen sofort in docker logs
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
