package org.beyondlight;

import java.util.*;

/** Explicit registry prevents request handlers from calling arbitrary engine classes. */
public final class EngineRegistry {
    private final Map<String, ResearchEngine> engines = new LinkedHashMap<>();

    public synchronized void register(ResearchEngine engine) {
        Objects.requireNonNull(engine, "engine");
        String id = Objects.requireNonNull(engine.id(), "engine id").trim();
        if (id.isEmpty()) throw new IllegalArgumentException("engine id is required");
        if (engines.putIfAbsent(id, engine) != null) throw new IllegalArgumentException("duplicate research engine: " + id);
    }

    public synchronized ResearchEngine require(String id) {
        ResearchEngine engine = engines.get(id);
        if (engine == null) throw new IllegalArgumentException("research engine is not registered: " + id);
        return engine;
    }

    public synchronized List<String> ids() { return List.copyOf(engines.keySet()); }

    public synchronized boolean supports(String id, ResearchRequest request) {
        ResearchEngine engine = engines.get(id);
        return engine != null && engine.supports(request);
    }
}
