import { api } from "./api";
/* Звуковий рушій (Web Audio) — БАГАТЕ звучання: реверберація + гармоніки + хор + поліфонія (акорди).
   Дзвінок — довгі мелодійні рінгтони ЦИКЛОМ + можливість завантажити свій аудіо-файл. */

let _ctx: AudioContext | null = null;
let _bus: GainNode | null = null;
function ac(): AudioContext {
  if (!_ctx) _ctx = new ((window as any).AudioContext || (window as any).webkitAudioContext)();
  const c = _ctx as AudioContext;
  if (c.state === "suspended") c.resume();
  return c;
}
// синтетична реверберація (затухаючий шум) — додає об'єм/«дорогий» звук
function makeReverb(c: AudioContext): ConvolverNode {
  const len = Math.floor(c.sampleRate * 1.6);
  const buf = c.createBuffer(2, len, c.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.6);
  }
  const conv = c.createConvolver(); conv.buffer = buf; return conv;
}
// шина: dry + wet(reverb) → вихід
function bus(c: AudioContext): GainNode {
  if (!_bus) {
    _bus = c.createGain(); _bus.gain.value = 0.85;
    const dry = c.createGain(); dry.gain.value = 0.78;
    const wet = c.createGain(); wet.gain.value = 0.42;
    const rev = makeReverb(c);
    _bus.connect(dry); dry.connect(c.destination);
    _bus.connect(rev); rev.connect(wet); wet.connect(c.destination);
  }
  return _bus;
}
if (typeof window !== "undefined") {
  const unlock = () => { try { ac(); } catch {} window.removeEventListener("pointerdown", unlock); };
  window.addEventListener("pointerdown", unlock);
}

// багатий голос: фундамент + гармоніки (partials) + лёгкий хор (detune) + ADSR
type VoiceOpts = { type?: OscillatorType; partials?: number[]; detune?: number; peak?: number; decay?: number };
function voice(c: AudioContext, freq: number, t0: number, dur: number, o: VoiceOpts = {}) {
  const { type = "sine", partials = [1, 0.5, 0.3], detune = 5, peak = 0.32, decay = 0.85 } = o;
  const out = c.createGain(); out.connect(bus(c));
  out.gain.setValueAtTime(0.0001, t0);
  out.gain.exponentialRampToValueAtTime(peak, t0 + 0.01);
  out.gain.exponentialRampToValueAtTime(peak * 0.55, t0 + 0.06);
  out.gain.exponentialRampToValueAtTime(0.0001, t0 + dur * decay);
  partials.forEach((amp, i) => {
    const osc = c.createOscillator(); const g = c.createGain();
    osc.type = type; osc.frequency.value = freq * (i + 1);
    if (detune) osc.detune.value = i % 2 ? detune : -detune;
    g.gain.value = amp; osc.connect(g); g.connect(out);
    osc.start(t0); osc.stop(t0 + dur + 0.06);
  });
}
// дзвоник (FM-метал) — багатий, «скляний»
function bell(c: AudioContext, freq: number, t0: number, dur: number, peak = 0.3) {
  voice(c, freq, t0, dur, { type: "sine", partials: [1, 0.0, 0.0, 0.6, 0.0, 0.35, 0.0, 0.2], detune: 0, peak, decay: 0.95 });
}
// акорд (поліфонія)
function chord(c: AudioContext, freqs: number[], t0: number, dur: number, o: VoiceOpts = {}) { freqs.forEach((f) => voice(c, f, t0, dur, o)); }

// ноти: [freq, offset, dur]
function seq(c: AudioContext, notes: [number, number, number][], o: VoiceOpts = {}) {
  const t = c.currentTime; notes.forEach(([f, off, d]) => voice(c, f, t + off, d, o));
}

type Sound = { label: string; play?: (c: AudioContext) => void; file?: string };
type Ring = { label: string; dur?: number; play?: (c: AudioContext) => void; file?: string };

