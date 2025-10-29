git pull
echo y | docker image prune

# 确保外部网络存在（docker-compose.yml 使用 external: nginx_default）
docker network ls | grep -q "nginx_default" || docker network create nginx_default

# 构建并启动服务
docker compose build ocr
docker compose up -d ocr

# 启动后自动运行一次性测试容器，输出到日志文件（不影响服务运行）
mkdir -p output/test_logs
TS=$(date +%Y%m%d_%H%M%S)
docker compose run --rm test 2>&1 | tee output/test_logs/test_data_case_${TS}.log

# 跟随服务日志（可选择）
docker compose logs -f --tail 100 ocr