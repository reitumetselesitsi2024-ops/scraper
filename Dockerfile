FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Completely remove any selenium cache directories
RUN rm -rf /root/.cache/selenium
RUN rm -rf /tmp/selenium

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Set environment variables to block selenium from downloading drivers
ENV SELENIUM_DRIVER_MANAGER=0
ENV WDM_DISABLE=1
ENV SE_DRIVER_MANAGER=0

CMD ["python", "main.py"]
