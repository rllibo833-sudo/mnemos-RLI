import { readFile } from "node:fs/promises";

async function main() {
const base = process.env.SUPABASE_URL?.replace(/\/$/, "");
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!base || !key) throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required");
const acknowledgements = JSON.parse(await readFile(".mnemos-outbox-acks.json", "utf8"));
const commitSha = process.env.KNOWLEDGE_COMMIT_SHA;
if (!commitSha || !/^[0-9a-f]{40}$/i.test(commitSha)) throw new Error("KNOWLEDGE_COMMIT_SHA must be the verified commit SHA on origin/Knowledge");
for (const item of acknowledgements) {
  const response = await fetch(base + "/rest/v1/mnemos_outbox?id=eq." + encodeURIComponent(item.id) + "&payload_sha256=eq." + encodeURIComponent(item.payload_sha256) + "&delivered_at=is.null", {
    method: "PATCH",
    headers: { apikey: key, Authorization: "Bearer " + key, "Content-Type": "application/json", Prefer: "return=representation" },
    body: JSON.stringify({ delivered_at: new Date().toISOString(), delivery_commit: commitSha, last_error: null })
  });
  if (!response.ok) throw new Error("Outbox acknowledgement failed for " + item.id + ": HTTP " + response.status + " " + (await response.text()).slice(0, 300));
  const rows = await response.json();
  if (!Array.isArray(rows) || rows.length !== 1) throw new Error("Outbox acknowledgement did not update exactly one pending event: " + item.id);
}
const cutoff = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
const cleanup = await fetch(base + "/rest/v1/mnemos_outbox?delivered_at=lt." + encodeURIComponent(cutoff), { method: "DELETE", headers: { apikey: key, Authorization: "Bearer " + key, Prefer: "return=minimal" } });
if (!cleanup.ok) throw new Error("Delivered outbox cleanup failed: HTTP " + cleanup.status + " " + (await cleanup.text()).slice(0, 300));
console.log(JSON.stringify({ acknowledged: acknowledgements.length, delivered_retention_days: 7, cleanup: cleanup.status }));

}

main().catch(error => { console.error(error); process.exitCode = 1; });
