package org.beyondlight;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.*;

/**
 * Publishes bounded research provenance to Mnemos' temporary Supabase outbox
 * and reads the canonical, versioned graph from mnemos-RLI:Knowledge.
 *
 * Supabase is transport only. The Knowledge branch remains the source of truth.
 */
public final class MnemosKnowledgeAdapter {
    private static final String EVENT_TYPE = "knowledge.graph.upsert.v1";
    private static final int MAX_INLINE_TEXT = 65_536;
    private static final int MAX_GRAPH_FILES = 2_000;
    private final HttpClient http;
    private final URI supabaseBase;
    private final URI knowledgeBase;
    private final String serviceRoleKey;
    private final String workspaceId;

    MnemosKnowledgeAdapter(HttpClient http, URI supabaseBase, String serviceRoleKey,
                           String workspaceId, URI knowledgeBase) {
        this.http = Objects.requireNonNull(http);
        this.supabaseBase = trimSlash(Objects.requireNonNull(supabaseBase));
        this.knowledgeBase = ensureSlash(Objects.requireNonNull(knowledgeBase));
        this.serviceRoleKey = requireText(serviceRoleKey, "Supabase service role key");
        this.workspaceId = requireUuid(workspaceId);
    }

    public static Optional<MnemosKnowledgeAdapter> fromEnvironment() {
        String url = firstEnv("MNEMOS_SUPABASE_URL", "SUPABASE_URL");
        String key = firstEnv("MNEMOS_SUPABASE_SECRET_KEY", "MNEMOS_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY");
        String workspace = firstEnv("MNEMOS_WORKSPACE_ID");
        if (url.isBlank() || key.isBlank() || workspace.isBlank()) return Optional.empty();
        try {
            URI base = URI.create(url);
            URI knowledge = URI.create(firstEnvOr("MNEMOS_KNOWLEDGE_BASE_URL",
                    "https://raw.githubusercontent.com/rllibo833-sudo/mnemos-RLI/Knowledge/knowledge/"));
            return Optional.of(new MnemosKnowledgeAdapter(
                    HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build(),
                    base, key, workspace, knowledge));
        } catch (RuntimeException error) {
            throw new IllegalStateException("Invalid Mnemos integration environment configuration", error);
        }
    }

    public Map<String, Object> publish(Map<String, Object> dispatchResponse) throws Exception {
        Map<String, Object> request = object(dispatchResponse.get("request"), "request");
        Map<String, Object> analysis = object(dispatchResponse.get("analysis"), "analysis");
        Map<String, Object> evidence = object(dispatchResponse.get("evidence"), "evidence");
        Map<String, Object> plan = objectOrEmpty(dispatchResponse.get("plan"));
        String requestId = requireText(Objects.toString(request.get("id"), ""), "research request id");
        if (requestId.length() > 128) throw new IllegalArgumentException("research request id exceeds 128 characters");
        Map<String, Object> payload = graphPayload(request, plan, analysis, evidence);
        String payloadHash = sha256(canonicalJson(payload));
        String idempotencyKey = "beyond-light:research:" + requestId + ":" + payloadHash;

        Map<String, Object> row = new LinkedHashMap<>();
        row.put("workspace_id", workspaceId);
        row.put("event_type", EVENT_TYPE);
        row.put("idempotency_key", idempotencyKey);
        row.put("payload", payload);
        row.put("payload_sha256", payloadHash);

        URI endpoint = supabaseBase.resolve("/rest/v1/mnemos_outbox?on_conflict=workspace_id%2Cidempotency_key");
        HttpRequest.Builder postBuilder = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(20))
                .header("apikey", serviceRoleKey)
                .header("Accept", "application/json")
                .header("Content-Type", "application/json")
                .header("Prefer", "resolution=ignore-duplicates,return=minimal")
                .POST(HttpRequest.BodyPublishers.ofString(Json.stringify(List.of(row))));
        if (!serviceRoleKey.startsWith("sb_secret_")) postBuilder.header("Authorization", "Bearer " + serviceRoleKey);
        HttpResponse<String> response = http.send(postBuilder.build(), HttpResponse.BodyHandlers.ofString());
        requireSuccess(response, "enqueue Mnemos outbox event");

