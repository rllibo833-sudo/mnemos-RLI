package org.beyondlight;

import java.time.Instant;
import java.util.*;

/** Conservative evidence evaluator shared by all adapters. */
public final class EvidenceEvaluator {
    private EvidenceEvaluator() {}

    public static EvidenceReport evaluate(ResearchRequest request, ResearchPlan plan, AnalysisResult result) {
        List<String> engineIds = plan.steps().stream().map(ResearchPlan.ResearchStep::engineId).toList();
        boolean generalCycle = engineIds.contains("research.open-data-cycle");
        boolean openDataDiscovery = engineIds.contains("research.open-data-discovery");
        boolean datasetAnalysis = engineIds.contains("dataset.deterministic-analysis");
        boolean technologyResearch = engineIds.contains("technology.integrated-research")
                || engineIds.contains("engineering.technology-domain")
                || engineIds.contains("engineering.cross-domain-technology")
                || engineIds.contains("engineering.feasibility-assessment");
        boolean catalogValidation = engineIds.contains("science.catalog-validation");
        boolean symbolic = engineIds.contains("mathematics.symbolic");
        boolean relativity = engineIds.contains("physics.special-relativity")
                || engineIds.contains("physics.metric-geometry");
        boolean engineeringCalculation = engineIds.contains("engineering.calculation");
        boolean benchmark = engineIds.contains("science.numerical-benchmarks");
        boolean materials = engineIds.contains("engineering.material-selection");
        boolean uncertaintyAnalysis = engineIds.contains("science.uncertainty-analysis");

        Map<String, String> checks = new LinkedHashMap<>();
        checks.put("sourceProvenance", result.sources().isEmpty()
                ? "NO_SOURCE_RECORD_ATTACHED" : "SOURCE_METADATA_ATTACHED_NOT_INDEPENDENTLY_VERIFIED");
        checks.put("execution", result.status());
        checks.put("completedSteps", Objects.toString(result.output().getOrDefault("successfulSteps", 0)));
        checks.put("plannedSteps", Objects.toString(result.output().getOrDefault("plannedStepCount", plan.steps().size())));
        checks.put("independentReplication", "NOT_PERFORMED");
        checks.put("experimentalValidation", "NOT_PERFORMED");
        checks.put("specialistDisciplineEngine", generalCycle
                ? "NOT_REGISTERED_FOR_" + plan.primaryDiscipline().toUpperCase(Locale.ROOT)
                : "REGISTERED_ENGINE_ROUTE_SELECTED");

        String classification;
        String summary;
        if (!result.error().isBlank() || result.status().contains("FAILED")) {
            classification = "INCOMPLETE_OR_FAILED";
            summary = "One or more required engine steps did not complete; no research conclusion should be inferred.";
        } else if (hasStatus(result, "NO_OPEN_RECORDS") || hasStatus(result, "NO_NUMERIC_CSV")) {
            classification = "NO_USABLE_EVIDENCE_FOUND";
            summary = "The search or import stage did not produce a usable dataset.";
        } else if (datasetAnalysis) {
            classification = "INTERNAL_DATASET_SCREENING";
            summary = "The result includes deterministic analysis of a selected dataset; it is not independent replication or experimental validation.";
        } else if (openDataDiscovery) {
            classification = "OPEN_DATA_METADATA_DISCOVERY";
            summary = "The run retrieved open repository record metadata only; no full-text interpretation, dataset import or specialist disciplinary analysis was performed.";
        } else if (catalogValidation) {
            classification = "SCIENTIFIC_CATALOG_VALIDATION";
            summary = "The configured scientific catalog passed or failed its implemented metadata and consistency checks; this is not an independent review of every primary source.";
        } else if (symbolic) {
            classification = "SYMBOLIC_MATHEMATICAL_ANALYSIS";
            summary = "The internal symbolic engine evaluated the requested expression operation; mathematical manipulation does not validate the real-world model.";
        } else if (relativity) {
            classification = "THEORETICAL_PHYSICS_CALCULATION";
            summary = "The result is a calculation within the implemented special-relativity model and supplied assumptions, not experimental validation.";
        } else if (benchmark) {
            classification = "NUMERICAL_BENCHMARK_RESULT";
            summary = "The numerical benchmark compared implemented outputs with configured reference values and tolerances; passing cases do not validate every model or engine.";
        } else if (materials) {
            classification = "MATERIAL_PROPERTY_SCREENING";
            summary = "Material candidates were screened against available properties; missing, unverified or condition-dependent values remain limitations.";
        } else if (uncertaintyAnalysis) {
            classification = "MODEL_UNCERTAINTY_ANALYSIS";
            summary = "Uncertainty was propagated or explored using the supplied mathematical model and input assumptions; model-form uncertainty may remain unaccounted for.";
        } else if (technologyResearch || engineeringCalculation) {
            classification = "PRELIMINARY_ENGINEERING_SCREENING";
            summary = "The selected engineering workflow is a bounded model-based screen, not a validated hardware design or certification.";
        } else if (generalCycle) {
            classification = "OPEN_DATA_EXPLORATORY_SCREENING";
            summary = "The run searched open records and performed bounded numeric screening where eligible data could be imported; pattern fit is not a scientific discovery.";
        } else {
            classification = "INTERNAL_ANALYSIS_RESULT";
            summary = "A registered internal analysis engine completed; interpret its result using the recorded assumptions, sources and limitations.";
        }

        List<String> uncertainty = new ArrayList<>();
        uncertainty.add("Source metadata may be incomplete and has not been independently authenticated by this layer.");
        uncertainty.add("A model fit or internal cross-validation result does not establish causation or a physical law.");
        uncertainty.add("No independent replication or experiment is performed by the integration layer.");
        if (generalCycle) {
            uncertainty.add("The current general route is open-data retrieval and numeric screening; it does not provide specialist historical or philosophical reasoning.");
        }
        if (openDataDiscovery) {
            uncertainty.add("Open-data discovery is limited to Zenodo record metadata; the underlying papers and datasets have not been read or independently verified.");
        }

        List<String> limitations = new ArrayList<>(result.limitations());
        limitations.add("Discipline classification is a routing hint, not proof that a specialist engine exists or was executed.");
        limitations.add("LLM-based planning is not enabled; this plan was produced by deterministic rules.");
        return new EvidenceReport(request.id(), classification, summary, checks, uncertainty, limitations, Instant.now());
    }

    private static boolean hasStatus(AnalysisResult result, String token) {
        if (result.status().contains(token)) return true;
        Object raw = result.output().get("stepResults");
        if (raw instanceof List<?> steps) for (Object step : steps) {
            if (step instanceof Map<?, ?> map && Objects.toString(map.get("status"), "").contains(token)) return true;
        }
        Object records = result.output().get("records");
        if (records instanceof List<?> list) for (Object record : list) {
            if (record instanceof Map<?, ?> map && Objects.toString(map.get("status"), "").contains(token)) return true;
        }
        return false;
    }
}
