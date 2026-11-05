package org.beyondlight;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Offline contract tests for Supabase outbox delivery and Mnemos Knowledge reads. */
public final class MnemosKnowledgeChecks {
    private static int checks;
    private MnemosKnowledgeChecks() {}

    public static void main(String[] args) throws Exception {
        run();
        System.out.println("Mnemos Knowledge integration checks passed: " + checks);
    }

    public static void run() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        Map<String, Map<String, Object>> outbox = new LinkedHashMap<>();
        AtomicInteger postRequests = new AtomicInteger();
        java.util.concurrent.atomic.AtomicBoolean bearerSeen = new java.util.concurrent.atomic.AtomicBoolean(false);
        java.util.concurrent.atomic.AtomicBoolean apiKeySeen = new java.util.concurrent.atomic.AtomicBoolean(false);
        server.createContext("/rest/v1/mnemos_outbox", exchange -> handleOutbox(exchange, outbox, postRequests, bearerSeen, apiKeySeen));
        server.createContext("/Knowledge/knowledge/manifest.json", exchange -> respond(exchange, 200, Map.of(
                "schema_version", 1, "source_of_truth", "mnemos-RLI:Knowledge",
                "generated_at", "2026-11-04T00:00:00Z",
                "node_files", List.of("alpha.json", "beta.json"),
                "edge_files", List.of("relations.json"))));
        server.createContext("/Knowledge/knowledge/nodes/alpha.json", exchange -> respond(exchange, 200,
                Map.of("id", "alpha", "kind", "concept", "title", "Energy storage", "content", "Battery chemistry")));
        server.createContext("/Knowledge/knowledge/nodes/beta.json", exchange -> respond(exchange, 200,
                Map.of("id", "beta", "kind", "source", "title", "Open paper", "content", "Research source")));
        server.createContext("/Knowledge/knowledge/edges/relations.json", exchange -> respond(exchange, 200,
                List.of(Map.of("source", "alpha", "target", "beta", "relation", "REFERENCES"))));
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            MnemosKnowledgeAdapter adapter = new MnemosKnowledgeAdapter(
                    java.net.http.HttpClient.newHttpClient(), URI.create(base), "sb_secret_test-only",
                    "f9a3cb1a-7eef-4d9c-86dd-e74414344bca", URI.create(base + "/Knowledge/knowledge/"));

            Map<String, Object> dispatch = fixtureDispatch();
            Map<String, Object> first = adapter.publish(dispatch);
            Map<String, Object> second = adapter.publish(dispatch);
            check("DELIVERED".equals(first.get("status")), "outbox acknowledgement is surfaced");
            check("DELIVERED".equals(second.get("status")), "idempotent retry returns existing acknowledgement");
            check(postRequests.get() == 2, "retry reuses the same outbox contract");
            check(apiKeySeen.get(), "Supabase API key is sent in the apikey header");
            check(!bearerSeen.get(), "modern Supabase secret key is never sent as a bearer token");
            MnemosKnowledgeAdapter legacyAdapter = new MnemosKnowledgeAdapter(
                    java.net.http.HttpClient.newHttpClient(), URI.create(base), "eyJlegacy-service-role-jwt",
                    "f9a3cb1a-7eef-4d9c-86dd-e74414344bca", URI.create(base + "/Knowledge/knowledge/"));
            legacyAdapter.deliveryStatus((String) first.get("idempotencyKey"));
            check(bearerSeen.get(), "legacy service-role JWT is sent as a bearer token");
            check(outbox.size() == 1, "idempotency key prevents duplicate outbox rows");
            Map<String, Object> stored = outbox.values().iterator().next();
            check("knowledge.graph.upsert.v1".equals(stored.get("event_type")), "canonical event type");
            check(stored.get("payload_sha256").toString().matches("^[a-f0-9]{64}$"), "payload SHA-256 format");
            Map<String, Object> payload = Json.map(stored.get("payload"));
            check(stored.get("payload_sha256").equals(sha256(MnemosKnowledgeAdapter.canonicalJson(payload))),
                    "payload digest matches canonical Mnemos stable JSON");
            check("{\"value\":2}".equals(MnemosKnowledgeAdapter.canonicalJson(Map.of("value", 2.0))),
                    "canonical JSON matches JavaScript integer-valued number encoding");
            check(((List<?>) payload.get("nodes")).size() == 3, "research, evidence, and source nodes are emitted");
            check(((List<?>) payload.get("edges")).size() == 3, "evidence and source provenance edges are emitted");
            Map<String, Object> sourceNode = Json.map(((List<?>) payload.get("nodes")).get(2));
            check("https://example.org/paper".equals(Json.map(sourceNode.get("source")).get("url")),
                    "signed URL query parameters are removed before graph sync");
            Map<String, Object> sourceMetadata = Json.map(sourceNode.get("metadata"));
            check("scientific".equals(sourceMetadata.get("knowledge_layer")), "source nodes enter Scientific Knowledge");
            Map<String, Object> sourceKnowledge = Json.map(sourceMetadata.get("knowledge"));
            check("unknown".equals(sourceKnowledge.get("evidence_status")), "source records do not imply evidence support");
            check(!((List<?>) sourceKnowledge.get("sources")).isEmpty(), "scientific source nodes retain a source reference");
            Map<String, Object> researchNode = Json.map(((List<?>) payload.get("nodes")).get(0));
            check("scientific".equals(Json.map(researchNode.get("metadata")).get("knowledge_layer")),
                    "research runs enter Scientific Knowledge when source evidence exists");

