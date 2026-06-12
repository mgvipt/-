// Wallcov AI backend — каркас.
// Потік: відео по кімнаті → витяг аудіо (ffmpeg) → транскрибація (Whisper)
//        → ИИ Claude (смета + опис осмотра + таймкоди дефектів)
//        → кадри ffmpeg на таймкодах → повертаємо JSON у застосунок.
//
// ПОТРІБНІ ключі (env): ANTHROPIC_API_KEY, OPENAI_API_KEY (для Whisper).
// ПОТРІБЕН ffmpeg у системі (apt-get install -y ffmpeg).

import express from "express";
import cors from "cors";
import multer from "multer";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs/promises";
import { createReadStream } from "node:fs";
import os from "node:os";
import path from "node:path";
import Anthropic from "@anthropic-ai/sdk";
import OpenAI from "openai";
import { SYSTEM_PROMPT } from "./prompt.js";

const execFileP = promisify(execFile);
const app = express();
app.use(cors());
const upload = multer({ dest: os.tmpdir(), limits: { fileSize: 200 * 1024 * 1024 } });

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
const MODEL = process.env.ANTHROPIC_MODEL || "claude-sonnet-4-6"; // або claude-opus-4-8 для кращої якості

app.get("/health", (_req, res) => res.json({ ok: true }));

// POST /process  (multipart: field "video", optional "roomName")
app.post("/process", upload.single("video"), async (req, res) => {
  const videoPath = req.file?.path;
  if (!videoPath) return res.status(400).json({ error: "no video" });
  const audioPath = videoPath + ".mp3";
  try {
    // 1) Витяг аудіо
    await execFileP("ffmpeg", ["-y", "-i", videoPath, "-vn", "-ac", "1", "-ar", "16000", audioPath]);

    // 2) Транскрибація з таймкодами (сегменти)
    const tr = await openai.audio.transcriptions.create({
      file: createReadStream(audioPath),
      model: "whisper-1",
      response_format: "verbose_json",
      timestamp_granularities: ["segment"],
    });
    const transcript = (tr.segments || [])
      .map((s) => `[${Math.round(s.start)}s] ${s.text.trim()}`)
      .join("\n") || tr.text || "";

    // 3) ИИ Claude → структурований JSON
    const userContent =
      (req.body.roomName ? `Кімната за замовчуванням: ${req.body.roomName}\n\n` : "") +
      `Транскрипт відеообходу (з таймкодами в секундах):\n${transcript}`;
    const msg = await anthropic.messages.create({
      model: MODEL,
      max_tokens: 4000,
      system: SYSTEM_PROMPT,
      messages: [{ role: "user", content: userContent }],
    });
    const raw = msg.content.map((c) => (c.type === "text" ? c.text : "")).join("");
    const json = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1));

    // 4) Кадри ffmpeg на таймкодах дефектів → base64, прикріплюємо до кімнати
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
    await fs.unlink(audioPath).catch(() => {});
  }
});

const PORT = process.env.PORT || 8080;
app.listen(PORT, () => console.log(`Wallcov AI backend на :${PORT}`));
