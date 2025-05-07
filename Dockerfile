# Use an official Python image as base
FROM python:3.12

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .

# Install MySQL client
RUN apt-get update && apt-get install -y \
    default-mysql-client \
    && apt-get clean \
    && pip install --no-cache-dir -r requirements.txt

# Copy the entire project structure
COPY . .

# Expose the port that Django runs on
EXPOSE 8000

# Set the default command to run Django
CMD ["bash", "-c", "cd backend && python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn core.wsgi:application --bind 0.0.0.0:8000"]
