FROM python:3.12

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev gcc \
    && apt-get clean

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full app
COPY . /app/

EXPOSE 8000

# 不再使用 entrypoint.sh
CMD ["bash", "-c", "cd backend && gunicorn core.wsgi:application --bind 0.0.0.0:8000 --log-level debug --access-logfile - --error-logfile -"]