            Map<String, Object> layeredDispatch = fixtureDispatchWithLayers();
            Map<String, Object> layeredResult = adapter.publish(layeredDispatch);
            check("DELIVERED".equals(layeredResult.get("status")), "explicit layered context is enqueued");
            Map<String, Object> layeredRow = outbox.values().stream()
                    .filter(row -> Objects.toString(row.get("idempotency_key"), "").equals(layeredResult.get("idempotencyKey")))
                    .findFirst().orElseThrow();
            Map<String, Object> layeredPayload = Json.map(layeredRow.get("payload"));
            List<?> layeredNodes = (List<?>) layeredPayload.get("nodes");
            List<?> layeredEdges = (List<?>) layeredPayload.get("edges");
            check(layeredNodes.size() == 7, "all five layers are represented by source-backed and explicit context nodes");
            check(layeredEdges.size() == 7, "typed provenance, experiment, and cross-disciplinary relations are emitted");
            Set<String> layerIds = new HashSet<>();
            for (Object value : layeredNodes) {
                Map<String, Object> item = Json.map(value);
                Object layer = Json.map(item.get("metadata")).get("knowledge_layer");
                if (layer != null) layerIds.add(layer.toString());
            }
            check(layerIds.containsAll(Set.of("historical", "philosophical", "scientific", "cross-disciplinary", "experimental")),
                    "the payload covers all five canonical knowledge layers");
            Map<String, Object> historicalNode = layeredNodes.stream().map(Json::map)
                    .filter(node -> "historical_knowledge".equals(node.get("kind"))).findFirst().orElseThrow();
            Map<String, Object> historicalKnowledge = Json.map(Json.map(historicalNode.get("metadata")).get("knowledge"));
            Map<String, Object> historicalSource = Json.map(((List<?>) historicalKnowledge.get("sources")).get(0));
            check("https://example.org/history".equals(historicalSource.get("ref")),
                    "explicit historical source references have query credentials stripped");
            Map<String, Object> experimentNode = layeredNodes.stream().map(Json::map)
                    .filter(node -> "experiment_record".equals(node.get("kind"))).findFirst().orElseThrow();
            check("inconclusive".equals(Json.map(Json.map(experimentNode.get("metadata")).get("knowledge")).get("outcome_status")),
                    "inconclusive experimental outcomes remain explicit");
            Map<String, Object> crossEdge = layeredEdges.stream().map(Json::map)
                    .filter(edge -> "bridges".equals(edge.get("relation"))).findFirst().orElseThrow();
            check("cross-disciplinary".equals(Json.map(crossEdge.get("metadata")).get("knowledge_layer")),
                    "cross-disciplinary links carry their own layer and provenance");

            Map<String, Object> status = adapter.deliveryStatus((String) first.get("idempotencyKey"));
            check("DELIVERED".equals(status.get("status")), "delivery status query reads worker acknowledgement");
            check("abc123knowledgecommit".equals(status.get("deliveryCommit")), "delivery commit is returned");

