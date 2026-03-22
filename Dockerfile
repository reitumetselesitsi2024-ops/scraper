FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Force removal of any selenium cache
RUN rm -rf /root/.cache/selenium /tmp/selenium

# Set environment variables
ENV SELENIUM_DRIVER_MANAGER=0
ENV WDM_DISABLE=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Verify installations
RUN which chromium && which chromedriver
RUN chromedriver --version
RUN chromium --version

CMD ["python", "main.py"]
