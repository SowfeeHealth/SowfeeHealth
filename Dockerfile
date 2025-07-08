FROM python:3.12

WORKDIR /app

# System dependencies + Node.js
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev gcc \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean

# Debug: Check Node and npm versions
RUN echo "=== Node/npm versions ===" && \
    node --version && \
    npm --version

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full app
COPY . /app/

# Debug: Check what files were copied
RUN echo "=== Files copied to container ===" && \
    ls -la /app/ && \
    echo "=== Backend directory ===" && \
    ls -la /app/backend/ && \
    echo "=== Frontend directory ===" && \
    ls -la /app/frontend/ 2>/dev/null || echo "No frontend directory" && \
    echo "=== Frontend_react directory ===" && \
    ls -la /app/frontend_react/ 2>/dev/null || echo "No frontend_react directory"

# Check if Django static files already exist
RUN echo "=== Checking existing Django static files ===" && \
    ls -la /app/backend/staticfiles/ 2>/dev/null || echo "No existing staticfiles directory" && \
    ls -la /app/frontend/static/ 2>/dev/null || echo "No frontend/static directory"

# Build React - SEPARATE COMMANDS so we can see where it fails
RUN echo "=== Installing React dependencies ===" && \
    cd frontend_react && \
    npm install

RUN echo "=== Building React app ===" && \
    cd frontend_react && \
    npm run build

# Verify build succeeded before copying
RUN echo "=== Verifying React build ===" && \
    ls -la /app/frontend_react/build/ && \
    test -f /app/frontend_react/build/index.html || (echo "❌ React build failed!" && exit 1)

# Create staticfiles directory
RUN echo "=== Creating staticfiles directory ===" && \
    mkdir -p /app/backend/staticfiles/react

# Copy React build files
RUN echo "=== Copying React build files ===" && \
    cp -r /app/frontend_react/build/* /app/backend/staticfiles/react/

# Copy Django static files if they exist
RUN echo "=== Copying Django static files ===" && \
    if [ -d "/app/frontend/static" ]; then \
        cp -r /app/frontend/static/* /app/backend/staticfiles/ 2>/dev/null || echo "No files to copy from frontend/static"; \
    fi

# Run Django collectstatic to gather admin/rest_framework files
RUN echo "=== Running Django collectstatic ===" && \
    cd /app/backend && \
    python manage.py collectstatic --noinput --clear

# Final verification - check ALL static files
RUN echo "=== FINAL VERIFICATION ===" && \
    echo "Staticfiles directory structure:" && \
    ls -la /app/backend/staticfiles/ && \
    echo "React files:" && \
    ls -la /app/backend/staticfiles/react/ 2>/dev/null || echo "No React files" && \
    echo "Admin files:" && \
    ls -la /app/backend/staticfiles/admin/ 2>/dev/null || echo "No admin files" && \
    echo "Total files in staticfiles:" && \
    find /app/backend/staticfiles -type f | wc -l

EXPOSE 8000

CMD ["bash", "-c", "cd backend && gunicorn core.wsgi:application --bind 0.0.0.0:8000 --log-level debug --access-logfile - --error-logfile -"]