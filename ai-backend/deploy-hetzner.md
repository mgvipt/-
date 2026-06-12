# Развёртывание AI-бэкенда на вашем Hetzner (46.225.71.162)

Под вашу инфраструктуру: Docker + Nginx (reverse proxy + Let's Encrypt), рядом с `wallcov-app-app`.
Транскрибация — **бесплатный whisper.cpp локально** (без OpenAI). ИИ — Claude API.
Сервис: контейнер `wallcov-ai` на порту **8080**, поддомен **ai.wallcovdec.com.ua**.

## 0. Создать ключ Claude под это приложение
1. Зайдите на **console.anthropic.com → Settings → API keys**.
2. (Рекомендую) создайте отдельный **Workspace** «Wallcov AI» — чтобы лимиты/расходы этого приложения были отдельно от других.
3. **Create Key** → назовите `wallcov-ai` → скопируйте `sk-ant-...` (показывается один раз).
4. Пополните баланс / включите billing. Этот ключ пойдёт в `.env` (`ANTHROPIC_API_KEY`).

## 1. DNS
A-запись: `ai.wallcovdec.com.ua → 46.225.71.162`.

## 2. Код на сервер
```bash
ssh root@46.225.71.162
mkdir -p /var/www/ai.wallcovdec.com.ua && cd /var/www/ai.wallcovdec.com.ua
# скопировать сюда содержимое папки ai-backend (git clone ветки или scp)
cp .env.example .env && nano .env     # вписать ANTHROPIC_API_KEY и придумать API_TOKEN
```

## 3. Docker (whisper.cpp собирается в образе)
```bash
# модель small (быстро). Для лучшего распознавания укр/рос — medium:
docker build --build-arg WHISPER_MODEL_NAME=small -t wallcov-ai .
#   (или: --build-arg WHISPER_MODEL_NAME=medium  — точнее, но образ ~+1.5GB и медленнее на CPU)

docker run -d --name wallcov-ai --restart unless-stopped \
  --env-file .env -p 127.0.0.1:8080:8080 wallcov-ai

curl localhost:8080/health     # {"ok":true}
```
> Сборка whisper.cpp + модель идёт при `docker build` (нужен интернет на сервере). Это разово.

## 4. Nginx + SSL
```nginx
# /etc/nginx/sites-available/ai.wallcovdec.com.ua
server {
  server_name ai.wallcovdec.com.ua;
  client_max_body_size 250M;          # видео
  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_read_timeout 600s;          # транскрибация на CPU + ИИ
    proxy_set_header Host $host;
  }
}
```
```bash
ln -s /etc/nginx/sites-available/ai.wallcovdec.com.ua /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d ai.wallcovdec.com.ua
```

## 5. Проверка целиком
```bash
curl -X POST https://ai.wallcovdec.com.ua/process \
  -H "Authorization: Bearer <ВАШ API_TOKEN>" \
  -F "roomName=Кімната 1" -F "video=@/path/to/test.mp4"
# вернёт JSON: rooms[] с inspect, items, defects, photos(base64)
```

## 6. Интеграция в приложение
В `decorator.html` в каждой комнате добавим кнопку «🎬 Відеообхід»: запись видео → `POST /process`
(с заголовком `Authorization: Bearer <API_TOKEN>`) → полученные данные вливаются в комнату
(описание осмотра, позиции сметы, фото дефектов). Сделаю после того, как бэкенд поднимется и я узнаю
финальный URL и токен (URL и токен можно держать в localStorage приложения, в настройках).

## Производительность
whisper.cpp на CPU: small — быстро, medium — точнее, но в несколько раз медленнее. Для коротких
видео по комнате (1–3 мин) — приемлемо. Если будет медленно, увеличим ядра сервера или возьмём small.
