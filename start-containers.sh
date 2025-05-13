#!/bin/bash

# 解密环境变量文件
python backend/utils/env_crypto.py decrypt

# 启动容器
docker-compose -f docker-compose.prod.yaml up -d

# 等待容器启动完成
echo "等待容器启动..."
sleep 30

# 检查容器是否正常运行
if docker ps | grep -q "my-mysql-container" && docker ps | grep -q "django-app" && docker ps | grep -q "nginx"; then
    echo "所有容器已成功启动"
    
    # 删除解密后的环境变量文件
    echo "正在删除环境变量文件..."
    rm -f .env
    
    echo "部署完成！"
else
    echo "容器启动异常，请检查日志"
fi