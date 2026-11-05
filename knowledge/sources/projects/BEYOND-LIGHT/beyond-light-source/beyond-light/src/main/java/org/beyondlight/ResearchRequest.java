package org.beyondlight;

import java.time.Instant;
import java.util.*;

/** Immutable user request entering the research integration layer. */
public record ResearchRequest(
        String id,
        String question,
        Map<String, Object> context,
        List<String> disciplineHints,
        Instant createdAt) {

    public ResearchRequest {
        id = requireText(id, "request id", 128);
        question = requireText(question, "question", 2000);
        context = context == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(context));
        disciplineHints = disciplineHints == null ? List.of() : disciplineHints.stream()
                .filter(Objects::nonNull).map(String::trim).filter(s -> !s.isEmpty()).distinct().limit(12).toList();
        createdAt = createdAt == null ? Instant.now() : createdAt;
    }

    public static ResearchRequest create(String question, Map<String, Object> context, List<String> hints) {
        return new ResearchRequest(UUID.randomUUID().toString(), question, context, hints, Instant.now());
    }

    public static ResearchRequest fromMap(Map<String, Object> value) {
        Object rawContext = value.get("context");
        Map<String, Object> context = rawContext instanceof Map<?, ?> ? Json.map(rawContext) : Map.of();
        Object rawHints = value.get("disciplineHints");
        List<String> hints = rawHints instanceof List<?> list
                ? list.stream().map(String::valueOf).toList() : List.of();
        return new ResearchRequest(
                Objects.toString(value.get("id"), UUID.randomUUID().toString()),
                Objects.toString(value.get("question"), ""),
                context,
                hints,
                parseInstant(value.get("createdAt")));
    }

    public Map<String, Object> toMap() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", id);
        out.put("question", question);
        out.put("context", context);
        out.put("disciplineHints", disciplineHints);
        out.put("createdAt", createdAt.toString());
        return out;
    }

    private static Instant parseInstant(Object value) {
        if (value == null || value.toString().isBlank()) return Instant.now();
        try { return Instant.parse(value.toString()); }
        catch (RuntimeException ignored) { throw new IllegalArgumentException("createdAt must be an ISO-8601 timestamp"); }
    }

    private static String requireText(String value, String label, int max) {
        String clean = Objects.toString(value, "").trim();
        if (clean.isEmpty() || clean.length() > max) throw new IllegalArgumentException(label + " must contain 1.." + max + " characters");
        return clean;
    }
}
