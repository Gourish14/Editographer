package com.editographer.storage.domain;

import java.util.Objects;
import java.util.regex.Pattern;

/**
 * A path inside the media folder, always relative and with forward slashes. Spec:
 * specs/02-architecture.md#storage-replaces-minio
 */
public record MediaPath(String value) {

  private static final Pattern SEPARATOR = Pattern.compile("/");

  public MediaPath {
    Objects.requireNonNull(value, "value");
    if (value.isBlank() || value.startsWith("/") || value.contains("\\") || value.contains(":")) {
      throw new IllegalArgumentException("Not a relative media path: " + value);
    }
    for (String segment : SEPARATOR.split(value, -1)) {
      if (segment.isEmpty() || ".".equals(segment) || "..".equals(segment)) {
        throw new IllegalArgumentException("Not a relative media path: " + value);
      }
    }
  }
}
