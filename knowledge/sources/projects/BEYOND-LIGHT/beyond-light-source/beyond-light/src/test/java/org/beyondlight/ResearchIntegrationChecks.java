package org.beyondlight;

import java.util.*;

/** Small offline regression suite for the integration contracts and deterministic planner. */
public final class ResearchIntegrationChecks {
    private static int checks;
    private ResearchIntegrationChecks() {}
    public static void main(String[] args) throws Exception {
        ResearchRequest request = ResearchRequest.create("Analisis dataset energi", Map.of(
                "datasetId", "fixture", "x", "time", "y", "energy"), List.of("physics"));
        check(request.id() != null && request.question().equals("Analisis dataset energi"), "request creation");
        check(request.context().get("datasetId").equals("fixture"), "request context retained");

        ResearchPlan plan = new ResearchPlanner().plan(request);
        check(plan.steps().get(0).engineId().equals("dataset.deterministic-analysis"), "structured dataset route");
        check(plan.primaryDiscipline().equals("data-science"), "dataset discipline");

        ResearchRequest integrated = ResearchRequest.create("Technology screening", Map.of(
                "workflow", "integrated-technology", "datasetId", "fixture", "target", "thrust",
                "powerVariable", "power", "x", "time", "y", "power"), List.of());
        check(new ResearchPlanner().plan(integrated).steps().get(0).engineId().equals("technology.integrated-research"),
                "explicit workflow takes precedence over generic dataset route");

        ResearchRequest general = ResearchRequest.create("Apa sejarah perkembangan energi?", Map.of(), List.of());
        ResearchPlan generalPlan = new ResearchPlanner().plan(general);
        check(generalPlan.primaryDiscipline().equals("history"), "history hint classification");
        check(generalPlan.steps().get(0).engineId().equals("research.open-data-discovery"),
                "history routes to metadata discovery instead of numeric screening");
        ResearchRequest generalScience = ResearchRequest.create("Explore a general science topic", Map.of(), List.of());
        check(new ResearchPlanner().plan(generalScience).steps().get(0).engineId().equals("research.open-data-cycle"),
                "general science route remains explicit");

        Map<String,String> workflowRoutes = Map.ofEntries(
                Map.entry("catalog-validation", "science.catalog-validation"),
                Map.entry("symbolic", "mathematics.symbolic"),
                Map.entry("relativity", "physics.special-relativity"),
                Map.entry("feasibility", "engineering.feasibility-assessment"),
                Map.entry("benchmark", "science.numerical-benchmarks"),
                Map.entry("material-selection", "engineering.material-selection"),
                Map.entry("uncertainty", "science.uncertainty-analysis"),
                Map.entry("technology-domain", "engineering.technology-domain"),
                Map.entry("cross-domain-technology", "engineering.cross-domain-technology"),
                Map.entry("integrated-technology", "technology.integrated-research"),
                Map.entry("dataset-analysis", "dataset.deterministic-analysis"),
                Map.entry("open-data", "research.open-data-cycle"),
                Map.entry("general-relativity", "physics.metric-geometry"),
                Map.entry("engineering-calculation", "engineering.calculation"),
                Map.entry("open-data-discovery", "research.open-data-discovery"));
        for (var route : workflowRoutes.entrySet()) {
            ResearchRequest routed = ResearchRequest.create("Workflow test", Map.of("workflow", route.getKey()), List.of());
            check(new ResearchPlanner().plan(routed).steps().get(0).engineId().equals(route.getValue()),
                    "workflow route " + route.getKey());
        }

        EngineRegistry fullRegistry = ResearchEngineAdapters.createDefaultRegistry();
        check(fullRegistry.ids().size() == 15, "all existing workflow adapters registered");
        check(fullRegistry.ids().contains("engineering.cross-domain-technology"), "cross-domain adapter registered");

        ResearchRequest symbolicRequest = ResearchRequest.create("Differentiate x squared", Map.of(
                "workflow", "symbolic", "operation", "differentiate", "expression", "x^2", "variable", "x"), List.of());
        Map<String,Object> symbolicResponse = new ResearchOrchestrator(new ResearchPlanner(), fullRegistry).dispatch(symbolicRequest);
        Map<String,Object> symbolicAnalysis = Json.map(symbolicResponse.get("analysis"));
        check("SYMBOLIC_OPERATION_COMPLETED".equals(symbolicAnalysis.get("status")), "symbolic adapter executes");
        check("SYMBOLIC_MATHEMATICAL_ANALYSIS".equals(Json.map(symbolicResponse.get("evidence")).get("classification")),
                "symbolic evidence classification");

        ResearchRequest relativityRequest = ResearchRequest.create("Evaluate special relativity", Map.of(
                "workflow", "relativity", "massKg", 1.0, "velocityMs", Physics.C * 0.1,
                "elapsedTimeS", 10.0, "lengthM", 2.0), List.of());
        Map<String,Object> relativityResponse = new ResearchOrchestrator(new ResearchPlanner(), fullRegistry).dispatch(relativityRequest);
        check("THEORETICAL_PHYSICS_CALCULATION".equals(Json.map(relativityResponse.get("evidence")).get("classification")),
                "relativity adapter and evidence classification");

        ResearchRequest uncertaintyRequest = ResearchRequest.create("Propagate input uncertainty", Map.of(
                "workflow", "uncertainty", "mode", "propagate", "expression", "x^2",
                "means", Map.of("x", 2.0), "sigma", Map.of("x", 0.1)), List.of());
        Map<String,Object> uncertaintyResponse = new ResearchOrchestrator(new ResearchPlanner(), fullRegistry).dispatch(uncertaintyRequest);
        check("MODEL_UNCERTAINTY_ANALYSIS".equals(Json.map(uncertaintyResponse.get("evidence")).get("classification")),
                "uncertainty adapter and evidence classification");

        ResearchRequest metricRequest = ResearchRequest.create("Diagnose Minkowski metric", Map.of(
                "workflow", "general-relativity", "operation", "diagnose", "model", "minkowski",
                "coordinates", List.of(0.0, 0.0, 1.0, 1.0)), List.of());
        Map<String,Object> metricResponse = new ResearchOrchestrator(new ResearchPlanner(), fullRegistry).dispatch(metricRequest);
        Map<String,Object> metricOutput = Json.map(Json.map(metricResponse.get("analysis")).get("output"));
        check(((List<?>)metricOutput.get("executionOrder")).contains("physics.metric-geometry"),
                "general relativity metric adapter executes");

        ResearchRequest engineeringRequest = ResearchRequest.create("Calculate electrical power", Map.of(
                "workflow", "engineering-calculation", "operation", "electrical", "voltageV", 12.0,
                "currentA", 2.0, "resistanceOhm", 6.0, "durationS", 5.0), List.of());
        Map<String,Object> engineeringResponse = new ResearchOrchestrator(new ResearchPlanner(), fullRegistry).dispatch(engineeringRequest);
        Map<String,Object> engineeringOutput = Json.map(Json.map(engineeringResponse.get("analysis")).get("output"));
        check(((List<?>)engineeringOutput.get("executionOrder")).contains("engineering.calculation"),
                "engineering calculation adapter executes");

        EngineRegistry registry = new EngineRegistry();
        ResearchEngine fake = new ResearchEngine() {
            public String id() { return "test.engine"; }
            public boolean supports(ResearchRequest r) { return true; }
            public AnalysisResult execute(ResearchRequest r, ResearchPlan p) {
                return new AnalysisResult(null, r.id(), id(), "TEST_SCREENING", null, null,
                        Map.of("value", 2), List.of(), List.of("fixture only"), "");
            }
        };
        registry.register(fake);
        check(registry.require("test.engine") == fake, "engine registration and lookup");
        boolean duplicateRejected = false;
        try { registry.register(fake); } catch (IllegalArgumentException expected) { duplicateRejected = true; }
        check(duplicateRejected, "duplicate engine id rejected");

        ResearchEngine second = new ResearchEngine() {
            public String id() { return "test.second"; }
            public boolean supports(ResearchRequest r) { return true; }
            public AnalysisResult execute(ResearchRequest r, ResearchPlan p) {
                return new AnalysisResult(null, r.id(), id(), "SECOND_STEP_OK", null, null,
                        Map.of("second", true), List.of(), List.of(), "");
            }
        };
        EngineRegistry multiRegistry = new EngineRegistry();
        multiRegistry.register(fake);
        multiRegistry.register(second);
        ResearchPlanningProvider twoStepPlanner = r -> new ResearchPlan(r.id(), "general", List.of("general"),
                List.of(new ResearchPlan.ResearchStep("first", "test.engine", "first step", true),
                        new ResearchPlan.ResearchStep("second", "test.second", "second step", true)),
                "multi-step fixture", null);
        Map<String, Object> multiResponse = new ResearchOrchestrator(twoStepPlanner, multiRegistry).dispatch(general);
        Map<String, Object> multiAnalysis = Json.map(multiResponse.get("analysis"));
        Map<String, Object> multiOutput = Json.map(multiAnalysis.get("output"));
        check(((Number) multiOutput.get("stepCount")).intValue() == 2, "multi-step orchestration runs both engines");
        check(((Number) multiOutput.get("successfulSteps")).intValue() == 2, "multi-step success count");

        ResearchPlan fakePlan = new ResearchPlan(general.id(), "general", List.of("general"),
                List.of(new ResearchPlan.ResearchStep("one", "test.engine", "test", true)), "fixture", null);
        Map<String, Object> response = new ResearchOrchestrator(new ResearchPlanner(), registryFor(fake)).dispatch(generalScience);
        check(response.containsKey("request") && response.containsKey("plan")
                && response.containsKey("analysis") && response.containsKey("evidence"), "orchestrator response contract");
        Map<String, Object> evidence = Json.map(response.get("evidence"));
        check("NOT_PERFORMED".equals(Json.map(evidence.get("checks")).get("experimentalValidation")),
                "evidence never claims experiments");
        check(fakePlan.steps().size() == 1, "plan step shape");
        check(SourceRecord.fromMap(Map.of("title", "Paper", "doi", "10.0000/example")).doi().equals("10.0000/example"),
                "source provenance mapping");
        check(Json.parse(Json.stringify(response)) instanceof Map<?, ?>, "response JSON serialization");
        MnemosKnowledgeChecks.run();
        System.out.println("Research integration checks passed: " + checks);
    }

    private static EngineRegistry registryFor(ResearchEngine engine) {
        EngineRegistry registry = new EngineRegistry();
        registry.register(new ResearchEngine() {
            public String id() { return "research.open-data-cycle"; }
            public boolean supports(ResearchRequest r) { return true; }
            public AnalysisResult execute(ResearchRequest r, ResearchPlan p) throws Exception {
                return engine.execute(r, new ResearchPlan(r.id(), "general", List.of("general"),
                        List.of(new ResearchPlan.ResearchStep("one", engine.id(), "test", true)), "test", null));
            }
        });
        return registry;
    }
    private static void check(boolean condition, String label) {
        checks++;
        if (!condition) throw new AssertionError(label);
    }
}
