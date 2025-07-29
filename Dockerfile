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
RUN cd frontend_react && \
    npm install && \
    npm run build

# Create staticfiles directory
RUN mkdir -p /app/backend/staticfiles

# Run Django collectstatic
RUN cd /app/backend && \
    python manage.py collectstatic --noinput --clear

# Copy React files after collectstatic
RUN mkdir -p /app/backend/staticfiles/react && \
    cp -r /app/frontend_react/build/* /app/backend/staticfiles/react/

# Copy Django static files if they exist
RUN if [ -d "/app/frontend/static" ]; then \
        cp -r /app/frontend/static/* /app/backend/staticfiles/ 2>/dev/null || true; \
    fi

EXPOSE 8000

CMD ["bash", "-c", "cd backend && gunicorn core.wsgi:application --bind 0.0.0.0:8000 --log-level debug --access-logfile - --error-logfile -"]