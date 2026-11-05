package org.beyondlight;

import java.time.Instant;
import java.util.*;

/** Explicit, inspectable execution plan produced before any research engine runs. */
public record ResearchPlan(
        String requestId,
        String primaryDiscipline,
        List<String> disciplines,
        List<ResearchStep> steps,
        String rationale,
        Instant createdAt) {

    public ResearchPlan {
        requestId = Objects.requireNonNull(requestId, "requestId");
        primaryDiscipline = Objects.requireNonNullElse(primaryDiscipline, "general");
        disciplines = disciplines == null ? List.of(primaryDiscipline) : List.copyOf(disciplines);
        steps = steps == null ? List.of() : List.copyOf(steps);
        if (steps.isEmpty()) throw new IllegalArgumentException("research plan requires at least one execution step");
        rationale = Objects.requireNonNullElse(rationale, "");
        createdAt = createdAt == null ? Instant.now() : createdAt;
    }

    public record ResearchStep(String id, String engineId, String purpose, boolean required) {
        public ResearchStep {
            id = Objects.requireNonNull(id, "step id");
            engineId = Objects.requireNonNull(engineId, "engine id");
            purpose = Objects.requireNonNullElse(purpose, "");
        }
        public Map<String, Object> toMap() {
            return Map.of("id", id, "engineId", engineId, "purpose", purpose, "required", required);
        }
    }

    public Map<String, Object> toMap() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("requestId", requestId);
        out.put("primaryDiscipline", primaryDiscipline);
        out.put("disciplines", disciplines);
        out.put("steps", steps.stream().map(ResearchStep::toMap).toList());
        out.put("rationale", rationale);
        out.put("createdAt", createdAt.toString());
        return out;
    }
}
