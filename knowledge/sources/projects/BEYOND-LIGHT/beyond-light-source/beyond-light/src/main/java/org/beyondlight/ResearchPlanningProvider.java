package org.beyondlight;

/** Replaceable planning boundary for deterministic, LLM-backed, or human-authored planners. */
public interface ResearchPlanningProvider {
    ResearchPlan plan(ResearchRequest request);
}
