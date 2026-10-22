#!/usr/bin/env node
// Authenticated smoke test for the Mnemos Cloud MCP endpoint.
// Uses Node.js built-ins only. Never prints or saves the user's password or access token.

import readline from "node:readline/promises";
import { stdin, stdout } from "node:process";

const PROJECT_URL = "https://kuditcnmasfjgzmimnlc.supabase.co";
const PUBLISHABLE_KEY = "sb_publishable_g73Xe5kQC19cR1nNXVtRWA_WzkRM-kI";
const MCP_URL = `${PROJECT_URL}/functions/v1/mnemos-mcp`;

function askHidden(question) {
  return new Promise((resolve, reject) => {
    if (!stdin.isTTY || typeof stdin.setRawMode !== "function") {
      reject(new Error("Run this script in an interactive terminal so the password can be hidden."));
      return;
    }
    stdout.write(question);
    let value = "";
    const wasRaw = stdin.isRaw;
    stdin.setRawMode(true);
    stdin.resume();
    const onData = (chunk) => {
      const s = chunk.toString("utf8");
      for (const ch of s) {
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
          reject(new Error("Cancelled."));
          return;
        }
        if (ch === "\u007f" || ch === "\b") value = value.slice(0, -1);
        else if (ch >= " ") value += ch;
      }
    };
    stdin.on("data", onData);
  });
}

async function mcp(token, id, method, params) {
  const response = await fetch(MCP_URL, {
    method: "POST",
    headers: {
      "authorization": `Bearer ${token}`,
      "apikey": PUBLISHABLE_KEY,
      "content-type": "application/json",
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, ...(params ? { params } : {}) }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`MCP HTTP ${response.status}: ${JSON.stringify(body).slice(0, 500)}`);
  if (body.error) throw new Error(`MCP RPC error: ${JSON.stringify(body.error)}`);
  if (body.result?.isError) throw new Error(body.result.content?.[0]?.text ?? "MCP tool failed");
  return body.result;
}

async function tool(token, id, name, args) {
  const result = await mcp(token, id, "tools/call", { name, arguments: args });
  if (result?.structuredContent !== undefined) return result.structuredContent;
  const text = result?.content?.find((part) => part.type === "text")?.text;
  if (text === undefined) return result;
  try { return JSON.parse(text); } catch { return text; }
}

try {
  const rl = readline.createInterface({ input: stdin, output: stdout });
  const email = (await rl.question("Email akun Supabase Mnemos: ")).trim();
  rl.close();
  const password = await askHidden("Password akun (tidak akan ditampilkan): ");
  if (!email || !password) throw new Error("Email dan password wajib diisi.");

  stdout.write("Login ke Supabase Auth... ");
  const loginResponse = await fetch(`${PROJECT_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { "apikey": PUBLISHABLE_KEY, "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const session = await loginResponse.json().catch(() => ({}));
  if (!loginResponse.ok || typeof session.access_token !== "string") {
    throw new Error(`Login gagal (HTTP ${loginResponse.status}). Periksa email/password dan status konfirmasi akun di Supabase Auth.`);
  }
  const token = session.access_token;
  stdout.write("OK\nMenguji MCP initialize... ");
  await mcp(token, 1, "initialize", {
    protocolVersion: "2025-03-26",
    capabilities: {},
    clientInfo: { name: "mnemos-cloud-smoke-test", version: "1.0.0" },
  });
  stdout.write("OK\nMenguji tools/list... ");
  const listed = await mcp(token, 2, "tools/list");
  const names = (listed?.tools ?? []).map((x) => x.name);
  for (const required of ["mnemos_add", "mnemos_get", "mnemos_search", "mnemos_export"]) {
    if (!names.includes(required)) throw new Error(`Tool hilang: ${required}`);
  }
  stdout.write("OK\nMenguji add/get/search/export pada database cloud... ");
  const marker = `Mnemos cloud smoke test ${new Date().toISOString()} ${Math.random().toString(36).slice(2, 8)}`;
  const added = await tool(token, 3, "mnemos_add", {
    content: marker,
    kind: "test",
    tags: ["cloud-smoke-test"],
    source: "cloud-smoke-test-script",
  });
  const memoryId = added?.id;
  if (typeof memoryId !== "string") throw new Error("mnemos_add tidak mengembalikan ID memori.");
  const fetched = await tool(token, 4, "mnemos_get", { memory_id: memoryId });
  if (fetched?.id !== memoryId || fetched?.content !== marker) throw new Error("mnemos_get tidak mengembalikan memori yang baru dibuat.");
  const searched = await tool(token, 5, "mnemos_search", { query: marker, limit: 10 });
  if (!Array.isArray(searched) || !searched.some((x) => x.id === memoryId)) throw new Error("mnemos_search tidak menemukan memori yang baru dibuat.");
  const exported = await tool(token, 6, "mnemos_export", {});
  if (!Array.isArray(exported?.memories) || !exported.memories.some((x) => x.id === memoryId)) throw new Error("mnemos_export tidak menyertakan memori yang baru dibuat.");
  stdout.write("\nBERHASIL: authenticated end-to-end cloud round trip lulus.\n");
  stdout.write(`- Auth login: OK\n- MCP initialize/tools/list: OK\n- mnemos_add: OK\n- mnemos_get: OK\n- mnemos_search: OK\n- mnemos_export: OK\n- Test memory ID: ${memoryId}\n`);
  stdout.write("Satu memori bertag cloud-smoke-test sengaja ditinggalkan di akun ini untuk pemeriksaan. Token/password tidak ditampilkan atau disimpan.\n");
} catch (error) {
  console.error(`\nGAGAL: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
}