            Map<String, Object> graph = adapter.readGraph();
            check("mnemos-RLI:Knowledge".equals(graph.get("sourceOfTruth")), "Knowledge branch remains canonical");
            check(((Number) graph.get("nodeCount")).intValue() == 2, "manifest-indexed nodes are loaded");
            check(((Number) graph.get("edgeCount")).intValue() == 1, "manifest-indexed edges are loaded");
            Map<String, Object> search = adapter.searchGraph("battery", 10);
            check(((Number) search.get("matchCount")).intValue() == 1, "graph lexical search returns matching node");
        } finally {
            server.stop(0);
        }
    }

    private static Map<String, Object> fixtureDispatch() {
        Map<String, Object> request = Map.of(
                "id", "b5dca0b2-0db6-4d45-9ed3-9c0a2e86f120",
                "question", "Assess battery energy storage",
                "disciplineHints", List.of("engineering"),
                "createdAt", "2026-11-04T00:00:00Z");
        Map<String, Object> plan = Map.of("steps", List.of(Map.of("engineId", "engineering.material-selection")));
        Map<String, Object> analysis = Map.of(
                "engineId", "research.orchestrator",
                "status", "SCREENING_COMPLETED",
                "startedAt", "2026-11-04T00:00:00Z",
                "output", Map.of("selected", "fixture", "numericResult", 2.0),
                "limitations", List.of("fixture only"),
                "sources", List.of(Map.of("id", "doi:10.0000/example", "title", "Battery paper",
                        "sourceType", "paper", "provider", "Zenodo", "doi", "10.0000/example",
                        "url", "https://example.org/paper?token=should-not-leak#section", "verificationStatus", "NOT_ASSESSED")));
        Map<String, Object> evidence = Map.of(
                "classification", "ENGINEERING_SCREENING",
                "checks", Map.of("experimentalValidation", "NOT_PERFORMED"),
                "limitations", List.of("No experimental validation"));
        return Map.of("request", request, "plan", plan, "analysis", analysis, "evidence", evidence);
    }

    private static Map<String, Object> fixtureDispatchWithLayers() {
        Map<String, Object> base = fixtureDispatch();
        Map<String, Object> request = new LinkedHashMap<>(Json.map(base.get("request")));
        request.put("id", "c7a8d5c1-3a8f-4b11-9d70-8a7f2a0f77b1");
        Map<String, Object> layers = new LinkedHashMap<>();
        layers.put("historical", Map.of("title", "Historical context", "summary", "A sourced historical event.",
                "sources", List.of(Map.of("ref", "https://example.org/history?token=should-not-leak", "title", "Historical source"))));
        layers.put("philosophical", Map.of("questions", List.of("What assumptions define the model?"),
                "assumptions", List.of("The model boundary is an explicit choice.")));
        layers.put("experimental", Map.of("hypothesis", "The candidate improves efficiency.",
                "method", "Compare controlled simulation runs.", "outcomeStatus", "inconclusive",
                "limitations", List.of("Simulation only."), "results", List.of("Simulation did not distinguish candidates.")));
        layers.put("cross-disciplinary", Map.of("disciplines", List.of("physics", "materials"),
                "mappingRationale", "The material property constrains the physical model.",
                "sourceNodeId", "alpha", "targetNodeId", "beta", "relation", "bridges"));
        request.put("context", Map.of("knowledgeLayers", layers));
        return Map.of("request", request, "plan", base.get("plan"),
                "analysis", base.get("analysis"), "evidence", base.get("evidence"));
    }
    private static void handleOutbox(HttpExchange exchange, Map<String, Map<String, Object>> outbox,
                                     AtomicInteger postRequests,
                                     java.util.concurrent.atomic.AtomicBoolean bearerSeen,
                                     java.util.concurrent.atomic.AtomicBoolean apiKeySeen) throws IOException {
        try {
            if (exchange.getRequestHeaders().getFirst("Authorization") != null) bearerSeen.set(true);
            if (exchange.getRequestHeaders().getFirst("apikey") != null) apiKeySeen.set(true);
            if ("POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                postRequests.incrementAndGet();
                Object parsed = Json.parse(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
                Map<String, Object> row = Json.map(((List<?>) parsed).get(0));
                String key = Objects.toString(row.get("idempotency_key"));
                Map<String, Object> stored = new LinkedHashMap<>(row);
                stored.put("id", "outbox-test-id");
                stored.put("created_at", "2026-11-04T00:00:00Z");
                stored.put("delivered_at", "2026-11-04T00:01:00Z");
                stored.put("delivery_commit", "abc123knowledgecommit");
                stored.put("attempts", 1);
                stored.put("last_error", null);
                outbox.putIfAbsent(key, stored);
                exchange.sendResponseHeaders(204, -1);
                return;
            }
            if ("GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                String raw = exchange.getRequestURI().getRawQuery();
                String key = "";
                for (String pair : raw.split("&")) {
                    String[] parts = pair.split("=", 2);
                    if (parts[0].equals("idempotency_key")) key = URLDecoder.decode(parts[1].substring("eq.".length()), StandardCharsets.UTF_8);
                }
                Map<String, Object> row = outbox.get(key);
                respond(exchange, 200, row == null ? List.of() : List.of(row));
                return;
            }
            exchange.sendResponseHeaders(405, -1);
        } catch (Exception error) {
            respond(exchange, 500, Map.of("error", Objects.toString(error.getMessage(), "test server error")));
        } finally {
            exchange.close();
        }
    }

    private static void respond(HttpExchange exchange, int status, Object body) throws IOException {
        byte[] bytes = Json.stringify(body).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }

    private static String sha256(String value) throws Exception {
        byte[] digest = java.security.MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(digest);
    }

    private static void check(boolean condition, String label) {
        checks++;
        if (!condition) throw new AssertionError(label);
    }
}
