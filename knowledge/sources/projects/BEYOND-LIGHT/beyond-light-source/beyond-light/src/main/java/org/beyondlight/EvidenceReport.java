package org.beyondlight;

import java.time.Instant;
import java.util.*;

/** Evidence assessment; it reports what was checked and never upgrades screening into proof. */
public record EvidenceReport(
        String requestId,
        String classification,
        String summary,
        Map<String, String> checks,
        List<String> uncertainty,
        List<String> limitations,
        Instant assessedAt) {

    public EvidenceReport {
        requestId = Objects.requireNonNull(requestId, "requestId");
        classification = Objects.requireNonNullElse(classification, "UNASSESSED");
        summary = Objects.requireNonNullElse(summary, "");
        checks = checks == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(checks));
        uncertainty = uncertainty == null ? List.of() : List.copyOf(uncertainty);
        limitations = limitations == null ? List.of() : List.copyOf(limitations);
        assessedAt = assessedAt == null ? Instant.now() : assessedAt;
    }

    public Map<String, Object> toMap() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("requestId", requestId); out.put("classification", classification);
        out.put("summary", summary); out.put("checks", checks); out.put("uncertainty", uncertainty);
        out.put("limitations", limitations); out.put("assessedAt", assessedAt.toString());
        return out;
    }
}
