# Wallcov AI backend (каркас)

Видео по комнате → транскрибация → ИИ (смета + акт осмотра + кадры дефектов из видео).

> ⚠️ Это **каркас/фундамент**, не протестированный продукт. Чтобы он заработал, нужны:
> сервер (Hetzner) и ключ **Claude API**. Транскрибация — **бесплатный whisper.cpp** (локально, собирается в Docker).
> Деплой — см. `deploy-hetzner.md`.

## Что делает

`POST /process` (multipart: `video` — файл, `roomName` — необязательно; заголовок `Authorization: Bearer <API_TOKEN>`):
1. `ffmpeg` извлекает аудио из видео.
2. **whisper.cpp** транскрибирует речь **с таймкодами** (бесплатно, на сервере).
3. Claude (с каталогом Wallcov) возвращает JSON: комнаты, описание состояния основы, **дефекты с таймкодами**, позиции сметы (работы/материалы с ценами из каталога, площади из размеров).
4. `ffmpeg` вырезает **кадр на таймкоде каждого дефекта** и прикрепляет его к комнате (base64).
5. Возвращает JSON, которым приложение автозаполняет смету и Акт обследования.

Формат ответа (упрощённо):
```json
{ "rooms": [ {
  "name": "Кімната 1",
  "dimensions": { "L": 5, "W": 4, "H": 2.7 },
  "inspect": "Стіни з тріщинами біля вікна, висока вологість у кутку…",
  "defects": [ { "description": "Тріщина біля вікна", "timestamp": 42 } ],
  "items": [ { "name": "Ґрунтування стін (2 рази)", "unit": "м²", "qty": 48.6, "price": 60, "kind": "work" } ],
  "photos": [ { "caption": "Тріщина біля вікна", "dataUrl": "data:image/jpeg;base64,..." } ]
} ] }
```

## Развёртывание на Hetzner (когда будут доступы)

```bash
# на сервере (Ubuntu)
sudo apt-get update && sudo apt-get install -y ffmpeg
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs

git clone <repo> && cd ai-backend
npm install
cp .env.example .env   # вписать ключи
npm start              # слушает :8080

# для постоянной работы:
sudo npm i -g pm2 && pm2 start server.js --name wallcov-ai && pm2 save
```
Поставьте перед сервером Nginx + домен + HTTPS (Let's Encrypt). Ограничьте `/process` авторизацией (токен), чтобы ключами не пользовались чужие.

## Интеграция с приложением (decorator.html)

В приложении в каждой комнате добавить кнопку «🎬 Відеообхід»: запись видео → `POST /process` →
полученные `rooms[]` влить в текущую комнату (items, inspect, photos). Это делается отдельным шагом
после деплоя бэкенда.

## Что нужно от вас

- Доступ к серверу Hetzner (SSH) — куда деплоить (или развернуть самим по `deploy-hetzner.md`).
- Отдельный ключ **Claude API** (`ANTHROPIC_API_KEY`) — как создать, см. `deploy-hetzner.md`, шаг 0.
- Транскрибация — бесплатно, whisper.cpp (ключи не нужны).
