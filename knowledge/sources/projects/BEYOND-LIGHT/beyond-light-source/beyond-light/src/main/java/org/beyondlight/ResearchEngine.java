package org.beyondlight;

/** Adapter boundary for existing and future research engines. */
public interface ResearchEngine {
    String id();
    boolean supports(ResearchRequest request);
    AnalysisResult execute(ResearchRequest request, ResearchPlan plan) throws Exception;
}
