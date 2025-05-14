#!/bin/bash

# 替换 SQL 文件中的变量
envsubst < /docker-entrypoint-initdb.d/create_health_user.sql > /docker-entrypoint-initdb.d/final.sql

# 启动 MySQL 的原始入口点
exec docker-entrypoint.sh mysqld

