package com.editographer.events.application;

import com.editographer.events.domain.StreamEvent;
import java.util.Optional;
import java.util.UUID;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** Opens live streams for browsers. */
public interface EventStreams {

  /**
   * Starts listening. The optional first event tells a late listener what it missed, for example
   * that the render has already finished.
   */
  SseEmitter open(UUID streamId, Optional<StreamEvent> firstEvent);
}
