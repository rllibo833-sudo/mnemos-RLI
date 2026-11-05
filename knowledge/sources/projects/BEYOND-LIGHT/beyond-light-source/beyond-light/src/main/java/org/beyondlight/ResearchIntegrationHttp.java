package org.beyondlight;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.net.URLDecoder;
import java.util.*;

/** HTTP boundary for the unified research dispatcher. */
public final class ResearchIntegrationHttp {
    private static final int MAX_BODY_BYTES = 1_000_000;
    private static final EngineRegistry REGISTRY = ResearchEngineAdapters.createDefaultRegistry();
    private static final ResearchOrchestrator ORCHESTRATOR =
            new ResearchOrchestrator(new ResearchPlanner(), REGISTRY);
    private static final Path ARCHIVE = DataPaths.path("data", "research_dispatch_runs.jsonl");

    private ResearchIntegrationHttp() {}

    public static void register(HttpServer server) {
        server.createContext("/research/dispatch", ResearchIntegrationHttp::dispatch).getFilters().add(new CorsFilter());
        server.createContext("/research/engines", ResearchIntegrationHttp::engines).getFilters().add(new CorsFilter());
        server.createContext("/knowledge/status", ResearchIntegrationHttp::knowledgeStatus).getFilters().add(new CorsFilter());
        server.createContext("/knowledge/graph", ResearchIntegrationHttp::knowledgeGraph).getFilters().add(new CorsFilter());
    }

