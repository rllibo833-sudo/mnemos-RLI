package org.beyondlight;

import java.util.*;

/**
 * Deterministic baseline planner. It is intentionally not presented as LLM reasoning:
 * future LLM planners can implement the same plan contract without changing execution.
 */
public final class ResearchPlanner implements ResearchPlanningProvider {
    public ResearchPlan plan(ResearchRequest request) {
        String question = request.question().toLowerCase(Locale.ROOT);
        Map<String, Object> context = request.context();
        String engineId;
        String discipline;
        String purpose;
        String rationale;

        String workflow = Objects.toString(context.get("workflow"), "");
        Map<String,String> workflows = Map.ofEntries(
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
        if (!workflow.isBlank() && workflows.containsKey(workflow)) {
            engineId = workflows.get(workflow);
            discipline = workflow.equals("symbolic") ? "mathematics"
                    : workflow.equals("relativity") ? "physics"
                    : workflow.equals("dataset-analysis") ? "data-science"
                    : workflow.equals("open-data") || workflow.equals("open-data-discovery") ? inferDiscipline(question, request.disciplineHints())
                    : workflow.equals("catalog-validation") || workflow.equals("benchmark") || workflow.equals("uncertainty") ? "science"
                    : "engineering";
            purpose = "Run the explicitly selected existing Beyond-Light domain workflow.";
            rationale = "The request explicitly selects a registered workflow; the planner does not infer unrequested tool execution.";
        } else if ("integrated-technology".equals(context.get("workflow"))
                && has(context, "datasetId") && has(context, "target") && has(context, "powerVariable")) {
            engineId = "technology.integrated-research";
            discipline = "engineering";
            purpose = "Run the existing integrated technology research workflow.";
            rationale = "The request explicitly selects the integrated-technology workflow and its required dataset fields.";
        } else if (has(context, "datasetId") && has(context, "x") && has(context, "y")) {
            engineId = "dataset.deterministic-analysis";
            discipline = "data-science";
            purpose = "Analyze the explicitly selected local dataset and variable pair.";
            rationale = "The request supplies a dataset identifier and both analysis variables.";
        } else {
            if (request.question().length() > 160) {
                throw new IllegalArgumentException("General open-data research currently accepts topics up to 160 characters; shorten the question or use a structured workflow.");
            }
            discipline = inferDiscipline(question, request.disciplineHints());
            if (Set.of("history", "philosophy", "economics", "social-science", "chemistry", "biology").contains(discipline)) {
                engineId = "research.open-data-discovery";
                purpose = "Retrieve open research-record metadata without forcing nonnumeric disciplines into a numeric-analysis pipeline.";
                rationale = "No specialist engine is registered for this discipline; use metadata-only open-source discovery and disclose that interpretive synthesis is not available.";
            } else {
                engineId = "research.open-data-cycle";
                purpose = "Search open research records, import eligible numeric CSV files, and run the existing bounded screening cycle.";
                rationale = "No specialized structured workflow was supplied; use the existing general open-data research cycle.";
            }
        }

        List<String> disciplines = new ArrayList<>();
        disciplines.add(discipline);
        for (String hint : request.disciplineHints()) if (!disciplines.contains(hint)) disciplines.add(hint);
        ResearchPlan.ResearchStep step = new ResearchPlan.ResearchStep("step-1", engineId, purpose, true);
        return new ResearchPlan(request.id(), discipline, disciplines, List.of(step), rationale, null);
    }

    private static boolean has(Map<String, Object> context, String key) {
        Object value = context.get(key);
        return value != null && !value.toString().isBlank();
    }

    private static String inferDiscipline(String question, List<String> hints) {
        if (!hints.isEmpty()) return hints.get(0).toLowerCase(Locale.ROOT);
        if (contains(question, "sejarah", "history", "historis")) return "history";
        if (contains(question, "filsafat", "filosofi", "philosophy", "etika", "ethics")) return "philosophy";
        if (contains(question, "ekonomi", "economy", "economic", "pasar")) return "economics";
        if (contains(question, "sosial", "masyarakat", "sociology")) return "social-science";
        if (contains(question, "kimia", "chemical", "chemistry", "reaksi")) return "chemistry";
        if (contains(question, "biologi", "biology", "genetik")) return "biology";
        if (contains(question, "fisika", "physics", "energi", "gravitasi")) return "physics";
        if (contains(question, "matematika", "mathematics", "equation", "persamaan")) return "mathematics";
        if (contains(question, "mesin", "rekayasa", "engineering", "material", "desain")) return "engineering";
        return "general";
    }

    private static boolean contains(String text, String... terms) {
        for (String term : terms) if (text.contains(term)) return true;
        return false;
    }
}
