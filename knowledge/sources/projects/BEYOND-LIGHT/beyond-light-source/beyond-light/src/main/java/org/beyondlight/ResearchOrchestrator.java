package org.beyondlight;

import java.time.Instant;
import java.util.*;

/** Single dispatch point coordinating ordered multi-engine plans and evidence review. */
public final class ResearchOrchestrator {
    private final ResearchPlanningProvider planner;
    private final EngineRegistry registry;

    public ResearchOrchestrator(ResearchPlanningProvider planner, EngineRegistry registry) {
        this.planner = Objects.requireNonNull(planner, "planner");
        this.registry = Objects.requireNonNull(registry, "registry");
    }

    public Map<String, Object> dispatch(ResearchRequest request) {
        ResearchPlan plan = planner.plan(request);
        Instant started = Instant.now();
        List<AnalysisResult> stepResults = new ArrayList<>();
        List<SourceRecord> allSources = new ArrayList<>();
        LinkedHashSet<String> allLimitations = new LinkedHashSet<>();
        List<String> executionOrder = new ArrayList<>();
        int successfulSteps = 0;
        boolean requiredFailure = false;
        List<String> errors = new ArrayList<>();

        for (ResearchPlan.ResearchStep step : plan.steps()) {
            executionOrder.add(step.engineId());
            ResearchEngine engine = registry.require(step.engineId());
            AnalysisResult result;
            Instant stepStarted = Instant.now();
            try {
                if (!engine.supports(request)) throw new IllegalArgumentException(
                        "request does not satisfy engine contract: " + engine.id());
                result = engine.execute(request, plan);
                if (result == null) throw new IllegalStateException("engine returned no AnalysisResult");
                if (result.status().contains("FAILED") || result.status().contains("ERROR") || !result.error().isBlank()) {
                    String message = result.error().isBlank() ? result.status() : result.error();
                    errors.add(step.engineId() + ": " + message);
                    if (step.required()) requiredFailure = true;
                } else {
                    successfulSteps++;
                }
            } catch (Exception error) {
                String message = Objects.toString(error.getMessage(), error.getClass().getSimpleName());
                errors.add(step.engineId() + ": " + message);
                result = new AnalysisResult(null, request.id(), step.engineId(), "ENGINE_FAILED",
                        stepStarted, Instant.now(), Map.of(), List.of(),
                        List.of("This engine step failed before producing a usable result."), message);
                if (step.required()) requiredFailure = true;
            }
            stepResults.add(result);
            allSources.addAll(result.sources());
            allLimitations.addAll(result.limitations());
            if (requiredFailure) break;
        }

        AnalysisResult last = stepResults.get(stepResults.size() - 1);
        Map<String, Object> output = new LinkedHashMap<>(last.output());
        output.put("stepResults", stepResults.stream().map(AnalysisResult::toMap).toList());
        output.put("stepCount", stepResults.size());
        output.put("plannedStepCount", plan.steps().size());
        output.put("successfulSteps", successfulSteps);
        output.put("executionOrder", executionOrder);

        String status = requiredFailure ? "ORCHESTRATION_FAILED"
                : plan.steps().size() == 1 ? last.status() : "ORCHESTRATION_COMPLETED";
        String error = String.join("; ", errors);
        AnalysisResult aggregate = new AnalysisResult(null, request.id(), "research.orchestrator",
                status, started, Instant.now(), output, distinctSources(allSources),
                List.copyOf(allLimitations), error);
        EvidenceReport evidence = EvidenceEvaluator.evaluate(request, plan, aggregate);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("request", request.toMap());
        response.put("plan", plan.toMap());
        response.put("analysis", aggregate.toMap());
        response.put("evidence", evidence.toMap());
        response.put("availableEngines", registry.ids());
        return response;
    }

    private static List<SourceRecord> distinctSources(List<SourceRecord> sources) {
        Map<String, SourceRecord> unique = new LinkedHashMap<>();
        for (SourceRecord source : sources) unique.putIfAbsent(source.id(), source);
        return List.copyOf(unique.values());
    }
}
