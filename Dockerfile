FROM python:3.12

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev gcc \
    && apt-get clean

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Copy the full app
COPY . /app/

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
