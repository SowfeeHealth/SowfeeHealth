#!/bin/bash
set -e

# Substitute environment variables in the SQL file and store in a temp file
envsubst < /docker-entrypoint-initdb.d/create_health_user.sql > /tmp/processed.sql

# Wait for MySQL to be up
echo "Waiting for MySQL to be ready..."
until mysql -h mysql -u root -p"$MYSQL_ROOT_PASSWORD" -e "SELECT 1;" &> /dev/null; do
  sleep 1
done

echo "Running processed SQL..."
mysql -h mysql -u root -p"$MYSQL_ROOT_PASSWORD" < /tmp/processed.sql

exec "$@"