// ── короткі сигнали повідомлень (реальні MP3 CC0 + синтез) ──
export const SOUNDS: Record<string, Sound> = {
  real_notify: { label: "Сповіщення (MP3)", file: "/sounds/msg_notify.mp3" },
  real_confirm: { label: "Підтвердження (MP3)", file: "/sounds/msg_confirm.mp3" },
  real_glass: { label: "Скло (MP3)", file: "/sounds/msg_glass.mp3" },
  bloom: { label: "Розквіт (акорд)", play: (c) => { const t = c.currentTime; chord(c, [523, 659, 784], t, 0.9, { type: "triangle", peak: 0.26, decay: 0.9 }); bell(c, 1568, t + 0.05, 0.8, 0.18); } },
  ding: { label: "Дзвоник", play: (c) => { const t = c.currentTime; bell(c, 1318, t, 1.0, 0.34); } },
  notify: { label: "Дін-дон", play: (c) => seq(c, [[1568, 0, 0.6], [1175, 0.16, 0.9]], { type: "triangle", partials: [1, 0.4, 0.25], peak: 0.34, decay: 0.9 }) },
  drop: { label: "Крапля", play: (c) => seq(c, [[2093, 0, 0.5], [1568, 0.12, 0.8]], { type: "sine", partials: [1, 0.5], peak: 0.3 }) },
  sparkle: { label: "Іскра", play: (c) => { const t = c.currentTime;[1568, 2093, 2637].forEach((f, i) => bell(c, f, t + i * 0.08, 0.7, 0.2)); } },
  alert: { label: "Сигнал (активний)", play: (c) => { const t = c.currentTime; chord(c, [880, 1109], t, 0.3, { type: "triangle", peak: 0.3 }); chord(c, [1109, 1319], t + 0.26, 0.5, { type: "triangle", peak: 0.3 }); } },
  marimba: { label: "Марімба", play: (c) => seq(c, [[784, 0, 0.5], [1175, 0.13, 0.6]], { type: "sine", partials: [1, 0.0, 0.0, 0.45], peak: 0.34, decay: 0.7 }) },
  soft: { label: "Мʼякий", play: (c) => chord(c, [587, 880], c.currentTime, 0.9, { type: "sine", partials: [1, 0.4], peak: 0.3 }) },
};

// ── рінгтони дзвінка (реальні MP3 CC0 + синтез; dur = період циклу) ──
export const CALL_SOUNDS: Record<string, Ring> = {
  real_pizzi: { label: "Піцикато (MP3)", file: "/sounds/ring_pizzi.mp3" },
  real_sax: { label: "Саксофон (MP3)", file: "/sounds/ring_sax.mp3" },
  iphone_marimba: {
    label: "Марімба (стиль iPhone)", dur: 2.9,
    play: (c) => seq(c, [[1047, 0, 0.18], [1319, 0.14, 0.18], [1568, 0.28, 0.18], [2093, 0.42, 0.24], [1568, 0.62, 0.18], [1319, 0.76, 0.18], [1047, 0.9, 0.18], [1319, 1.08, 0.2], [1568, 1.24, 0.18], [2093, 1.4, 0.4]],
      { type: "sine", partials: [1, 0.0, 0.0, 0.5], peak: 0.34, decay: 0.7 }),
  },
  crystal: {
    label: "Кришталь", dur: 2.8,
    play: (c) => { const t = c.currentTime;[1568, 2093, 2637, 2093, 1865, 2349].forEach((f, i) => bell(c, f, t + i * 0.22, 0.9, 0.24)); } },
  harmony: {
    label: "Гармонія (акорди)", dur: 3.2,
    play: (c) => { const t = c.currentTime; chord(c, [523, 659, 784], t, 0.7, { type: "triangle", peak: 0.22 }); chord(c, [587, 740, 880], t + 0.7, 0.7, { type: "triangle", peak: 0.22 }); chord(c, [659, 784, 988], t + 1.4, 0.9, { type: "triangle", peak: 0.22 }); } },
  sunrise: {
    label: "Світанок", dur: 3.0,
    play: (c) => seq(c, [[784, 0, 0.3], [1047, 0.26, 0.3], [1319, 0.52, 0.3], [1568, 0.78, 0.34], [2093, 1.1, 0.6], [1568, 1.6, 0.5]],
      { type: "sine", partials: [1, 0.5, 0.25], peak: 0.32 }),
  },
  classic: {
    label: "Класичний телефон", dur: 2.2,
    play: (c) => { const t = c.currentTime; for (const f of [440, 480]) voice(c, f, t, 1.3, { type: "sine", partials: [1, 0.3], detune: 0, peak: 0.4, decay: 0.98 }); } },
  digital: {
    label: "Цифровий", dur: 2.4,
    play: (c) => seq(c, [[1568, 0, 0.16], [1175, 0.16, 0.16], [1568, 0.32, 0.16], [1175, 0.48, 0.16], [1865, 0.68, 0.3]],
      { type: "triangle", partials: [1, 0.4, 0.2], peak: 0.34 }),
  },
};

