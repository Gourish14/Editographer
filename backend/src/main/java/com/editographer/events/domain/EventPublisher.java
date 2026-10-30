package com.editographer.events.domain;

import java.util.UUID;

/** Port for pushing live events. Spec: specs/07-api-and-data.md */
public interface EventPublisher {

  /** Sends an event to everyone listening on the stream. Nobody listening is not an error. */
  void publish(UUID streamId, StreamEvent event);
}
