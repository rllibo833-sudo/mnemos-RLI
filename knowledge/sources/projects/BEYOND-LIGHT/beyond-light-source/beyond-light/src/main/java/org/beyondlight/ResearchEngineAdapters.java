package org.beyondlight;

import java.time.Instant;
import java.util.*;

/** Adapters that connect existing engines to the common ResearchEngine contract. */
public final class ResearchEngineAdapters {
    private ResearchEngineAdapters() {}

    public static EngineRegistry createDefaultRegistry() {
        EngineRegistry registry = new EngineRegistry();
        registry.register(new OpenDataCycleAdapter());
        registry.register(new DatasetAnalysisAdapter());
        registry.register(new IntegratedTechnologyAdapter());
        ResearchDomainAdapters.register(registry);
        return registry;
    }

    private static final class OpenDataCycleAdapter implements ResearchEngine {
        public String id() { return "research.open-data-cycle"; }
        public boolean supports(ResearchRequest request) { return request.question().length() >= 3 && request.question().length() <= 160; }
        public AnalysisResult execute(ResearchRequest request, ResearchPlan plan) {
            Instant started = Instant.now();
            List<Map<String, Object>> records = ResearchCycle.run(request.question(), Main.DATA, Main.REGISTRY.all(), Main.MACHINE);
            List<SourceRecord> sources = new ArrayList<>();
            List<String> limitations = new ArrayList<>();
            for (Map<String, Object> record : records) {
                Object rawSources = record.get("sources");
                if (rawSources instanceof List<?> list) for (Object raw : list) {
                    if (raw instanceof Map<?, ?>) sources.add(SourceRecord.fromMap(Json.map(raw)));
                }
                Object rawSearchResults = record.get("searchResults");
                if (rawSearchResults instanceof List<?> searchResults) for (Object raw : searchResults) {
                    if (raw instanceof Map<?, ?>) {
                        Map<String, Object> metadata = new LinkedHashMap<>(Json.map(raw));
                        metadata.putIfAbsent("sourceType", "open-data-record");
                        metadata.putIfAbsent("provider", "Zenodo");
                        metadata.putIfAbsent("verificationStatus", "METADATA_ONLY_NOT_IMPORTED");
                        sources.add(SourceRecord.fromMap(metadata));
                    }
                }
                Object rawLimits = record.get("limitations");
                if (rawLimits instanceof List<?> list) for (Object raw : list) limitations.add(String.valueOf(raw));
            }
            Map<String, Object> output = new LinkedHashMap<>();
            output.put("records", records);
            output.put("recordCount", records.size());
            String status = records.isEmpty() ? "NO_RESEARCH_RECORDS" : Objects.toString(records.get(records.size() - 1).get("status"), "COMPLETED");
            return new AnalysisResult(null, request.id(), id(), status, started, Instant.now(), output,
                    distinctSources(sources), limitations, "");
        }
    }

    private static final class DatasetAnalysisAdapter implements ResearchEngine {
        public String id() { return "dataset.deterministic-analysis"; }
        public boolean supports(ResearchRequest request) {
            return has(request.context(), "datasetId") && has(request.context(), "x") && has(request.context(), "y");
        }
        public AnalysisResult execute(ResearchRequest request, ResearchPlan plan) {
            Instant started = Instant.now();
            Map<String, Object> context = request.context();
            Map<String, Object> result = DeterministicResearchEngine.run(
                    Main.DATA.get(text(context, "datasetId")), text(context, "x"), text(context, "y"));
            List<SourceRecord> sources = sourcesFrom(result.get("sources"));
            List<String> limitations = strings(result.get("limitations"));
            return new AnalysisResult(null, request.id(), id(), Objects.toString(result.get("status"), "COMPLETED"),
                    started, Instant.now(), result, sources, limitations, "");
        }
    }

    private static final class IntegratedTechnologyAdapter implements ResearchEngine {
        public String id() { return "technology.integrated-research"; }
        public boolean supports(ResearchRequest request) {
            Map<String, Object> c = request.context();
            return "integrated-technology".equals(c.get("workflow"))
                    && has(c, "datasetId") && has(c, "target") && has(c, "powerVariable");
        }
        public AnalysisResult execute(ResearchRequest request, ResearchPlan plan) {
            Instant started = Instant.now();
            Map<String, Object> c = request.context();
            Map<String, Object> result = IntegratedTechnologyResearch.explore(
                    Main.DATA.get(text(c, "datasetId")), text(c, "target"), text(c, "powerVariable"),
                    number(c, "dryMassKg", 900), number(c, "payloadKg", 100), number(c, "deltaVMs", 9000),
                    number(c, "availablePowerW", 100_000), number(c, "coolingCapacityW", 50_000),
                    number(c, "maximumBurnDays", 180), Main.MACHINE.assemble());
            return new AnalysisResult(null, request.id(), id(), Objects.toString(result.get("status"), "COMPLETED"),
                    started, Instant.now(), result, sourcesFrom(result.get("sources")),
                    strings(result.get("limitations")), "");
        }
    }

    private static List<SourceRecord> sourcesFrom(Object raw) {
        if (!(raw instanceof List<?> list)) return List.of();
        List<SourceRecord> out = new ArrayList<>();
        for (Object item : list) if (item instanceof Map<?, ?>) out.add(SourceRecord.fromMap(Json.map(item)));
        return distinctSources(out);
    }
    private static List<SourceRecord> distinctSources(List<SourceRecord> input) {
        Map<String, SourceRecord> unique = new LinkedHashMap<>();
        for (SourceRecord source : input) unique.putIfAbsent(source.id(), source);
        return List.copyOf(unique.values());
    }
    private static List<String> strings(Object raw) {
        if (!(raw instanceof List<?> list)) return List.of();
        return list.stream().map(String::valueOf).toList();
    }
    private static boolean has(Map<String, Object> c, String k) { return c.get(k) != null && !c.get(k).toString().isBlank(); }
    private static String text(Map<String, Object> c, String k) { return Objects.toString(c.get(k), ""); }
    private static double number(Map<String, Object> c, String k, double fallback) {
        Object value = c.get(k);
        if (value == null) return fallback;
        if (!(value instanceof Number n)) throw new IllegalArgumentException(k + " must be numeric");
        double result = n.doubleValue();
        if (!Double.isFinite(result)) throw new IllegalArgumentException(k + " must be finite");
        return result;
    }
}
