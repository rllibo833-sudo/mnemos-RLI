package org.beyondlight;

import java.time.Instant;
import java.util.*;

/** Normalized output from one registered research engine. */
public record AnalysisResult(
        String id,
        String requestId,
        String engineId,
        String status,
        Instant startedAt,
        Instant completedAt,
        Map<String, Object> output,
        List<SourceRecord> sources,
        List<String> limitations,
        String error) {

    public AnalysisResult {
        id = Objects.requireNonNullElseGet(id, () -> UUID.randomUUID().toString());
        requestId = Objects.requireNonNull(requestId, "requestId");
        engineId = Objects.requireNonNull(engineId, "engineId");
        status = Objects.requireNonNullElse(status, "UNKNOWN");
        startedAt = startedAt == null ? Instant.now() : startedAt;
        completedAt = completedAt == null ? Instant.now() : completedAt;
        output = output == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(output));
        sources = sources == null ? List.of() : List.copyOf(sources);
        limitations = limitations == null ? List.of() : List.copyOf(limitations);
        error = Objects.requireNonNullElse(error, "");
    }

    public Map<String, Object> toMap() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", id); out.put("requestId", requestId); out.put("engineId", engineId);
        out.put("status", status); out.put("startedAt", startedAt.toString());
        out.put("completedAt", completedAt.toString()); out.put("output", output);
        out.put("sources", sources.stream().map(SourceRecord::toMap).toList());
        out.put("limitations", limitations); out.put("error", error);
        return out;
    }
}
