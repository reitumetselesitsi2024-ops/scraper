FROM python:3.11-slim

# Install Chromium and ChromeDriver (matching versions from apt)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Verify installations
RUN chromium --version && chromedriver --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "main.py"]
