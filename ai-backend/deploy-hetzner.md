# Развёртывание AI-бэкенда на вашем Hetzner (46.225.71.162)

Под вашу существующую инфраструктуру: Docker + Nginx (reverse proxy + Let's Encrypt),
рядом с `wallcov-app-app`. AI-сервис поднимаем как отдельный контейнер на порту **8080**
и поддомене **ai.wallcovdec.com.ua**.

## 1. DNS
Добавьте A-запись: `ai.wallcovdec.com.ua → 46.225.71.162`.

## 2. Код на сервер
```bash
ssh root@46.225.71.162
mkdir -p /var/www/ai.wallcovdec.com.ua && cd /var/www/ai.wallcovdec.com.ua
# скопировать сюда содержимое папки ai-backend (git clone ветки или scp)
cp .env.example .env && nano .env   # вписать ANTHROPIC_API_KEY, OPENAI_API_KEY
```

## 3. Docker
```bash
docker build -t wallcov-ai .
docker run -d --name wallcov-ai --restart unless-stopped \
  --env-file .env -p 127.0.0.1:8080:8080 wallcov-ai
docker ps   # проверить, что контейнер поднялся
curl localhost:8080/health   # {"ok":true}
```

## 4. Nginx + SSL (как у магазина)
```nginx
# /etc/nginx/sites-available/ai.wallcovdec.com.ua
server {
  server_name ai.wallcovdec.com.ua;
  client_max_body_size 250M;            # видео
  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_read_timeout 300s;            # транскрибация+ИИ дольше
    proxy_set_header Host $host;
  }
}
```
```bash
ln -s /etc/nginx/sites-available/ai.wallcovdec.com.ua /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d ai.wallcovdec.com.ua    # SSL
```

## 5. Защита
В `/process` добавить проверку токена (заголовок `Authorization`), чтобы вашими API-ключами
не пользовались посторонние. Скажете — добавлю в код middleware с токеном из `.env`.

## Что нужно от вас, чтобы я сделал всё сам
- SSH-доступ к `46.225.71.162` (ключ или пароль), добавленный в окружение сессии.
- `ANTHROPIC_API_KEY` (Claude) и ключ транскрибации (OpenAI) — или поднимем whisper.cpp локально на сервере без OpenAI.
