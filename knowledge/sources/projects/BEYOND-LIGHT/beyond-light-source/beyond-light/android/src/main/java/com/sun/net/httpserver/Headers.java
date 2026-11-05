package com.sun.net.httpserver;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;

public final class Headers extends HashMap<String, List<String>> {
    public void set(String name, String value) {
        put(name, new ArrayList<>(List.of(value)));
    }
    public void add(String name, String value) {
        computeIfAbsent(name, k -> new ArrayList<>()).add(value);
    }
    public String getFirst(String name) {
        for (var entry : entrySet()) if (entry.getKey().equalsIgnoreCase(name) && !entry.getValue().isEmpty()) return entry.getValue().get(0);
        return null;
    }
}
