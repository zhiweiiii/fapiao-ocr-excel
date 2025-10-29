git pull
echo y | docker image prune

# 确保外部网络存在（docker-compose.yml 使用 external: nginx_default）
docker network ls | grep -q "nginx_default" || docker network create nginx_default

# 构建并启动服务
docker compose build ocr
docker compose up -d ocr


# 跟随服务日志（可选择）
docker compose logs -f --tail 100 ocr