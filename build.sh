git pull
docker build -t paddleocr-my:v1 .
docker compose up -d ocr
docker compose logs -f --tail 100 ocr