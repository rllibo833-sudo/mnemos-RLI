package org.beyondlight;

import java.util.*;

/** Provenance metadata for a source used or discovered during a research run. */
public record SourceRecord(
        String id,
        String title,
        String sourceType,
        String provider,
        String author,
        String publicationDate,
        String doi,
        String url,
        String license,
        String verificationStatus,
        Map<String, Object> metadata) {

    public SourceRecord {
        id = text(id);
        title = text(title);
        sourceType = text(sourceType).isEmpty() ? "unspecified" : text(sourceType);
        provider = text(provider);
        author = text(author);
        publicationDate = text(publicationDate);
        doi = text(doi);
        url = text(url);
        license = text(license);
        verificationStatus = text(verificationStatus).isEmpty() ? "NOT_ASSESSED" : text(verificationStatus);
        metadata = metadata == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(metadata));
    }

    public static SourceRecord fromMap(Map<String, Object> value) {
        String url = first(value, "url", "recordUrl", "sourceUrl");
        String doi = first(value, "doi", "DOI");
        String id = first(value, "id", "recordId", "identifier");
        if (id.isEmpty()) id = !doi.isEmpty() ? doi : !url.isEmpty() ? url : UUID.randomUUID().toString();
        Map<String, Object> metadata = new LinkedHashMap<>(value);
        return new SourceRecord(id, first(value, "title", "name"), first(value, "sourceType", "type"),
                first(value, "provider", "repository", "source"), first(value, "author", "authors"),
                first(value, "publicationDate", "year", "date"), doi, url,
                first(value, "license", "licenseId"), first(value, "verificationStatus", "status"), metadata);
    }

    public Map<String, Object> toMap() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", id); out.put("title", title); out.put("sourceType", sourceType);
        out.put("provider", provider); out.put("author", author); out.put("publicationDate", publicationDate);
        out.put("doi", doi); out.put("url", url); out.put("license", license);
        out.put("verificationStatus", verificationStatus); out.put("metadata", metadata);
        return out;
    }

    private static String first(Map<String, Object> m, String... keys) {
        for (String key : keys) {
            Object value = m.get(key);
            if (value != null && !value.toString().isBlank()) return value.toString().trim();
        }
        return "";
    }
    private static String text(String value) { return Objects.toString(value, "").trim(); }
}
