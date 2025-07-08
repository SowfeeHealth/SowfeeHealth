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
RUN echo "=== Building React app ===" && \
    cd frontend_react && \
    npm install && \
    npm run build

# Verify React build
RUN echo "=== Verifying React build ===" && \
    ls -la /app/frontend_react/build/ && \
    test -f /app/frontend_react/build/index.html || (echo "❌ React build failed!" && exit 1)

# Create staticfiles directory
RUN mkdir -p /app/backend/staticfiles

# First: Run Django collectstatic (this will clear everything)
RUN echo "=== Running Django collectstatic ===" && \
    cd /app/backend && \
    python manage.py collectstatic --noinput --clear

# Second: Copy React files AFTER collectstatic
RUN echo "=== Copying React build files AFTER collectstatic ===" && \
    mkdir -p /app/backend/staticfiles/react && \
    cp -r /app/frontend_react/build/* /app/backend/staticfiles/react/

# Third: Copy Django static files if they exist
RUN echo "=== Copying Django static files ===" && \
    if [ -d "/app/frontend/static" ]; then \
        cp -r /app/frontend/static/* /app/backend/staticfiles/ 2>/dev/null || echo "No files to copy from frontend/static"; \
    fi

# Fourth: Copy any existing CSS files from backend/staticfiles source
RUN echo "=== Copying existing CSS files ===" && \
    if [ -f "/app/backend/staticfiles/dashboard.css" ]; then \
        echo "CSS files already exist in staticfiles"; \
    else \
        echo "Looking for CSS files in source..."; \
        find /app -name "*.css" -not -path "*/node_modules/*" -not -path "*/build/*" | head -10; \
    fi

# Final verification
RUN echo "=== FINAL VERIFICATION ===" && \
    echo "Staticfiles directory structure:" && \
    ls -la /app/backend/staticfiles/ && \
    echo "React files:" && \
    ls -la /app/backend/staticfiles/react/ 2>/dev/null || echo "No React files" && \
    echo "CSS files found:" && \
    find /app/backend/staticfiles -name "*.css" | head -10 && \
    echo "Total files in staticfiles:" && \
    find /app/backend/staticfiles -type f | wc -l

EXPOSE 8000

CMD ["bash", "-c", "cd backend && gunicorn core.wsgi:application --bind 0.0.0.0:8000 --log-level debug --access-logfile - --error-logfile -"]