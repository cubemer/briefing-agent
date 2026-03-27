FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -fsSL https://github.com/aptible/supercronic/releases/latest/download/supercronic-linux-amd64 \
       -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY crontab /app/crontab
COPY start.sh .
RUN chmod +x start.sh

COPY . .

EXPOSE 8080

CMD ["./start.sh"]
