import { readFile } from "node:fs/promises";
const base = process.env.SUPABASE_URL?.replace(/\/$/, "");
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!base || !key) throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required");
const acknowledgements = JSON.parse(await readFile(".mnemos-outbox-acks.json", "utf8"));
for (const item of acknowledgements) {
  const response = await fetch(base + "/rest/v1/mnemos_outbox?id=eq." + encodeURIComponent(item.id) + "&payload_sha256=eq." + encodeURIComponent(item.payload_sha256) + "&delivered_at=is.null", {
    method: "PATCH",
    headers: { apikey: key, Authorization: "Bearer " + key, "Content-Type": "application/json", Prefer: "return=representation" },
    body: JSON.stringify({ delivered_at: new Date().toISOString(), delivery_commit: process.env.GITHUB_SHA || "verified-by-workflow", last_error: null })
  });
  if (!response.ok) throw new Error("Outbox acknowledgement failed for " + item.id + ": HTTP " + response.status + " " + (await response.text()).slice(0, 300));
  const rows = await response.json();
  if (!Array.isArray(rows) || rows.length !== 1) throw new Error("Outbox acknowledgement did not update exactly one pending event: " + item.id);
}
console.log(JSON.stringify({ acknowledged: acknowledgements.length }));
