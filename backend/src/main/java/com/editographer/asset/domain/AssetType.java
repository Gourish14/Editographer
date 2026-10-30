package com.editographer.asset.domain;

import java.util.Arrays;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;

/** Kind of asset, decided by file extension. Spec: specs/00-overview.md#inputs */
public enum AssetType {
  VIDEO(Set.of("mp4", "mov", "osv", "lrf")),
  PHOTO(Set.of("jpg", "jpeg", "png", "heic", "dng")),
  MUSIC(Set.of("mp3", "wav", "m4a", "flac"));

  private final Set<String> extensions;

  AssetType(Set<String> extensions) {
    this.extensions = extensions;
  }

  /** The type for a filename, or empty when the extension is not supported. */
  public static Optional<AssetType> fromFilename(String filename) {
    String extension = extensionOf(filename);
    return Arrays.stream(values()).filter(type -> type.extensions.contains(extension)).findFirst();
  }

  /** Lower-case extension without the dot, or an empty string when there is none. */
  public static String extensionOf(String filename) {
    int dot = filename.lastIndexOf('.');
    return dot < 0 ? "" : filename.substring(dot + 1).toLowerCase(Locale.ROOT);
  }
}
