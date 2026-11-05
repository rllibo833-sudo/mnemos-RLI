package org.beyondlight;

import java.nio.file.Path;

/** Keeps desktop-relative storage and lets Android point every repository into app-private files. */
public final class DataPaths {
    private DataPaths() {}

    public static Path path(String... parts) {
        String root = System.getProperty("beyondlight.dataDir");
        Path result = root == null || root.isBlank() ? Path.of(parts[0]) : Path.of(root);
        for (int i = root == null || root.isBlank() ? 1 : 0; i < parts.length; i++) result = result.resolve(parts[i]);
        return result;
    }
}
