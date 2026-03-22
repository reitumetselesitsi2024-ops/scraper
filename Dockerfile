FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Remove any cached selenium drivers
RUN rm -rf /root/.cache/selenium

# Create a symlink to ensure system chromedriver is used
RUN ln -sf /usr/bin/chromedriver /usr/local/bin/chromedriver

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Set environment variables to disable selenium manager
ENV SELENIUM_DRIVER_MANAGER=0
ENV WDM_DISABLE=1

CMD ["python", "main.py"]
