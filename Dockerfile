FROM python:3.12

WORKDIR /app

# System dependencies + Node.js
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev gcc \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full app
COPY . /app/

# Build React
RUN cd frontend_react && npm install && npm run build && \
    mkdir -p /app/staticfiles && cp -r build/* /app/staticfiles/

EXPOSE 8000

# 不再使用 entrypoint.sh
CMD ["bash", "-c", "cd backend && gunicorn core.wsgi:application --bind 0.0.0.0:8000 --log-level debug --access-logfile - --error-logfile -"]
