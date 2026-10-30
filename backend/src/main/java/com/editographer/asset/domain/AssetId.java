package com.editographer.asset.domain;

import java.util.Objects;
import java.util.UUID;

/** Identity of an uploaded asset. */
public record AssetId(UUID value) {

  public AssetId {
    Objects.requireNonNull(value, "value");
  }

  public static AssetId newId() {
    return new AssetId(UUID.randomUUID());
  }
}
