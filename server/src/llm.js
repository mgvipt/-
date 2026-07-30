// Вызов LLM (Claude / OpenAI) на серверном ключе. TEST_LLM=1 — заглушка без сети.
import { CONFIG, SYSTEM_PROMPT } from "./config.js";

export async function chat(messages, context) {
  var system = SYSTEM_PROMPT + (context ? "\n\n" + context : "");
  if (CONFIG.testLLM) {
    var last = messages.length ? messages[messages.length - 1].content : "";
    return { text: "Я рядом. (демо-ответ сервера) Ты спросила: " + String(last).slice(0, 80), inTok: 200, outTok: 40, model: CONFIG.model };
  }
  return CONFIG.provider === "openai" ? openai(messages, system) : anthropic(messages, system);
}

async function anthropic(messages, system) {
  var r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "content-type": "application/json", "x-api-key": CONFIG.anthropicKey, "anthropic-version": "2023-06-01" },
    body: JSON.stringify({ model: CONFIG.model, max_tokens: CONFIG.maxTokens, system: system, messages: messages })
  });
  var d = await r.json();
  if (d.error) throw new Error(d.error.message || "anthropic error");
  var block = (d.content || []).find(b => b.type === "text");
  return { text: (block && block.text) || "…", inTok: (d.usage && d.usage.input_tokens) || 0, outTok: (d.usage && d.usage.output_tokens) || 0, model: CONFIG.model };
}

async function openai(messages, system) {
  var msgs = [{ role: "system", content: system }].concat(messages);
  var r = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { "content-type": "application/json", authorization: "Bearer " + CONFIG.openaiKey },
    body: JSON.stringify({ model: CONFIG.model, max_tokens: CONFIG.maxTokens, messages: msgs })
  });
  var d = await r.json();
  if (d.error) throw new Error(d.error.message || "openai error");
  var u = d.usage || {};
  return { text: (d.choices && d.choices[0] && d.choices[0].message.content) || "…", inTok: u.prompt_tokens || 0, outTok: u.completion_tokens || 0, model: CONFIG.model };
}