const LS_MSG = "crm_msg_sound", LS_CALL = "crm_call_sound", LS_MSG_ON = "crm_msg_sound_on", LS_CALL_ON = "crm_call_sound_on";
const LS_LIB = "crm_sound_lib";

export function getMsgSound() { return localStorage.getItem(LS_MSG) || "real_notify"; }
export function setMsgSound(v: string) { localStorage.setItem(LS_MSG, v); }
export function getCallSound() { return localStorage.getItem(LS_CALL) || "real_pizzi"; }
export function setCallSound(v: string) { localStorage.setItem(LS_CALL, v); }
export function msgSoundOn() { return localStorage.getItem(LS_MSG_ON) !== "0"; }
export function setMsgSoundOn(v: boolean) { localStorage.setItem(LS_MSG_ON, v ? "1" : "0"); }
export function callSoundOn() { return localStorage.getItem(LS_CALL_ON) !== "0"; }
export function setCallSoundOn(v: boolean) { localStorage.setItem(LS_CALL_ON, v ? "1" : "0"); }
const LS_TEAM = "crm_team_sound", LS_TEAM_ON = "crm_team_sound_on";
export function getTeamSound() { return localStorage.getItem(LS_TEAM) || "real_confirm"; }
export function setTeamSound(v: string) { localStorage.setItem(LS_TEAM, v); }
export function teamSoundOn() { return localStorage.getItem(LS_TEAM_ON) !== "0"; }
export function setTeamSoundOn(v: boolean) { localStorage.setItem(LS_TEAM_ON, v ? "1" : "0"); }

// Спільна бібліотека звуків — на сервері, доступна всім (не localStorage).
export type CustomSound = { id: number; name: string; url: string; by?: string };
let _lib: CustomSound[] = [];
let _canUploadSnd = false;
export function getLibrary(): CustomSound[] { return _lib; }
export function canUploadSounds(): boolean { return _canUploadSnd; }
export async function loadSoundLibrary(): Promise<void> {
  try {
    const r = await api.get<any>("/api/sounds/");
    _lib = (r && (r.items || r)) || [];
    _canUploadSnd = !!(r && r.can_upload);
    try { localStorage.setItem("crm_sound_lib_cache", JSON.stringify(_lib)); } catch { /* */ }
  } catch { /* */ }
}
export async function uploadSound(name: string, dataUrl: string): Promise<{ dedup?: boolean }> {
  const r = await api.post<any>("/api/sounds/", { name, data: dataUrl });
  await loadSoundLibrary();
  return { dedup: !!(r && r.dedup) };
}
export async function deleteSound(id: number): Promise<void> {
  await api.del(`/api/sounds/${id}/`);
  await loadSoundLibrary();
}
function _oldLocal(): { id: string; name: string; data: string }[] {
  try { return JSON.parse(localStorage.getItem("crm_sound_lib") || "[]"); } catch { return []; }
}
function _customUrl(id: string): string {
  let s: any = _lib.find((x) => String(x.id) === String(id));
  if (!s) { try { const cache = JSON.parse(localStorage.getItem("crm_sound_lib_cache") || "[]"); s = cache.find((x: any) => String(x.id) === String(id)); } catch { /* */ } }
  if (s) return s.url;
  const o = _oldLocal().find((x) => String(x.id) === String(id));  // fallback: старий локальний звук
  return o ? o.data : "";
}
// One-time migration of old local sounds (localStorage) into the SHARED server library.
export async function migrateLocalSounds(): Promise<number> {
  const old = _oldLocal();
  if (!old.length) return 0;
  const map: Record<string, string> = {};
  for (const snd of old) {
    try { const r = await api.post<any>("/api/sounds/", { name: snd.name || "Sound", data: snd.data }); if (r && r.id) map["custom:" + snd.id] = "custom:" + r.id; } catch { /* skip */ }
  }
  const remap = (get: () => string, set: (v: string) => void) => { const cur = get(); if (map[cur]) set(map[cur]); };
  remap(getMsgSound, setMsgSound);
  remap(getCallSound, setCallSound);
  remap(getTeamSound, setTeamSound);
  if (Object.keys(map).length === old.length) localStorage.removeItem("crm_sound_lib");
  await loadSoundLibrary();
  return Object.keys(map).length;
}
function _playFile(data: string, loop: boolean, onend?: () => void): () => void { try { const a = new Audio(data); a.loop = loop; a.volume = 1; a.play().catch(() => {}); if (onend) a.onended = onend; return () => { try { a.pause(); a.currentTime = 0; } catch {} }; } catch { return () => {}; } }

