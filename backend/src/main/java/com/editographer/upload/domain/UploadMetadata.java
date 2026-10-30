package com.editographer.upload.domain;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * The tus Upload-Metadata header: comma-separated "key base64value" pairs. Spec:
 * specs/07-api-and-data.md (metadata { projectId, filename })
 */
public record UploadMetadata(UUID projectId, String filename) {

  private static final Pattern PAIR_SEPARATOR = Pattern.compile(",");
  private static final Pattern KEY_VALUE_SEPARATOR = Pattern.compile("\\s+");
  private static final String PROJECT_ID_KEY = "projectId";
  private static final String FILENAME_KEY = "filename";
  private static final int KEY_AND_VALUE = 2;

  /** Reads the header, or returns empty when projectId or filename is missing or malformed. */
  public static Optional<UploadMetadata> parse(String header) {
    if (header == null) {
      return Optional.empty();
    }
    Map<String, String> values = new HashMap<>();
    for (String pair : PAIR_SEPARATOR.split(header)) {
      String[] parts = KEY_VALUE_SEPARATOR.split(pair.strip());
      if (parts.length == KEY_AND_VALUE) {
        values.put(parts[0], parts[1]);
      }
    }
    try {
      UUID projectId = UUID.fromString(decode(values.getOrDefault(PROJECT_ID_KEY, "")));
      String filename = safeFilename(decode(values.getOrDefault(FILENAME_KEY, "")));
      return filename.isBlank()
          ? Optional.empty()
          : Optional.of(new UploadMetadata(projectId, filename));
    } catch (IllegalArgumentException exception) {
      return Optional.empty();
    }
  }

  private static String decode(String base64) {
    return new String(Base64.getDecoder().decode(base64), StandardCharsets.UTF_8);
  }

  /** Browsers can send a full path; only the last part is the name. */
  private static String safeFilename(String filename) {
    int slash = Math.max(filename.lastIndexOf('/'), filename.lastIndexOf('\\'));
    return filename.substring(slash + 1);
  }
}
