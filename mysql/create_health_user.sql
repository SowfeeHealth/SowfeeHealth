-- 删除已存在的用户
DROP USER IF EXISTS 'health_user'@'localhost';
DROP USER IF EXISTS 'health_user'@'%';
DROP USER IF EXISTS 'health_user'@'172.18.0.2';

-- 创建新用户
CREATE USER 'health_user'@'%' IDENTIFIED BY '${MYSQL_HEALTH_USER_PASSWORD}';

-- 授予更多权限
GRANT ALL PRIVILEGES ON *.* TO 'health_user'@'%';

-- 刷新权限
FLUSH PRIVILEGES;