// прослуховування в налаштуваннях — зупиняється по повторному кліку / зміні / переході сторінки
let _previewStop: (() => void) | null = null;
let _previewKey = "";
export function stopPreview() { if (_previewStop) { try { _previewStop(); } catch {} } _previewStop = null; _previewKey = ""; }
export function previewSel(val: string, isCall: boolean) {
  const key = val + (isCall ? "|c" : "|m");
  if (_previewStop && _previewKey === key) { stopPreview(); return; } // повторний клік = стоп
  stopPreview();
  let data = "";
  if (val.startsWith("custom:")) data = _customUrl(val.slice(7));
  else { const s = isCall ? CALL_SOUNDS[val] : SOUNDS[val]; data = s?.file || ""; if (!data) { try { s?.play?.(ac()); } catch {} return; } }
  if (!data) return;
  _previewKey = key;
  _previewStop = _playFile(data, false, () => { if (_previewKey === key) { _previewStop = null; _previewKey = ""; } });
}

function playSnd(s: Sound | Ring | undefined) { if (!s) return; try { if (s.file) { _playFile(s.file, false); return; } s.play?.(ac()); } catch {} }
export function preview(map: Record<string, Sound>, name: string) { playSnd(map[name]); }
export function previewCall(name: string) { playSnd(CALL_SOUNDS[name]); }
export function playMessageSound() {
  if (!msgSoundOn()) return;
  const v = getMsgSound();
  if (v.startsWith("custom:")) { const u = _customUrl(v.slice(7)); if (u) { _playFile(u, false); return; } }
  playSnd(SOUNDS[v] || SOUNDS.real_notify);
}
export function playTeamSound() {
  if (!teamSoundOn()) return;
  const v = getTeamSound();
  if (v.startsWith("custom:")) { const u = _customUrl(v.slice(7)); if (u) { _playFile(u, false); return; } }
  playSnd(SOUNDS[v] || SOUNDS.real_confirm);
}

let _ringStop: (() => void) | null = null;
export function startCallRing() {
  stopCallRing();
  if (!callSoundOn()) return;
  const v = getCallSound();
  if (v.startsWith("custom:")) { const u = _customUrl(v.slice(7)); if (u) { _ringStop = _playFile(u, true); return; } }
  const r = CALL_SOUNDS[v] || CALL_SOUNDS.real_pizzi;
  if (r.file) { _ringStop = _playFile(r.file, true); return; }
  const c = ac();
  r.play?.(c);
  const iv = window.setInterval(() => { try { r.play?.(ac()); } catch {} }, (r.dur || 3) * 1000);
  _ringStop = () => clearInterval(iv);
}
export function stopCallRing() { if (_ringStop) { try { _ringStop(); } catch {} _ringStop = null; } }


// ── Розблокування звуку ──
// Браузери глушать programmatic-звук до першого жесту користувача. На перший клік/клавішу
// резюмуємо AudioContext і «праймимо» Audio — тоді дзвінок/сповіщення чутні одразу.
let _audioUnlocked = false;
export function unlockAudio() {
  if (_audioUnlocked) return;
  _audioUnlocked = true;
  try { const c = ac(); if (c.state === "suspended") c.resume(); } catch { /* */ }
  try { const a = new Audio(); a.muted = true; const pr = a.play(); if (pr && (pr as any).catch) (pr as any).catch(() => {}); } catch { /* */ }
}
if (typeof window !== "undefined") {
  const _uh = () => { unlockAudio(); };
  window.addEventListener("pointerdown", _uh, { once: true });
  window.addEventListener("keydown", _uh, { once: true });
  window.addEventListener("click", _uh, { once: true });
}