    private static final class CorsFilter extends com.sun.net.httpserver.Filter {
        @Override public String description() { return "Allow configured Beyond-Light frontend origins (comma-separated)"; }
        @Override public void doFilter(HttpExchange exchange, Chain chain) throws IOException {
            Set<String> allowed = Arrays.stream(System.getenv().getOrDefault("BEYOND_LIGHT_ALLOWED_ORIGIN", "https://rllibo833-sudo.github.io").split(","))
                    .map(String::trim).filter(value -> !value.isBlank()).collect(java.util.stream.Collectors.toUnmodifiableSet());
            String origin = exchange.getRequestHeaders().getFirst("Origin");
            if (origin != null && allowed.contains(origin)) {
                exchange.getResponseHeaders().set("Access-Control-Allow-Origin", origin);
                exchange.getResponseHeaders().set("Vary", "Origin");
                exchange.getResponseHeaders().set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
                exchange.getResponseHeaders().set("Access-Control-Allow-Headers", "Content-Type");
                exchange.getResponseHeaders().set("Access-Control-Max-Age", "600");
            }
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(204, -1);
                exchange.close();
                return;
            }
            chain.doFilter(exchange);
        }
    }

    private static void engines(HttpExchange exchange) throws IOException {
        try {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                send(exchange, 405, Map.of("error", "GET required"));
                return;
            }
            List<Map<String,Object>> workflows = List.of(
                    workflow("catalog-validation", "science.catalog-validation", "Validate configured scientific catalog metadata and internal consistency.", Map.of()),
                    workflow("symbolic", "mathematics.symbolic", "Symbolic simplify, differentiate, integrate, substitute, evaluate or isolate.", Map.of("operation","simplify|differentiate|integrate|substitute|evaluate|isolate", "expression","string")),
                    workflow("relativity", "physics.special-relativity", "Evaluate the implemented special-relativity model.", Map.of("massKg","number","velocityMs","number","elapsedTimeS","number?","lengthM","number?")),
                    workflow("feasibility", "engineering.feasibility-assessment", "Run the existing propulsion feasibility assessment and evidence classification.", Map.of("propulsionFamily","string","dryMassKg","number","payloadKg","number","deltaVMs","number","ispS","number","thrustN","number","efficiency","number","durationS","number","availablePowerW","number","coolingW","number")),
                    workflow("benchmark", "science.numerical-benchmarks", "Run one configured numerical benchmark or a benchmark group.", Map.of("benchmarkId","string?","benchmarkGroup","string?","tolerance","number?")),
                    workflow("material-selection", "engineering.material-selection", "Screen material records against supplied property thresholds.", Map.of("requirements","object<number>")),
                    workflow("uncertainty", "science.uncertainty-analysis", "Run first-order propagation, sensitivity, Monte Carlo or parameter sweep.", Map.of("mode","propagate|sensitivity|monte-carlo|sweep","expression","string","means","object<number>","sigma","object<number>?")),
                    workflow("technology-domain", "engineering.technology-domain", "Run one registered technology-design domain using its input schema.", Map.of("domainId","string","inputs","object<number>")),
                    workflow("cross-domain-technology", "engineering.cross-domain-technology", "Run sequential energy-storage, thermal and structural screening.", Map.of("inputs","object<number>")),
                    workflow("general-relativity", "physics.metric-geometry", "Analyze Minkowski, Schwarzschild, Alcubierre or Morris-Thorne metric geometry, residuals or energy-condition screens.", Map.of("operation","analyze|diagnose|convergence|stress-energy|field-residual|energy-conditions")),
                    workflow("engineering-calculation", "engineering.calculation", "Run stress, electrical, thermal, buckling, energy-storage, pressure-hoop or thermal-expansion calculations.", Map.of("operation","stress|electrical|thermal|buckling|energy-storage|pressure-hoop|thermal-expansion")),
                    workflow("integrated-technology", "technology.integrated-research", "Run the existing integrated technology research workflow.", Map.of("datasetId","string","target","string","powerVariable","string")),
                    workflow("dataset-analysis", "dataset.deterministic-analysis", "Analyze selected local dataset columns.", Map.of("datasetId","string","x","string","y","string")),
                    workflow("open-data", "research.open-data-cycle", "Search open records, import eligible CSV datasets and perform bounded numeric screening.", Map.of("question","string, 3..160 characters")),
                    workflow("open-data-discovery", "research.open-data-discovery", "Retrieve repository metadata only for disciplines without a specialist engine; no numeric screening.", Map.of("question","string, 3..160 characters"))
            );
            Map<String,Object> response = new LinkedHashMap<>();
            response.put("engines", REGISTRY.ids());
            response.put("workflows", workflows);
            response.put("technologyDomains", TechnologyDesignDomains.catalog());
            response.put("planner", "deterministic-rule-based");
            response.put("llmEnabled", LlmAnswerProvider.fromEnvironment().isPresent());
            response.put("llmConfiguration", "BEYOND_LIGHT_LLM_API_KEY + BEYOND_LIGHT_LLM_MODEL; optional BEYOND_LIGHT_LLM_BASE_URL");
            response.put("sourceFiles", 49);
            response.put("integrationNote", "Utility and model classes are grouped behind domain workflows; not every Java file is an independent engine.");
            send(exchange, 200, response);
        } finally { exchange.close(); }
    }

    private static Map<String,Object> workflow(String workflow, String engineId, String description,
                                                Map<String,Object> contextSchema) {
        Map<String,Object> value = new LinkedHashMap<>();
        value.put("workflow", workflow); value.put("engineId", engineId);
        value.put("description", description); value.put("contextSchema", contextSchema);
        return value;
    }

    private static void dispatch(HttpExchange exchange) throws IOException {
        try {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                send(exchange, 405, Map.of("error", "POST with a JSON ResearchRequest is required"));
                return;
            }
            byte[] body = exchange.getRequestBody().readNBytes(MAX_BODY_BYTES + 1);
            if (body.length > MAX_BODY_BYTES) {
                send(exchange, 413, Map.of("error", "request body exceeds 1 MB"));
                return;
            }
            Object parsed = Json.parse(new String(body, StandardCharsets.UTF_8));
            if (!(parsed instanceof Map<?, ?>)) throw new IllegalArgumentException("JSON body must be an object");
            ResearchRequest request = ResearchRequest.fromMap(Json.map(parsed));
            Optional<MnemosKnowledgeAdapter> knowledge = MnemosKnowledgeAdapter.fromEnvironment();
            Map<String, Object> graphEvidence = Map.of("status", "UNAVAILABLE",
                    "reason", "Mnemos Knowledge integration environment is not configured");
            if (knowledge.isPresent()) {
                try {
                    graphEvidence = knowledge.get().searchGraph(request.question(), 20);
                } catch (Exception graphError) {
                    graphEvidence = Map.of("status", "FAILED",
                            "reason", Objects.toString(graphError.getMessage(), "Knowledge graph retrieval failed"));
                }
            }
            Map<String, Object> enrichedContext = new LinkedHashMap<>(request.context());
            enrichedContext.put("mnemosKnowledgeGraph", graphEvidence);
            request = new ResearchRequest(request.id(), request.question(), enrichedContext,
                    request.disciplineHints(), request.createdAt());
            Map<String, Object> response = ORCHESTRATOR.dispatch(request);
            int graphRecordCount = ((Number) graphEvidence.getOrDefault("recordCount", 0)).intValue();
            String graphRetrievalStatus = graphRecordCount > 0 ? "RETRIEVED"
                    : graphEvidence.containsKey("records") ? "NO_RECORD_MATCH"
                    : Objects.toString(graphEvidence.get("status"), "EMPTY");
            response.put("knowledgeRetrieval", Map.of(
                    "status", graphRetrievalStatus,
                    "sourceOfTruth", Objects.toString(graphEvidence.getOrDefault("sourceOfTruth", "mnemos-RLI:Knowledge")),
                    "recordCount", graphEvidence.getOrDefault("recordCount", 0),
                    "graphNodeCount", graphEvidence.getOrDefault("graphNodeCount", 0),
                    "graphEdgeCount", graphEvidence.getOrDefault("graphEdgeCount", 0)));
            Optional<LlmAnswerProvider> llm = LlmAnswerProvider.fromEnvironment();
            if (llm.isPresent()) {
                try {
                    response.put("answer", llm.get().answer(request.question(), graphEvidence, response));
                } catch (Exception llmError) {
                    response.put("answer", Map.of("status", "FAILED",
                            "error", Objects.toString(llmError.getMessage(), "LLM answer generation failed")));
                }
            } else {
                response.put("answer", Map.of("status", "DISABLED",
                        "reason", "Configure BEYOND_LIGHT_LLM_API_KEY and BEYOND_LIGHT_LLM_MODEL to enable the LLM answer layer."));
            }
            try {
                Optional<MnemosKnowledgeAdapter> knowledgeForSync = knowledge;
                if (knowledgeForSync.isEmpty()) {
                    response.put("knowledgeSync", Map.of("status", "DISABLED",
                            "reason", "Set MNEMOS_SUPABASE_URL, MNEMOS_SUPABASE_SERVICE_ROLE_KEY, and MNEMOS_WORKSPACE_ID on the Java server."));
                } else {
                    response.put("knowledgeSync", knowledgeForSync.get().publish(response));
                }
            } catch (Exception syncError) {
                response.put("knowledgeSync", Map.of("status", "FAILED",
                        "error", Objects.toString(syncError.getMessage(), syncError.getClass().getSimpleName()),
                        "canonicalDestination", "mnemos-RLI:Knowledge"));
            }
            appendArchive(response);
            send(exchange, 200, response);
        } catch (IllegalArgumentException error) {
            send(exchange, 400, Map.of("error", Objects.toString(error.getMessage(), "invalid request")));
        } catch (Exception error) {
            send(exchange, 500, Map.of("error", "research dispatch failed", "detail",
                    Objects.toString(error.getMessage(), error.getClass().getSimpleName())));
        } finally { exchange.close(); }
    }

    private static synchronized void appendArchive(Map<String, Object> response) throws IOException {
        Files.createDirectories(ARCHIVE.getParent());
        Files.writeString(ARCHIVE, Json.stringify(response) + "\n", StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }

    private static void knowledgeStatus(HttpExchange exchange) throws IOException {
        try {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                send(exchange, 405, Map.of("error", "GET required"));
                return;
            }
            Optional<MnemosKnowledgeAdapter> adapter = MnemosKnowledgeAdapter.fromEnvironment();
            if (adapter.isEmpty()) {
                send(exchange, 503, Map.of("status", "DISABLED", "reason", "Mnemos integration environment is not configured"));
                return;
            }
            String key = queryParameter(exchange.getRequestURI().getRawQuery(), "idempotencyKey");
            if (!key.isBlank()) {
                send(exchange, 200, adapter.get().deliveryStatus(key));
                return;
            }
            Map<String, Object> graph = adapter.get().readGraph();
            Map<String, Object> manifest = Json.map(graph.get("manifest"));
            send(exchange, 200, Map.of("status", "GRAPH_READABLE",
                    "outboxConfigured", true,
                    "sourceOfTruth", graph.get("sourceOfTruth"),
                    "nodeCount", graph.get("nodeCount"),
                    "edgeCount", graph.get("edgeCount"),
                    "layers", manifest.getOrDefault("knowledge_layers", List.of()),
                    "transport", "Supabase Outbox; each event reports its own delivery state",
                    "generatedAt", Objects.toString(manifest.get("generated_at"), "")));
        } catch (Exception error) {
            send(exchange, 502, Map.of("status", "UNAVAILABLE",
                    "error", Objects.toString(error.getMessage(), error.getClass().getSimpleName())));
        } finally { exchange.close(); }
    }

    private static void knowledgeGraph(HttpExchange exchange) throws IOException {
        try {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                send(exchange, 405, Map.of("error", "GET required"));
                return;
            }
            Optional<MnemosKnowledgeAdapter> adapter = MnemosKnowledgeAdapter.fromEnvironment();
            if (adapter.isEmpty()) {
                send(exchange, 503, Map.of("error", "Mnemos integration environment is not configured"));
                return;
            }
            String query = queryParameter(exchange.getRequestURI().getRawQuery(), "q");
            String layer = queryParameter(exchange.getRequestURI().getRawQuery(), "layer");
            Set<String> validLayers = Set.of("historical", "philosophical", "scientific", "cross-disciplinary", "experimental");
            if (!layer.isBlank() && !validLayers.contains(layer)) {
                throw new IllegalArgumentException("Unknown Knowledge layer: " + layer);
            }
            Map<String, Object> result = query.isBlank() && layer.isBlank()
                    ? adapter.get().readGraph()
                    : query.isBlank() ? adapter.get().readGraph() : layer.isBlank()
                    ? adapter.get().searchGraph(query, 50) : adapter.get().readGraph();
            if (!layer.isBlank()) {
                List<Map<String, Object>> allNodes = (List<Map<String, Object>>) result.get("nodes");
                List<Map<String, Object>> allEdges = (List<Map<String, Object>>) result.get("edges");
                List<Map<String, Object>> selectedEdges = allEdges.stream().filter(edge -> {
                    Object rawMetadata = edge.get("metadata");
                    Map<String, Object> metadata = rawMetadata instanceof Map<?, ?> ? Json.map(rawMetadata) : Map.of();
                    return layer.equals(Objects.toString(metadata.get("knowledge_layer"), ""));
                }).toList();
                Set<String> selectedIds = new LinkedHashSet<>();
                for (Map<String, Object> node : allNodes) {
                    Object rawMetadata = node.get("metadata");
                    Map<String, Object> metadata = rawMetadata instanceof Map<?, ?> ? Json.map(rawMetadata) : Map.of();
                    if (layer.equals(Objects.toString(metadata.get("knowledge_layer"), ""))) {
                        selectedIds.add(Objects.toString(node.get("id"), ""));
                    }
                }
                for (Map<String, Object> edge : selectedEdges) {
                    selectedIds.add(Objects.toString(edge.get("source"), ""));
                    selectedIds.add(Objects.toString(edge.get("target"), ""));
                }
                List<Map<String, Object>> selectedNodes = allNodes.stream()
                        .filter(node -> selectedIds.contains(Objects.toString(node.get("id"), ""))).toList();
                result.put("nodes", selectedNodes);
                result.put("edges", selectedEdges);
                result.put("nodeCount", selectedNodes.size());
                result.put("edgeCount", selectedEdges.size());
                result.put("layer", layer);
            }
            if (!query.isBlank() && !layer.isBlank()) {
                String term = query.toLowerCase(Locale.ROOT);
                List<Map<String, Object>> nodes = (List<Map<String, Object>>) result.get("nodes");
                List<Map<String, Object>> matches = nodes.stream().filter(node ->
                        (Objects.toString(node.get("id"), "") + " " + Objects.toString(node.get("title"), "")
                                + " " + Objects.toString(node.get("content"), "")
                                + " " + Json.stringify(node.getOrDefault("metadata", Map.of())))
                                .toLowerCase(Locale.ROOT).contains(term)).limit(50).toList();
                Set<String> matchIds = new HashSet<>();
                matches.forEach(node -> matchIds.add(Objects.toString(node.get("id"), "")));
                List<Map<String, Object>> edges = (List<Map<String, Object>>) result.get("edges");
                List<Map<String, Object>> matchingEdges = edges.stream().filter(edge ->
                        matchIds.contains(Objects.toString(edge.get("source"), ""))
                                && matchIds.contains(Objects.toString(edge.get("target"), ""))).toList();
                result.put("nodes", matches);
                result.put("edges", matchingEdges);
                result.put("nodeCount", matches.size());
                result.put("edgeCount", matchingEdges.size());
                result.put("query", query);
            }
            send(exchange, 200, result);
        } catch (IllegalArgumentException error) {
            send(exchange, 400, Map.of("error", Objects.toString(error.getMessage(), "invalid graph query")));
        } catch (Exception error) {
            send(exchange, 502, Map.of("error", "Knowledge graph read failed",
                    "detail", Objects.toString(error.getMessage(), error.getClass().getSimpleName())));
        } finally { exchange.close(); }
    }

    private static String queryParameter(String rawQuery, String name) {
        if (rawQuery == null || rawQuery.isBlank()) return "";
        for (String pair : rawQuery.split("&")) {
            String[] parts = pair.split("=", 2);
            String key = URLDecoder.decode(parts[0], StandardCharsets.UTF_8);
            if (name.equals(key)) return parts.length > 1
                    ? URLDecoder.decode(parts[1], StandardCharsets.UTF_8) : "";
        }
        return "";
    }

    private static void send(HttpExchange exchange, int status, Map<String, Object> payload) throws IOException {
        byte[] bytes = Json.stringify(payload).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
}
