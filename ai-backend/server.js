// Wallcov AI backend.
// Поток: видео по комнате → ffmpeg (аудио) → whisper.cpp (текст с таймкодами, БЕСПЛАТНО, локально)
//        → Claude (смета + описание осмотра + таймкоды дефектов)
//        → ffmpeg вырезает кадры дефектов → возвращаем JSON приложению.
//
// ENV: ANTHROPIC_API_KEY (обязателен), API_TOKEN (защита эндпоинта),
//      WHISPER_BIN, WHISPER_MODEL, WHISPER_LANG (по умолчанию auto), ANTHROPIC_MODEL.
// Нужны в системе: ffmpeg и собранный whisper.cpp (в Docker уже всё есть).

import express from "express";
import cors from "cors";
import crypto from "node:crypto";
import multer from "multer";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs/promises";
import os from "node:os";
import Anthropic from "@anthropic-ai/sdk";
import { SYSTEM_PROMPT } from "./prompt.js";

const execFileP = promisify(execFile);
const app = express();
app.use(cors());
const upload = multer({ dest: os.tmpdir(), limits: { fileSize: 250 * 1024 * 1024 } });

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const MODEL = process.env.ANTHROPIC_MODEL || "claude-opus-4-8"; // краща якість; для економії — claude-sonnet-4-6 у .env
const WHISPER_BIN = process.env.WHISPER_BIN || "/opt/whisper/build/bin/whisper-cli";
const WHISPER_MODEL = process.env.WHISPER_MODEL || "/opt/whisper/models/ggml-small.bin";
const WHISPER_LANG = process.env.WHISPER_LANG || "auto";
const THREADS = String(os.cpus().length || 2);

// Захист: перевіряємо токен входу в кабінет (той самий JWT_SECRET, що й у cabinet-backend)
const JWT_SECRET = process.env.JWT_SECRET || "";
function verifyToken(tok) {
  if (!tok || !JWT_SECRET) return null;
  const [b, s] = tok.split(".");
  if (!b || !s) return null;
  const e = crypto.createHmac("sha256", JWT_SECRET).update(b).digest("base64url");
  const A = Buffer.from(s), B = Buffer.from(e);
  if (A.length !== B.length || !crypto.timingSafeEqual(A, B)) return null;
  try { return JSON.parse(Buffer.from(b, "base64url").toString()); } catch (_) { return null; }
}
app.use((req, res, next) => {
  if (req.path === "/health") return next();
  const p = verifyToken((req.get("authorization") || "").replace(/^Bearer /, ""));
  if (!p) return res.status(401).json({ error: "Потрібно увійти в кабінет" });
  next();
});

app.get("/health", (_req, res) => res.json({ ok: true }));

// whisper.cpp → сегменти з таймкодами (секунди)
async function transcribe(wavPath) {
  const prefix = wavPath + ".out";
  await execFileP(WHISPER_BIN, ["-m", WHISPER_MODEL, "-f", wavPath, "-l", WHISPER_LANG, "-t", THREADS, "-oj", "-of", prefix], { maxBuffer: 64 * 1024 * 1024 });
  const json = JSON.parse(await fs.readFile(prefix + ".json", "utf8"));
  await fs.unlink(prefix + ".json").catch(() => {});
  return (json.transcription || []).map((s) => ({
    start: Math.round((s.offsets?.from ?? 0) / 1000),
    text: (s.text || "").trim(),
  }));
}

// POST /polish — покращення формулювань опису (без зміни змісту)
app.post("/polish", express.json({ limit: "1mb" }), async (req, res) => {
  const text = String(req.body?.text || "").trim();
  if (!text) return res.status(400).json({ error: "Порожній текст" });
  const lang = req.body?.lang === "ru" ? "російською мовою" : "українською мовою";
  try {
    const msg = await anthropic.messages.create({
      model: MODEL, max_tokens: 900,
      system: `Ти — помічник майстра-оздоблювача. Тобі дають чернетку опису стану поверхонь (обстеження основи) для акта. Завдання: виправити граматику й орфографію, зробити формулювання професійними, чіткими та зрозумілими для документа. КАТЕГОРИЧНО НЕ МОЖНА: додавати нові факти, цифри чи деталі, яких немає в тексті; змінювати зміст або висновки автора; вигадувати. Збережи всі смисли як написав майстер. Поверни ЛИШЕ виправлений текст ${lang}, без коментарів і без лапок.`,
      messages: [{ role: "user", content: text }],
    });
    const out = msg.content.map((c) => (c.type === "text" ? c.text : "")).join("").trim();
    res.json({ text: out || text });
  } catch (e) { console.error(e); res.status(500).json({ error: String(e.message || e) }); }
});

// POST /process (multipart: video, roomName?)
app.post("/process", upload.single("video"), async (req, res) => {
  const videoPath = req.file?.path;
  if (!videoPath) return res.status(400).json({ error: "no video" });
  const wavPath = videoPath + ".wav";
  try {
    // 1) аудіо у wav 16k моно (для whisper.cpp)
    await execFileP("ffmpeg", ["-y", "-i", videoPath, "-vn", "-ac", "1", "-ar", "16000", wavPath]);

    // 2) транскрибація з таймкодами
    const segments = await transcribe(wavPath);
    const transcript = segments.map((s) => `[${s.start}s] ${s.text}`).join("\n");
    if (!transcript) return res.status(422).json({ error: "empty transcript" });

    // 3) Claude → структурований JSON
    const userContent =
      (req.body.roomName ? `Кімната за замовчуванням: ${req.body.roomName}\n\n` : "") +
      `Транскрипт відеообходу (таймкоди в секундах):\n${transcript}`;
    const msg = await anthropic.messages.create({
      model: MODEL, max_tokens: 8000, system: SYSTEM_PROMPT,
      messages: [{ role: "user", content: userContent }],
    });
    const raw = msg.content.map((c) => (c.type === "text" ? c.text : "")).join("");
    const json = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1));

    // 4) кадри дефектів на таймкодах
    for (const room of json.rooms || []) {
      room.photos = [];
      for (const d of room.defects || []) {
        if (typeof d.timestamp !== "number") continue;
        const frame = `${videoPath}.${d.timestamp}.jpg`;
        try {
          await execFileP("ffmpeg", ["-y", "-ss", String(d.timestamp), "-i", videoPath, "-frames:v", "1", "-vf", "scale=1100:-1", frame]);
          const b = await fs.readFile(frame);
          room.photos.push({ caption: d.description, dataUrl: "data:image/jpeg;base64," + b.toString("base64") });
          await fs.unlink(frame).catch(() => {});
        } catch (_) {}
      }
    }
    res.json(json);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: String(e.message || e) });
  } finally {
    await fs.unlink(videoPath).catch(() => {});
    await fs.unlink(wavPath).catch(() => {});
  }
});

const PORT = process.env.PORT || 8080;
app.listen(PORT, () => console.log(`Wallcov AI backend на :${PORT} (whisper.cpp, model=${WHISPER_MODEL})`));
