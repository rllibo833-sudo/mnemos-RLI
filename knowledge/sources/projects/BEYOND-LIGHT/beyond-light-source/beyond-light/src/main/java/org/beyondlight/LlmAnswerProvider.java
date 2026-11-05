package org.beyondlight;

import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;

/** Optional OpenAI-compatible LLM answer layer. It never replaces deterministic engines. */
public final class LlmAnswerProvider {
    private final HttpClient http;
    private final URI endpoint;
    private final String apiKey;
    private final String model;

    private LlmAnswerProvider(HttpClient http, URI endpoint, String apiKey, String model) {
        this.http = http;
        this.endpoint = endpoint;
        this.apiKey = apiKey;
        this.model = model;
    }

    public static Optional<LlmAnswerProvider> fromEnvironment() {
        String key = env("BEYOND_LIGHT_LLM_API_KEY");
        String model = env("BEYOND_LIGHT_LLM_MODEL");
        String base = env("BEYOND_LIGHT_LLM_BASE_URL");
        if (key.isBlank() || model.isBlank()) return Optional.empty();
        if (base.isBlank()) base = "https://api.openai.com/v1";
        try {
            URI root = URI.create(base.endsWith("/") ? base : base + "/");
            URI chat = root.resolve("chat/completions");
            if (!Set.of("https", "http").contains(chat.getScheme()) || chat.getHost() == null) {
                throw new IllegalArgumentException("LLM base URL must be an HTTP(S) URL");
            }
            return Optional.of(new LlmAnswerProvider(
                    HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build(),
                    chat, key, model));
        } catch (RuntimeException error) {
            throw new IllegalStateException("Invalid LLM provider configuration", error);
        }
    }

    public Map<String, Object> answer(String question, Map<String, Object> graphEvidence,
                                      Map<String, Object> researchResult) throws Exception {
        String system = "You are Beyond-Light, a research assistant. Answer using supplied Mnemos-RLI Knowledge Graph evidence and deterministic research output. Never invent sources, measurements, proofs, or discoveries. Distinguish established facts, computational results, hypotheses, and unknowns. If evidence is insufficient, say so. Cite source titles and URLs from evidence.";
        Map<String, Object> userPayload = new LinkedHashMap<>();
        userPayload.put("question", question);
        userPayload.put("knowledge_graph_evidence", graphEvidence);
        userPayload.put("deterministic_research", researchResult.getOrDefault("analysis", Map.of()));
        userPayload.put("evidence_assessment", researchResult.getOrDefault("evidence", Map.of()));
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", model);
        body.put("temperature", 0.2);
        body.put("messages", List.of(
                Map.of("role", "system", "content", system),
                Map.of("role", "user", "content", Json.stringify(userPayload))));
        HttpRequest request = HttpRequest.newBuilder(endpoint).timeout(Duration.ofSeconds(60))
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(Json.stringify(body), StandardCharsets.UTF_8))
                .build();
        HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            String detail = response.body() == null ? "" : response.body();
            if (detail.length() > 500) detail = detail.substring(0, 500);
            throw new IllegalStateException("LLM provider returned HTTP " + response.statusCode() + ": " + detail);
        }
        Map<String, Object> payload = Json.map(Json.parse(response.body()));
        List<?> choices = (List<?>) payload.getOrDefault("choices", List.of());
        if (choices.isEmpty()) throw new IllegalStateException("LLM provider returned no choices");
        Map<String, Object> choice = Json.map(choices.get(0));
        Map<String, Object> message = Json.map(choice.get("message"));
        String content = Objects.toString(message.get("content"), "").trim();
        if (content.isBlank()) throw new IllegalStateException("LLM provider returned an empty answer");
        return Map.of("status", "ACTIVE", "provider", endpoint.getHost(), "model", model, "answer", content);
    }

    private static String env(String name) {
        return Objects.toString(System.getenv(name), "").trim();
    }
}
