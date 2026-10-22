#!/usr/bin/env node
// Two-account isolation test for Mnemos Cloud MCP. Node.js built-ins only.
// Never prints or saves passwords or access tokens. Creates two tagged test memories.

import readline from "node:readline/promises";
import { stdin, stdout } from "node:process";

const PROJECT_URL = "https://kuditcnmasfjgzmimnlc.supabase.co";
const PUBLISHABLE_KEY = "sb_publishable_g73Xe5kQC19cR1nNXVtRWA_WzkRM-kI";
const MCP_URL = `${PROJECT_URL}/functions/v1/mnemos-mcp`;

function askHidden(question) {
  return new Promise((resolve, reject) => {
    if (!stdin.isTTY || typeof stdin.setRawMode !== "function") {
      reject(new Error("Jalankan di terminal interaktif agar password tidak terlihat."));
      return;
    }
    stdout.write(question);
    let value = "";
    const wasRaw = stdin.isRaw;
    stdin.setRawMode(true);
    stdin.resume();
    const onData = (chunk) => {
      for (const ch of chunk.toString("utf8")) {
        if (ch === "\r" || ch === "\n") {
          stdin.off("data", onData);
          stdin.setRawMode(wasRaw ?? false);
          stdin.pause();
          stdout.write("\n");
          resolve(value);
          return;
        }
        if (ch === "\u0003") {
          stdin.off("data", onData);
          stdin.setRawMode(wasRaw ?? false);
          stdin.pause();
          reject(new Error("Dibatalkan."));
          return;
        }
        if (ch === "\u007f" || ch === "\b") {
          if (value.length) { value = value.slice(0, -1); stdout.write("\b \b"); }
        } else if (ch >= " ") { value += ch; stdout.write("*"); }
      }
    };
    stdin.on("data", onData);
  });
}

async function login(email, password) {
  const r = await fetch(`${PROJECT_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: PUBLISHABLE_KEY, "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok || typeof body.access_token !== "string") {
    const detail = [body.msg, body.message, body.error_description, body.code].filter(x => typeof x === "string").join(" | ");
    throw new Error(`Login gagal untuk salah satu akun (HTTP ${r.status})${detail ? `: ${detail}` : ""}`);
  }
  return body.access_token;
}

async function mcp(token, id, method, params) {
  const r = await fetch(MCP_URL, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, apikey: PUBLISHABLE_KEY, "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, ...(params ? { params } : {}) }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`MCP HTTP ${r.status}: ${JSON.stringify(body).slice(0, 300)}`);
  if (body.error) throw new Error(`MCP RPC error: ${JSON.stringify(body.error)}`);
  return body.result;
}

async function tool(token, id, name, args) {
  const result = await mcp(token, id, "tools/call", { name, arguments: args });
  if (result?.isError) return { __toolError: true, message: result.content?.[0]?.text ?? "tool error" };
  if (result?.structuredContent !== undefined) return result.structuredContent;
  const t = result?.content?.find(p => p.type === "text")?.text;
  if (t === undefined) return result;
  try { return JSON.parse(t); } catch { return t; }
}

function assert(condition, message) {
  if (!condition) throw new Error(`ISOLATION TEST FAILED: ${message}`);
}

try {
  const rl = readline.createInterface({ input: stdin, output: stdout });
  const emailA = (await rl.question("Email akun A (pemilik memori): ")).trim();
  const emailB = (await rl.question("Email akun B (akun penguji): ")).trim();
  rl.close();
  if (!emailA || !emailB || emailA.toLowerCase() === emailB.toLowerCase()) {
    throw new Error("Masukkan dua email akun berbeda.");
  }
  const passwordA = await askHidden("Password akun A: ");
  const passwordB = await askHidden("Password akun B: ");
  stdout.write("Login kedua akun... ");
  const tokenA = await login(emailA, passwordA);
  const tokenB = await login(emailB, passwordB);
  stdout.write("OK\nMembuat memori penanda terpisah... ");
  const markerA = `ISOLATION_A_${crypto.randomUUID()}`;
  const markerB = `ISOLATION_B_${crypto.randomUUID()}`;
  const a = await tool(tokenA, 1, "mnemos_add", { content: markerA, kind: "security-test", tags: ["cloud-isolation-test"], source: "cloud-isolation-test-script" });
  assert(typeof a?.id === "string", "akun A gagal membuat memori");
  const b = await tool(tokenB, 2, "mnemos_add", { content: markerB, kind: "security-test", tags: ["cloud-isolation-test"], source: "cloud-isolation-test-script" });
  assert(typeof b?.id === "string", "akun B gagal membuat memori");
  stdout.write("OK\n");

  stdout.write("Akses langsung B ke UUID milik A... ");
  const crossGet = await tool(tokenB, 3, "mnemos_get", { memory_id: a.id });
  assert(crossGet === null || crossGet?.id !== a.id, "akun B berhasil membaca memori akun A");
  stdout.write("PASS\n");

  stdout.write("Pencarian B terhadap marker A... ");
  const crossSearch = await tool(tokenB, 4, "mnemos_search", { query: markerA, limit: 20 });
  assert(Array.isArray(crossSearch) && !crossSearch.some(x => x.id === a.id || x.content === markerA), "pencarian akun B membocorkan memori akun A");
  stdout.write("PASS\n");

  stdout.write("Export B tidak memuat memori A... ");
  const exportB = await tool(tokenB, 5, "mnemos_export", {});
  assert(Array.isArray(exportB?.memories) && !exportB.memories.some(x => x.id === a.id || x.content === markerA), "export akun B membocorkan memori akun A");
  stdout.write("PASS\n");

  stdout.write("B tidak dapat membuat link ke memori A... ");
  const link = await tool(tokenB, 6, "mnemos_link", { source_id: b.id, target_id: a.id, relation: "isolation-test" });
  assert(link?.__toolError === true, "akun B berhasil menghubungkan memori miliknya ke memori akun A");
  stdout.write("PASS\n");

  stdout.write("\nBERHASIL: uji isolasi dua akun lulus.\n");
  stdout.write(`- Memori A: ${a.id}\n- Memori B: ${b.id}\n- Cross-user get/search/export/link: semua ditolak/terisolasi.\n`);
  stdout.write("Dua memori bertag cloud-isolation-test sengaja ditinggalkan untuk pemeriksaan. Token/password tidak ditampilkan atau disimpan.\n");
} catch (error) {
  console.error(`\nGAGAL: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
}
