package com.editographer.events.domain;

import java.util.Objects;

/** One message on a live stream. The last message closes the stream. */
public record StreamEvent(String name, Object data, boolean last) {

  public StreamEvent {
    Objects.requireNonNull(name, "name");
    Objects.requireNonNull(data, "data");
  }
}
