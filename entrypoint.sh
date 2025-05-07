#!/bin/bash

# Exit the script immediately if any command fails
set -e

# Wait for the database to be ready (optional, but useful in case DB takes time to start)
echo "Waiting for the database to be ready..."
while ! nc -z db 3306; do
  sleep 0.1
done
echo "Database is ready!"

# Run Django migrations
echo "Running migrations..."
cd backend
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start the application using Gunicorn
echo "Starting the application..."
gunicorn core.wsgi:application --bind 0.0.0.0:8000 --log-level debug --access-logfile - --error-logfile -
