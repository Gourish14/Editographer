package com.editographer.events.infrastructure;

import com.editographer.events.application.EventStreams;
import com.editographer.events.domain.EventPublisher;
import com.editographer.events.domain.StreamEvent;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** Server-Sent Events over Spring's SseEmitter. A render can run for an hour, so no timeout. */
@Component
final class SseEventPublisher implements EventPublisher, EventStreams {

  private static final long NO_TIMEOUT = 0L;

  private final Map<UUID, List<SseEmitter>> streams = new ConcurrentHashMap<>();

  @Override
  public SseEmitter open(UUID streamId, Optional<StreamEvent> firstEvent) {
    SseEmitter emitter = new SseEmitter(NO_TIMEOUT);
    if (firstEvent.isPresent() && firstEvent.get().last()) {
      send(emitter, firstEvent.get());
      emitter.complete();
      return emitter;
    }
    Runnable forget = () -> forget(streamId, emitter);
    emitter.onCompletion(forget);
    emitter.onTimeout(forget);
    emitter.onError(failure -> forget.run());
    streams.computeIfAbsent(streamId, id -> new CopyOnWriteArrayList<>()).add(emitter);
    firstEvent.ifPresent(event -> send(emitter, event));
    return emitter;
  }

  @Override
  public void publish(UUID streamId, StreamEvent event) {
    for (SseEmitter emitter : streams.getOrDefault(streamId, List.of())) {
      if (send(emitter, event)) {
        if (event.last()) {
          emitter.complete();
        }
      } else {
        forget(streamId, emitter);
      }
    }
  }

  private static boolean send(SseEmitter emitter, StreamEvent event) {
    try {
      emitter.send(SseEmitter.event().name(event.name()).data(event.data()));
      return true;
    } catch (IOException | IllegalStateException exception) {
      return false;
    }
  }

  private void forget(UUID streamId, SseEmitter emitter) {
    streams.computeIfPresent(
        streamId,
        (id, emitters) -> {
          emitters.remove(emitter);
          return emitters.isEmpty() ? null : emitters;
        });
  }
}
