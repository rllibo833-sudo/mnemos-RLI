import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const reply = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { ...cors, "Content-Type": "application/json", "Cache-Control": "no-store" },
  });

const UUID = /^[0-9a-f-]{36}$/i;
const REPOSITORY = "rllibo833-sudo/mnemos-RLI";
const EVENT_TYPE = "run-beyond-light-python";

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return reply({ error: "POST required" }, 405);

  const base = Deno.env.get("SUPABASE_URL");
  const publicKey = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("SUPABASE_PUBLISHABLE_KEY");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const githubToken = Deno.env.get("MNEMOS_GITHUB_TOKEN");

  if (!base || !publicKey || !serviceKey) {
    return reply({ error: "Supabase function environment is incomplete." }, 500);
  }
  if (!githubToken) {
    return reply({ error: "MNEMOS_GITHUB_TOKEN is not configured in Supabase Edge Function secrets." }, 503);
  }

  const authorization = req.headers.get("Authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) return reply({ error: "Sign-in required." }, 401);

  try {
    const userResponse = await fetch(base + "/auth/v1/user", {
      headers: { apikey: publicKey, Authorization: authorization },
    });
    if (!userResponse.ok) return reply({ error: "Invalid or expired Supabase session." }, 401);
    const user = await userResponse.json();
    if (!user?.id) return reply({ error: "Authenticated user identity is unavailable." }, 401);

    let input: Record<string, unknown>;
    try {
      input = await req.json();
    } catch {
      return reply({ error: "A JSON request body is required." }, 400);
    }
    const workspaceId = String(input.knowledge_workspace_id ?? "");
    if (!UUID.test(workspaceId)) return reply({ error: "Valid knowledge_workspace_id required." }, 400);
    if (input.mode !== undefined && input.mode !== "full") {
      return reply({ error: "Only the full Python engine run is supported." }, 400);
    }

    const adminHeaders = {
      apikey: serviceKey,
      Authorization: "Bearer " + serviceKey,
      Accept: "application/json",
    };
    const workspaceResponse = await fetch(
      base + "/rest/v1/knowledge_workspaces?id=eq." + encodeURIComponent(workspaceId) + "&select=id,owner_id&limit=1",
      { headers: adminHeaders },
    );
    if (!workspaceResponse.ok) return reply({ error: "Could not verify Knowledge workspace." }, 502);
    const workspace = (await workspaceResponse.json())[0];
    if (!workspace) return reply({ error: "Knowledge workspace not found." }, 404);

    let allowed = workspace.owner_id === user.id;
    if (!allowed) {
      const memberResponse = await fetch(
        base + "/rest/v1/knowledge_workspace_members?workspace_id=eq." + encodeURIComponent(workspaceId) +
          "&user_id=eq." + encodeURIComponent(user.id) + "&select=role&limit=1",
        { headers: adminHeaders },
      );
      if (!memberResponse.ok) return reply({ error: "Could not verify Knowledge workspace membership." }, 502);
      const membership = (await memberResponse.json())[0];
      allowed = membership?.role === "writer" || membership?.role === "admin";
    }
    if (!allowed) return reply({ error: "Knowledge workspace writer or admin access is required." }, 403);

    const requestId = crypto.randomUUID();
    const dispatch = await fetch("https://api.github.com/repos/" + REPOSITORY + "/dispatches", {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: "Bearer " + githubToken,
        "Content-Type": "application/json",
        "User-Agent": "Mnemos-Beyond-Light-Runner",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        event_type: EVENT_TYPE,
        client_payload: {
          request_id: requestId,
          workspace_id: workspaceId,
          requested_by: user.id,
          source_repository: "rllibo833-sudo/Beyond-Light",
          source_ref: "python-migration",
          mode: "full",
        },
      }),
    });
    if (!dispatch.ok) {
      const detail = (await dispatch.text()).slice(0, 400);
      console.error("GitHub repository_dispatch failed:", dispatch.status, detail);
      return reply({ error: "Could not queue the Python engine run.", upstream_status: dispatch.status }, 502);
    }

    return reply({
      ok: true,
      queued: true,
      request_id: requestId,
      source: "rllibo833-sudo/Beyond-Light@python-migration",
      canonical_target: "mnemos-RLI:Knowledge",
      transport: "Supabase mnemos_outbox",
      workflow_url: "https://github.com/" + REPOSITORY + "/actions/workflows/run-beyond-light-python.yml",
      message: "The Python engine run was queued. Results will be published to the canonical Knowledge branch after validation.",
    }, 202);
  } catch (error) {
    console.error("Beyond-Light run dispatch error:", error);
    return reply({ error: error instanceof Error ? error.message : "Unexpected dispatch error." }, 500);
  }
});