        Map<String, Object> status = deliveryStatus(idempotencyKey);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", status.get("status"));
        result.put("eventType", EVENT_TYPE);
        result.put("idempotencyKey", idempotencyKey);
        result.put("payloadSha256", payloadHash);
        result.put("workspaceId", workspaceId);
        result.put("nodeCount", ((List<?>) payload.get("nodes")).size());
        result.put("edgeCount", ((List<?>) payload.get("edges")).size());
        result.put("outbox", status);
        result.put("canonicalDestination", "mnemos-RLI:Knowledge");
        return result;
    }

    public Map<String, Object> deliveryStatus(String idempotencyKey) throws Exception {
        String query = "select=id,workspace_id,event_type,idempotency_key,payload_sha256,created_at,delivered_at,delivery_commit,attempts,last_error"
                + "&workspace_id=eq." + encode(workspaceId)
                + "&idempotency_key=eq." + encode(requireText(idempotencyKey, "idempotency key"))
                + "&limit=1";
        HttpRequest.Builder getBuilder = HttpRequest.newBuilder(supabaseBase.resolve("/rest/v1/mnemos_outbox?" + query))
                .timeout(Duration.ofSeconds(15))
                .header("apikey", serviceRoleKey)
                .header("Accept", "application/json")
                .GET();
        if (!serviceRoleKey.startsWith("sb_secret_")) getBuilder.header("Authorization", "Bearer " + serviceRoleKey);
        HttpRequest get = getBuilder.build();
        HttpResponse<String> response = http.send(get, HttpResponse.BodyHandlers.ofString());
        requireSuccess(response, "read Mnemos outbox status");
        Object parsed = Json.parse(response.body());
        if (!(parsed instanceof List<?> rows) || rows.isEmpty()) {
            throw new IllegalStateException("Mnemos outbox event was not found after enqueue");
        }
        Map<String, Object> row = Json.map(rows.get(0));
        boolean hasTimestamp = row.get("delivered_at") != null && !row.get("delivered_at").toString().isBlank();
        boolean hasCommit = row.get("delivery_commit") != null && !row.get("delivery_commit").toString().isBlank();
        String deliveryState = hasTimestamp && hasCommit ? "DELIVERED"
                : hasTimestamp || hasCommit ? "ACK_INCOMPLETE" : "QUEUED";
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", deliveryState);
        result.put("outboxId", row.get("id"));
        result.put("deliveredAt", row.get("delivered_at"));
        result.put("deliveryCommit", row.get("delivery_commit"));
        result.put("attempts", row.get("attempts"));
        result.put("lastError", row.get("last_error"));
        return result;
    }

    /** Reads and validates the complete manifest-indexed Knowledge graph snapshot. */
    public Map<String, Object> readGraph() throws Exception {
        Map<String, Object> manifest = Json.map(getJson(knowledgeBase.resolve("manifest.json")));
        List<String> nodeFiles = strings(manifest.get("node_files"), "manifest.node_files");
        List<String> edgeFiles = strings(manifest.get("edge_files"), "manifest.edge_files");
        if (nodeFiles.size() + edgeFiles.size() > MAX_GRAPH_FILES) {
            throw new IllegalStateException("Knowledge manifest exceeds the configured file safety limit");
        }

        List<Map<String, Object>> nodes = new ArrayList<>();
        for (String file : nodeFiles) {
            if (!safeFilename(file)) throw new IllegalStateException("Unsafe Knowledge node filename in manifest");
            Object parsed = getJson(knowledgeBase.resolve("nodes/" + encodePath(file)));
            if (!(parsed instanceof Map<?, ?>)) throw new IllegalStateException("Knowledge node must be a JSON object");
            nodes.add(Json.map(parsed));
        }

        List<Map<String, Object>> edges = new ArrayList<>();
        for (String file : edgeFiles) {
            if (!safeFilename(file)) throw new IllegalStateException("Unsafe Knowledge edge filename in manifest");
            Object parsed = getJson(knowledgeBase.resolve("edges/" + encodePath(file)));
            if (!(parsed instanceof List<?> list)) throw new IllegalStateException("Knowledge edge file must be a JSON array");
            for (Object edge : list) edges.add(Json.map(edge));
        }

        Set<String> ids = new HashSet<>();
        for (Map<String, Object> node : nodes) {
            String id = Objects.toString(node.get("id"), "");
            if (id.isBlank() || !ids.add(id)) throw new IllegalStateException("Knowledge graph contains a missing or duplicate node id");
        }
        for (Map<String, Object> edge : edges) {
            String source = Objects.toString(edge.getOrDefault("source", edge.get("source_id")), "");
            String target = Objects.toString(edge.getOrDefault("target", edge.get("target_id")), "");
            if (!ids.contains(source) || !ids.contains(target)) {
                throw new IllegalStateException("Knowledge graph contains a dangling edge: " + source + " -> " + target);
            }
        }

        Map<String, Object> graph = new LinkedHashMap<>();
        graph.put("sourceOfTruth", Objects.toString(manifest.get("source_of_truth"), "mnemos-RLI:Knowledge"));
        graph.put("manifest", manifest);
        graph.put("nodes", nodes);
        graph.put("edges", edges);
        graph.put("nodeCount", nodes.size());
        graph.put("edgeCount", edges.size());
        return graph;
    }

    /** Searches graph indexes and expands matching collections into their archived source records. */
    public Map<String, Object> searchGraph(String query, int limit) throws Exception {
        String cleanQuery = requireText(query, "graph search query");
        if (cleanQuery.length() < 2 || cleanQuery.length() > 2000) throw new IllegalArgumentException("graph search query must contain 2..2000 characters");
        List<String> terms = Arrays.stream(cleanQuery.toLowerCase(Locale.ROOT)
                        .replaceAll("[^\\p{L}\\p{N}_-]+", " ").trim().split("\\s+"))
                .filter(token -> token.length() >= 3)
                .filter(token -> !Set.of("the", "and", "for", "with", "that", "this", "from", "what", "which",
                        "where", "when", "how", "can", "could", "does", "have", "into", "about", "yang", "dan",
                        "atau", "untuk", "dari", "dengan", "apakah", "bisakah", "bagaimana", "pada", "dalam").contains(token))
                .distinct().limit(12).toList();
        if (terms.isEmpty()) throw new IllegalArgumentException("graph search query must contain a searchable term");
        int boundedLimit = Math.max(1, Math.min(limit, 100));
        Map<String, Object> graph = readGraph();
        List<Map<String, Object>> all = (List<Map<String, Object>>) graph.get("nodes");
        List<Map<String, Object>> matches = new ArrayList<>();
        for (Map<String, Object> node : all) {
            String haystack = (Objects.toString(node.get("id"), "") + " "
                    + Objects.toString(node.get("kind"), "") + " "
                    + Objects.toString(node.get("title"), "") + " "
                    + Objects.toString(node.get("content"), "") + " "
                    + Json.stringify(node.getOrDefault("source", Map.of())) + " "
                    + Json.stringify(node.getOrDefault("metadata", Map.of()))).toLowerCase(Locale.ROOT);
            if (matchesAny(haystack, terms)) matches.add(node);
        }

        // Collection nodes are only indexes. Read their verbatim archive files so retrieval
        // returns evidence records, not merely a title saying that a collection exists.
        List<Map<String, Object>> records = new ArrayList<>();
        Set<String> scanned = new LinkedHashSet<>();
        for (Map<String, Object> node : matches) {
            Map<String, Object> metadata = objectOrEmpty(node.get("metadata"));
            Map<String, Object> knowledge = objectOrEmpty(metadata.get("knowledge"));
            Object refs = knowledge.get("raw_data_refs");
            if (!(refs instanceof List<?> list)) continue;
            for (Object rawRef : list) {
                String path = Objects.toString(rawRef, "").trim();
                if (!path.startsWith("knowledge/sources/beyond-light/") || path.contains("..") || !scanned.add(path)) continue;
                String filename = path.substring(path.lastIndexOf('/') + 1);
                if (!safeFilename(filename)) continue;
                String raw = getText(knowledgeBase.resolve(path.substring("knowledge/".length()).replace(" ", "%20")));
                String lower = raw.toLowerCase(Locale.ROOT);
                if (!matchesAny(lower, terms)) continue;
                if (filename.endsWith(".jsonl")) {
                    for (String line : raw.split("\\R")) {
                        if (line.isBlank() || !matchesAny(line.toLowerCase(Locale.ROOT), terms)) continue;
                        Object parsed = Json.parse(line);
                        if (parsed instanceof Map<?, ?>) {
                            Map<String, Object> record = new LinkedHashMap<>(Json.map(parsed));
                            record.putIfAbsent("_knowledgeCollection", Objects.toString(node.get("title"), ""));
                            record.putIfAbsent("_archivePath", path);
                            records.add(record);
                            if (records.size() >= boundedLimit) break;
                        }
                    }
                } else if (filename.endsWith(".json")) {
                    Object parsed = Json.parse(raw);
                    if (parsed instanceof Map<?, ?> map) {
                        Map<String, Object> record = new LinkedHashMap<>(Json.map(map));
                        record.put("_archivePath", path);
                        records.add(record);
                    } else if (parsed instanceof List<?> listRecords) {
                        for (Object item : listRecords) {
                            if (matchesAny(Json.stringify(item).toLowerCase(Locale.ROOT), terms) && item instanceof Map<?, ?>) {
                                Map<String, Object> record = new LinkedHashMap<>(Json.map(item));
                                record.put("_archivePath", path);
                                records.add(record);
                                if (records.size() >= boundedLimit) break;
                            }
                        }
                    }
                } else if (filename.endsWith(".csv")) {
                    for (String line : raw.split("\\R")) {
                        if (matchesAny(line.toLowerCase(Locale.ROOT), terms)) {
                            records.add(Map.of("recordType", "csv_row", "text", line, "_archivePath", path));
                            if (records.size() >= boundedLimit) break;
                        }
                    }
                }
                if (records.size() >= boundedLimit) break;
            }
            if (records.size() >= boundedLimit) break;
        }

        Set<String> matchedIds = new LinkedHashSet<>();
        matches.forEach(node -> matchedIds.add(Objects.toString(node.get("id"), "")));
        List<Map<String, Object>> relationships = new ArrayList<>();
        for (Map<String, Object> edge : (List<Map<String, Object>>) graph.get("edges")) {
            String source = Objects.toString(edge.getOrDefault("source", edge.get("source_id")), "");
            String target = Objects.toString(edge.getOrDefault("target", edge.get("target_id")), "");
            if (matchedIds.contains(source) || matchedIds.contains(target)) relationships.add(edge);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("sourceOfTruth", graph.get("sourceOfTruth"));
        result.put("query", cleanQuery);
        result.put("queryTerms", terms);
        result.put("matches", matches.stream().limit(boundedLimit).toList());
        result.put("records", records);
        result.put("relationships", relationships);
        result.put("matchCount", matches.size());
        result.put("recordCount", records.size());
        result.put("graphNodeCount", graph.get("nodeCount"));
        result.put("graphEdgeCount", graph.get("edgeCount"));
        return result;
    }

    private Map<String, Object> graphPayload(Map<String, Object> request,
                                             Map<String, Object> plan,
                                             Map<String, Object> analysis,
                                             Map<String, Object> evidence) {
        String requestId = Objects.toString(request.get("id"), "");
        String question = Objects.toString(request.get("question"), "Research result");
        String now = Objects.toString(request.getOrDefault("createdAt", analysis.getOrDefault("startedAt", Instant.EPOCH.toString())), Instant.EPOCH.toString());
        String workflow = workflow(plan, analysis);
        Map<String, Object> context = objectOrEmpty(request.get("context"));
        Map<String, Object> layerInputs = objectOrEmpty(context.get("knowledgeLayers"));
        List<Map<String, Object>> sourceRefs = knowledgeSourceRefs(analysis.get("sources"));
        String evidenceStatus = evidenceStatus(objectOrEmpty(layerInputs.get("scientific")).get("evidenceStatus"));
        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> edges = new ArrayList<>();

        String researchId = "bl-research-" + requestId;
        Map<String, Object> analysisOutput = objectOrEmpty(analysis.get("output"));
        String analysisStatus = Objects.toString(analysis.get("status"), "UNKNOWN");
        String classification = Objects.toString(evidence.get("classification"), "UNCLASSIFIED");
        String content = "Question: " + question + "\nAnalysis status: " + analysisStatus
                + "\nEvidence classification: " + classification
                + "\nWorkflow: " + workflow
                + "\nAnalysis output: " + Json.stringify(analysisOutput);
        if (content.length() > MAX_INLINE_TEXT) content = content.substring(0, MAX_INLINE_TEXT);
        Map<String, Object> researchMetadata = new LinkedHashMap<>();
        researchMetadata.put("analysis_status", analysisStatus);
        researchMetadata.put("evidence_classification", classification);
        researchMetadata.put("discipline_hints", request.getOrDefault("disciplineHints", List.of()));
        researchMetadata.put("source_count", sourceRefs.size());
        researchMetadata.put("limitations", analysis.getOrDefault("limitations", List.of()));
        researchMetadata.put("created_at", now);
        if (!sourceRefs.isEmpty()) applyScientificLayer(researchMetadata, "research_run", evidenceStatus, sourceRefs);
        Map<String, Object> researchNode = node(researchId, "research_run", question, content,
                Map.of("type", "beyond-light-research", "request_id", requestId, "workflow", workflow),
                researchMetadata, now);
        nodes.add(researchNode);

        Map<String, Object> evidenceChecks = objectOrEmpty(evidence.get("checks"));
        String evidenceId = "bl-evidence-" + requestId;
        String evidenceContent = "Classification: " + classification + "\n"
                + "Experimental validation: " + Objects.toString(evidenceChecks.get("experimentalValidation"), "NOT_REPORTED")
                + "\n" + "Evidence report: " + Json.stringify(evidence);
        if (evidenceContent.length() > MAX_INLINE_TEXT) evidenceContent = evidenceContent.substring(0, MAX_INLINE_TEXT);
        Map<String, Object> evidenceMetadata = new LinkedHashMap<>();
        evidenceMetadata.put("classification", classification);
        evidenceMetadata.put("checks", evidenceChecks);
        evidenceMetadata.put("limitations", evidence.getOrDefault("limitations", List.of()));
        evidenceMetadata.put("created_at", now);
        if (!sourceRefs.isEmpty()) applyScientificLayer(evidenceMetadata, "evidence_assessment", evidenceStatus, sourceRefs);
        nodes.add(node(evidenceId, "evidence_report", "Evidence report — " + question, evidenceContent,
                Map.of("type", "beyond-light-evidence", "request_id", requestId),
                evidenceMetadata, now));
        if (!sourceRefs.isEmpty()) edges.add(typedEdge(evidenceId, researchId, "derived_from", "scientific", requestId, now));
        else edges.add(edge(researchId, evidenceId, "HAS_EVIDENCE", requestId, now));

        Object rawSources = analysis.get("sources");
        if (rawSources instanceof List<?> sources) {
            for (Object rawSource : sources) {
                Map<String, Object> source = Json.map(rawSource);
                String sourceKey = Objects.toString(source.get("id"), "");
                if (sourceKey.isBlank()) continue;
                String sourceId = "bl-source-" + sha256(sourceKey).substring(0, 32);
                String title = Objects.toString(source.getOrDefault("title", sourceKey), sourceKey);
                String sourceUrl = safeSourceUrl(Objects.toString(source.get("url"), ""));
                String sourceContent = "Provider: " + Objects.toString(source.get("provider"), "unspecified")
                        + "\nType: " + Objects.toString(source.get("sourceType"), "unspecified")
                        + "\nDOI: " + Objects.toString(source.get("doi"), "")
                        + "\nURL: " + sourceUrl;
                Map<String, Object> sourceRef = new LinkedHashMap<>();
                sourceRef.put("type", "beyond-light-source");
                sourceRef.put("source_id", sourceKey);
                sourceRef.put("provider", Objects.toString(source.get("provider"), ""));
                sourceRef.put("url", sourceUrl);
                Map<String, Object> sourceMetadata = new LinkedHashMap<>();
                sourceMetadata.put("source_type", Objects.toString(source.get("sourceType"), "unspecified"));
                sourceMetadata.put("provider", Objects.toString(source.get("provider"), ""));
                sourceMetadata.put("author", Objects.toString(source.get("author"), ""));
                sourceMetadata.put("publication_date", Objects.toString(source.get("publicationDate"), ""));
                sourceMetadata.put("doi", Objects.toString(source.get("doi"), ""));
                sourceMetadata.put("license", Objects.toString(source.get("license"), ""));
                sourceMetadata.put("verification_status", Objects.toString(source.get("verificationStatus"), "NOT_ASSESSED"));
                List<Map<String, Object>> selfReference = List.of(sourceReference(source, sourceKey, title, sourceUrl));
                applyScientificLayer(sourceMetadata, "source_record", "unknown", selfReference);
                nodes.add(node(sourceId, "research_source", title, sourceContent, sourceRef, sourceMetadata, now));
                edges.add(typedEdge(researchId, sourceId, "derived_from", "scientific", requestId, now));
                edges.add(typedEdge(evidenceId, sourceId, "derived_from", "scientific", requestId, now));
            }
        }
        appendExplicitLayerNodes(nodes, edges, request, layerInputs, researchId, now, sourceRefs);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("nodes", nodes);
        payload.put("edges", edges);
        return payload;
    }


    private static List<Map<String, Object>> knowledgeSourceRefs(Object rawSources) {
        List<Map<String, Object>> refs = new ArrayList<>();
        if (!(rawSources instanceof List<?> sources)) return refs;
        for (Object raw : sources) {
            if (!(raw instanceof Map<?, ?>)) continue;
            Map<String, Object> source = Json.map(raw);
            String id = Objects.toString(source.get("id"), "").trim();
            String url = safeSourceUrl(Objects.toString(source.get("url"), ""));
            String title = Objects.toString(source.get("title"), id).trim();
            String ref = !url.isBlank() ? url : id;
            if (ref.isBlank() && title.isBlank()) continue;
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("type", Objects.toString(source.get("sourceType"), "research_source"));
            if (!ref.isBlank()) item.put("ref", ref);
            if (!title.isBlank()) item.put("title", title);
            putIfText(item, "publisher", source.get("provider"));
            putIfText(item, "published_at", source.get("publicationDate"));
            refs.add(item);
        }
        return List.copyOf(refs);
    }

    private static Map<String, Object> sourceReference(Map<String, Object> source, String sourceKey,
                                                         String title, String sourceUrl) {
        Map<String, Object> ref = new LinkedHashMap<>();
        ref.put("type", Objects.toString(source.get("sourceType"), "research_source"));
        ref.put("ref", sourceUrl.isBlank() ? sourceKey : sourceUrl);
        ref.put("title", title);
        putIfText(ref, "publisher", source.get("provider"));
        putIfText(ref, "published_at", source.get("publicationDate"));
        return ref;
    }

    private static void applyScientificLayer(Map<String, Object> metadata, String claimType,
                                             String evidenceStatus, List<Map<String, Object>> sources) {
        metadata.put("knowledge_layer", "scientific");
        Map<String, Object> knowledge = new LinkedHashMap<>();
        knowledge.put("claim_type", claimType);
        knowledge.put("evidence_status", evidenceStatus);
        knowledge.put("sources", sources);
        metadata.put("knowledge", knowledge);
    }

    private static String evidenceStatus(Object value) {
        String status = Objects.toString(value, "unknown").trim().toLowerCase(Locale.ROOT);
        return Set.of("proposed", "theoretical", "supported", "contested", "refuted", "unknown").contains(status)
                ? status : "unknown";
    }

    private static void putIfText(Map<String, Object> target, String key, Object value) {
        String text = Objects.toString(value, "").trim();
        if (!text.isBlank()) target.put(key, text.length() > 1000 ? text.substring(0, 1000) : text);
    }

    private static List<String> contextStrings(Object value) {
        if (!(value instanceof List<?> list)) return List.of();
        LinkedHashSet<String> unique = new LinkedHashSet<>();
        for (Object item : list) {
            String text = Objects.toString(item, "").trim();
            if (!text.isBlank() && text.length() <= 2000) unique.add(text);
            if (unique.size() >= 50) break;
        }
        return List.copyOf(unique);
    }

    private static Map<String, Object> explicitSources(Map<String, Object> input, List<Map<String, Object>> fallback) {
        Object raw = input.get("sources");
        if (!(raw instanceof List<?> list) || list.isEmpty()) return new LinkedHashMap<>(Map.of("sources", fallback));
        List<Map<String, Object>> sources = new ArrayList<>();
        for (Object value : list) {
            if (!(value instanceof Map<?, ?>)) continue;
            Map<String, Object> rawSource = Json.map(value);
            Map<String, Object> ref = new LinkedHashMap<>();
            putIfText(ref, "type", rawSource.get("type"));
            String rawReference = Objects.toString(rawSource.get("ref"), "").trim();
            String safeReference = safeSourceUrl(rawReference);
            putIfText(ref, "ref", safeReference.isBlank() ? rawReference : safeReference);
            putIfText(ref, "title", rawSource.get("title"));
            putIfText(ref, "publisher", rawSource.get("publisher"));
            putIfText(ref, "published_at", rawSource.get("published_at"));
            putIfText(ref, "accessed_at", rawSource.get("accessed_at"));
            if (ref.containsKey("ref") || ref.containsKey("title")) sources.add(ref);
        }
        return new LinkedHashMap<>(Map.of("sources", sources.isEmpty() ? fallback : List.copyOf(sources)));
    }

    private void appendExplicitLayerNodes(List<Map<String, Object>> nodes, List<Map<String, Object>> edges,
                                                 Map<String, Object> request, Map<String, Object> layerInputs,
                                                 String researchId, String now, List<Map<String, Object>> sourceRefs) {
        String requestId = Objects.toString(request.get("id"), "");
        String question = Objects.toString(request.get("question"), "Research context");

        Map<String, Object> historical = objectOrEmpty(layerInputs.get("historical"));
        if (!historical.isEmpty()) {
            Map<String, Object> knowledge = explicitSources(historical, sourceRefs);
            putIfText(knowledge, "date", historical.get("date"));
            putIfText(knowledge, "time_period", historical.get("timePeriod"));
            putIfText(knowledge, "event_type", historical.get("eventType"));
            knowledge.put("people", contextStrings(historical.get("people")));
            knowledge.put("institutions", contextStrings(historical.get("institutions")));
            putIfText(knowledge, "historical_context", historical.get("historicalContext"));
            if (((List<?>) knowledge.get("sources")).isEmpty()) throw new IllegalArgumentException("historical knowledge requires source references");
            addContextNode(nodes, "historical", requestId, "historical_knowledge",
                    Objects.toString(historical.getOrDefault("title", "Historical context — " + question)),
                    Objects.toString(historical.getOrDefault("content", historical.getOrDefault("summary", ""))),
                    knowledge, now);
        }

        Map<String, Object> philosophical = objectOrEmpty(layerInputs.get("philosophical"));
        if (!philosophical.isEmpty()) {
            Map<String, Object> knowledge = new LinkedHashMap<>();
            knowledge.put("questions", contextStrings(philosophical.get("questions")));
            knowledge.put("assumptions", contextStrings(philosophical.get("assumptions")));
            knowledge.put("principles", contextStrings(philosophical.get("principles")));
            knowledge.put("arguments", contextStrings(philosophical.get("arguments")));
            knowledge.put("ethical_considerations", contextStrings(philosophical.get("ethicalConsiderations")));
            knowledge.put("consequences", contextStrings(philosophical.get("consequences")));
            knowledge.put("counterarguments", contextStrings(philosophical.get("counterarguments")));
            addContextNode(nodes, "philosophical", requestId, "philosophical_analysis",
                    Objects.toString(philosophical.getOrDefault("title", "Philosophical analysis — " + question)),
                    Objects.toString(philosophical.getOrDefault("content", philosophical.getOrDefault("summary", ""))),
                    knowledge, now);
        }

        Map<String, Object> experimental = objectOrEmpty(layerInputs.get("experimental"));
        if (!experimental.isEmpty()) {
            Map<String, Object> knowledge = new LinkedHashMap<>();
            putIfText(knowledge, "hypothesis", experimental.get("hypothesis"));
            putIfText(knowledge, "method", experimental.get("method"));
            putIfText(knowledge, "protocol", experimental.get("protocol"));
            putIfText(knowledge, "outcome_status", experimental.get("outcomeStatus"));
            knowledge.put("conditions", contextStrings(experimental.get("conditions")));
            knowledge.put("variables", contextStrings(experimental.get("variables")));
            knowledge.put("results", contextStrings(experimental.get("results")));
            knowledge.put("raw_data_refs", contextStrings(experimental.get("rawDataRefs")));
            putIfText(knowledge, "replication_of", experimental.get("replicationOf"));
            knowledge.put("failure_modes", contextStrings(experimental.get("failureModes")));
            knowledge.put("limitations", contextStrings(experimental.get("limitations")));
            knowledge.put("sources", explicitSources(experimental, sourceRefs).get("sources"));
            addContextNode(nodes, "experimental", requestId, "experiment_record",
                    Objects.toString(experimental.getOrDefault("title", "Experiment — " + question)),
                    Objects.toString(experimental.getOrDefault("content", experimental.getOrDefault("summary", ""))),
                    knowledge, now);
            String experimentId = "bl-experimental-" + sha256(requestId).substring(0, 32);
            edges.add(typedEdge(researchId, experimentId, "tests", "experimental", requestId, now));
        }

        Map<String, Object> cross = objectOrEmpty(layerInputs.get("cross-disciplinary"));
        if (!cross.isEmpty()) {
            List<String> disciplines = contextStrings(cross.get("disciplines"));
            String rationale = Objects.toString(cross.get("mappingRationale"), "").trim();
            String sourceId = Objects.toString(cross.get("sourceNodeId"), "").trim();
            String targetId = Objects.toString(cross.get("targetNodeId"), "").trim();
            if (disciplines.stream().map(value -> value.toLowerCase(Locale.ROOT)).distinct().count() < 2
                    || rationale.isBlank() || sourceId.isBlank() || targetId.isBlank() || sourceId.equals(targetId)) {
                throw new IllegalArgumentException("cross-disciplinary context requires two disciplines, mappingRationale, sourceNodeId, and targetNodeId");
            }
            Map<String, Object> knowledge = new LinkedHashMap<>();
            knowledge.put("disciplines", disciplines);
            knowledge.put("mapping_rationale", rationale);
            putIfText(knowledge, "shared_concept", cross.get("sharedConcept"));
            knowledge.put("transfer_limits", contextStrings(cross.get("transferLimits")));
            Map<String, Object> sourceKnowledge = explicitSources(cross, sourceRefs);
            knowledge.put("sources", sourceKnowledge.get("sources"));
            String bridgeId = "bl-crossdisciplinary-" + sha256(requestId).substring(0, 32);
            addContextNodeWithId(nodes, bridgeId, "cross-disciplinary", "cross_disciplinary_relation",
                    Objects.toString(cross.getOrDefault("title", "Cross-disciplinary relation — " + question)),
                    Objects.toString(cross.getOrDefault("content", rationale)), knowledge, now);
            String relation = Objects.toString(cross.get("relation"), "bridges");
            if (!Set.of("bridges", "maps_to", "analogous_to", "applies_to", "shares_structure_with", "transfers_method_to").contains(relation)) {
                throw new IllegalArgumentException("cross-disciplinary relation is not in the canonical layer vocabulary");
            }
            edges.add(typedEdge(sourceId, targetId, relation, "cross-disciplinary", requestId, now));
            edges.add(typedEdge(bridgeId, sourceId, "maps_to", "cross-disciplinary", requestId, now));
            edges.add(typedEdge(bridgeId, targetId, "maps_to", "cross-disciplinary", requestId, now));
        }
    }

    private void addContextNode(List<Map<String, Object>> nodes, String layer, String requestId,
                                       String kind, String title, String content,
                                       Map<String, Object> knowledge, String now) {
        String id = "bl-" + layer + "-" + sha256(requestId).substring(0, 32);
        addContextNodeWithId(nodes, id, layer, kind, title, content, knowledge, now);
    }

    private void addContextNodeWithId(List<Map<String, Object>> nodes, String id, String layer,
                                             String kind, String title, String content,
                                             Map<String, Object> knowledge, String now) {
        validateLayerKnowledge(layer, knowledge);
        if (title == null || title.isBlank()) title = kind;
        if (content == null || content.isBlank()) content = title;
        if (content.length() > MAX_INLINE_TEXT) content = content.substring(0, MAX_INLINE_TEXT);
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("knowledge_layer", layer);
        metadata.put("knowledge", knowledge);
        metadata.put("created_by", "beyond-light-research");
        nodes.add(node(id, kind, title, content, Map.of("type", "beyond-light-context", "layer", layer), metadata, now));
    }

    private static void validateLayerKnowledge(String layer, Map<String, Object> knowledge) {
        switch (layer) {
            case "historical" -> {
                Object sources = knowledge.get("sources");
                if (!(sources instanceof List<?> list) || list.isEmpty()) throw new IllegalArgumentException("historical knowledge requires source references");
            }
            case "philosophical" -> {
                boolean present = List.of("questions", "assumptions", "principles", "arguments", "ethical_considerations", "consequences")
                        .stream().anyMatch(field -> !contextStrings(knowledge.get(field)).isEmpty());
                if (!present) throw new IllegalArgumentException("philosophical knowledge requires a question, assumption, principle, argument, ethical consideration, or consequence");
            }
            case "experimental" -> {
                if (!nonEmpty(knowledge.get("hypothesis")) || !nonEmpty(knowledge.get("method"))) throw new IllegalArgumentException("experimental knowledge requires hypothesis and method");
                String status = Objects.toString(knowledge.get("outcome_status"), "").trim();
                if (!Set.of("planned", "in_progress", "supported", "not_supported", "inconclusive", "failed", "replicated").contains(status)) throw new IllegalArgumentException("experimental outcomeStatus is not in the canonical layer vocabulary");
                List<String> results = contextStrings(knowledge.get("results"));
                List<String> failures = contextStrings(knowledge.get("failure_modes"));
                List<String> rawDataRefs = contextStrings(knowledge.get("raw_data_refs"));
                Object rawSources = knowledge.get("sources");
                boolean hasSources = rawSources instanceof List<?> sources && !sources.isEmpty();
                if (status.equals("supported") && (results.isEmpty() || (rawDataRefs.isEmpty() && !hasSources))) throw new IllegalArgumentException("supported experiments require results and raw data references or sources");
                if (status.equals("replicated") && (results.isEmpty() || !nonEmpty(knowledge.get("replication_of")))) throw new IllegalArgumentException("replicated experiments require results and replicationOf");
                if ((status.equals("not_supported") || status.equals("inconclusive")) && results.isEmpty() && failures.isEmpty()) throw new IllegalArgumentException("not_supported and inconclusive experiments require results or failure modes");
                if (status.equals("failed") && failures.isEmpty() && results.isEmpty()) throw new IllegalArgumentException("failed experiments require failure modes or results");
            }
            case "cross-disciplinary" -> {
                List<String> disciplines = contextStrings(knowledge.get("disciplines"));
                if (disciplines.stream().map(value -> value.toLowerCase(Locale.ROOT)).distinct().count() < 2 || !nonEmpty(knowledge.get("mapping_rationale"))) throw new IllegalArgumentException("cross-disciplinary knowledge requires two distinct disciplines and mapping rationale");
            }
            default -> throw new IllegalArgumentException("unsupported explicit knowledge layer: " + layer);
        }
    }

    private static boolean nonEmpty(Object value) {
        return value instanceof String text && !text.trim().isEmpty();
    }

    private static Map<String, Object> typedEdge(String source, String target, String relation,
                                                 String layer, String requestId, String now) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("knowledge_layer", layer);
        metadata.put("provenance", Map.of("type", "beyond_light_research", "request_id", requestId));
        return Map.of("source", source, "target", target, "relation", relation,
                "created_at", now, "metadata", metadata);
    }

    private Map<String, Object> node(String id, String kind, String title, String content,
                                     Map<String, Object> source, Map<String, Object> metadata, String now) {
        Map<String, Object> node = new LinkedHashMap<>();
        if (content.length() > MAX_INLINE_TEXT) content = content.substring(0, MAX_INLINE_TEXT);
        node.put("id", id);
        node.put("kind", kind);
        node.put("title", title.length() > 512 ? title.substring(0, 512) : title);
        node.put("content", content);
        node.put("source", source);
        node.put("metadata", metadata);
        node.put("media", Map.of());
        node.put("workspace_id", workspaceId);
        node.put("content_sha256", sha256(content));
        node.put("schema_version", 1);
        node.put("created_at", now);
        node.put("updated_at", now);
        return node;
    }

    private static Map<String, Object> edge(String source, String target, String relation,
                                             String requestId, String now) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("provenance", Map.of("type", "beyond_light_research", "request_id", requestId));
        return Map.of("source", source, "target", target, "relation", relation,
                "created_at", now, "metadata", metadata);
    }

    private static boolean matchesAny(String haystack, List<String> terms) {
        for (String term : terms) if (haystack.contains(term)) return true;
        return false;
    }

    private String getText(URI uri) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(20))
                .header("Accept", "text/plain, application/json").GET().build();
        HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        requireSuccess(response, "read Mnemos Knowledge source archive");
        return response.body();
    }

    private Object getJson(URI uri) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(20))
                .header("Accept", "application/json").GET().build();
        HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
        requireSuccess(response, "read Mnemos Knowledge file");
        return Json.parse(response.body());
    }

    private static void requireSuccess(HttpResponse<String> response, String action) {
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            String body = response.body() == null ? "" : response.body();
            if (body.length() > 500) body = body.substring(0, 500);
            throw new IllegalStateException(action + " failed with HTTP " + response.statusCode() + ": " + body);
        }
    }

    private static String workflow(Map<String, Object> plan, Map<String, Object> analysis) {
        Object steps = plan.get("steps");
        if (steps instanceof List<?> list && !list.isEmpty() && list.get(0) instanceof Map<?, ?> step) {
            return Objects.toString(Json.map(step).get("engineId"), "unspecified");
        }
        return Objects.toString(analysis.get("engineId"), "research.orchestrator");
    }

    private static Map<String, Object> object(Object value, String label) {
        if (!(value instanceof Map<?, ?>)) throw new IllegalArgumentException("dispatch response is missing " + label + " object");
        return Json.map(value);
    }
    private static Map<String, Object> objectOrEmpty(Object value) {
        return value instanceof Map<?, ?> ? Json.map(value) : Map.of();
    }
    private static List<String> strings(Object value, String label) {
        if (!(value instanceof List<?> list)) throw new IllegalStateException(label + " must be an array");
        return list.stream().map(item -> Objects.toString(item, "")).toList();
    }
    private static String safeSourceUrl(String value) {
        if (value == null || value.isBlank()) return "";
        try {
            URI uri = URI.create(value.trim());
            String scheme = Objects.toString(uri.getScheme(), "").toLowerCase(Locale.ROOT);
            if (!(scheme.equals("http") || scheme.equals("https")) || uri.getHost() == null) return "";
            return new URI(scheme, null, uri.getHost(), uri.getPort(), uri.getPath(), null, null).toASCIIString();
        } catch (Exception ignored) {
            return "";
        }
    }
    private static boolean safeFilename(String file) {
        return !file.isBlank() && file.length() <= 240 && !file.contains("/") && !file.contains("\\")
                && !file.equals(".") && !file.equals("..") && file.chars().noneMatch(Character::isISOControl);
    }
    private static String firstEnv(String... keys) {
        for (String key : keys) {
            String value = System.getenv(key);
            if (value != null && !value.isBlank()) return value.trim();
        }
        return "";
    }
    private static String firstEnvOr(String key, String fallback) {
        String value = firstEnv(key);
        return value.isBlank() ? fallback : value;
    }
    private static String requireText(String value, String label) {
        String clean = Objects.toString(value, "").trim();
        if (clean.isEmpty()) throw new IllegalArgumentException(label + " is required");
        return clean;
    }
    private static String requireUuid(String value) {
        String clean = requireText(value, "Mnemos workspace id");
        try { return UUID.fromString(clean).toString(); }
        catch (IllegalArgumentException error) { throw new IllegalArgumentException("MNEMOS_WORKSPACE_ID must be a UUID"); }
    }
    private static URI trimSlash(URI uri) {
        String value = uri.toString();
        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
        return URI.create(value);
    }
    private static URI ensureSlash(URI uri) {
        return uri.toString().endsWith("/") ? uri : URI.create(uri + "/");
    }
    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
    private static String encodePath(String value) {
        return encode(value).replace("+", "%20");
    }
    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (Exception error) { throw new IllegalStateException("SHA-256 is unavailable", error); }
    }
    static String canonicalJson(Object value) {
        if (value == null || value instanceof Boolean) return Json.stringify(value);
        if (value instanceof String string) return canonicalString(string);
        if (value instanceof Number number) return canonicalNumber(number);
        if (value instanceof Map<?, ?> map) {
            StringBuilder out = new StringBuilder("{");
            boolean first = true;
            for (String key : map.keySet().stream().map(String::valueOf).sorted().toList()) {
                if (!first) out.append(',');
                first = false;
                out.append(canonicalString(key)).append(':').append(canonicalJson(map.get(key)));
            }
            return out.append('}').toString();
        }
        if (value instanceof List<?> list) {
            StringBuilder out = new StringBuilder("[");
            for (int i = 0; i < list.size(); i++) {
                if (i > 0) out.append(',');
                out.append(canonicalJson(list.get(i)));
            }
            return out.append(']').toString();
        }
        throw new IllegalArgumentException("unsupported value in canonical JSON payload");
    }
    private static String canonicalString(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20) out.append(String.format(Locale.ROOT, "\\u%04x", (int) ch));
                    else out.append(ch);
                }
            }
        }
        return out.append('"').toString();
    }
    private static String canonicalNumber(Number number) {
        double value = number.doubleValue();
        if (!Double.isFinite(value)) throw new IllegalArgumentException("nonfinite canonical JSON number");
        if (value == 0.0d) return "0";
        java.math.BigDecimal decimal = java.math.BigDecimal.valueOf(value).stripTrailingZeros();
        double absolute = Math.abs(value);
        if (absolute >= 1.0e-6d && absolute < 1.0e21d) return decimal.toPlainString();
        return decimal.toString().replace("E", "e");
    }
}
