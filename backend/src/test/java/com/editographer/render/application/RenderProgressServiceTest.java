package com.editographer.render.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentCaptor.forClass;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.editographer.events.domain.EventPublisher;
import com.editographer.events.domain.StreamEvent;
import com.editographer.project.domain.ProjectId;
import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderRepository;
import com.editographer.render.domain.RenderSettings;
import com.editographer.render.domain.RenderStatus;
import com.editographer.storage.domain.MediaPath;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class RenderProgressServiceTest {

  private static final Instant NOW = Instant.parse("2026-10-30T10:00:00Z");
  private static final MediaPath OUTPUT = new MediaPath("renders/r/final.mp4");

  private final RenderRepository renders = mock(RenderRepository.class);
  private final EventPublisher events = mock(EventPublisher.class);
  private final RenderProgressService service =
      new RenderProgressService(renders, events, Clock.fixed(NOW, ZoneOffset.UTC));
  private final Render render =
      Render.queued(
          ProjectId.newId(),
          new RenderSettings("9:16", "4K", 30, "auto", "fast", null, null, false, 1L),
          NOW);

  private void stored(Render value) {
    when(renders.findById(render.id())).thenReturn(Optional.of(value));
  }

  private Render saved() {
    ArgumentCaptor<Render> captor = forClass(Render.class);
    verify(renders).save(captor.capture());
    return captor.getValue();
  }

  private StreamEvent published() {
    ArgumentCaptor<StreamEvent> captor = forClass(StreamEvent.class);
    verify(events).publish(eq(render.id().value()), captor.capture());
    return captor.getValue();
  }

  @Test
  void progressIsStoredAndPushed() {
    stored(render);

    service.progress(render.id(), "COMPOSING", 40, "segment 3");

    assertThat(saved().state().status()).isEqualTo(RenderStatus.COMPOSING);
    StreamEvent event = published();
    assertThat(event.name()).isEqualTo("progress");
    assertThat(event.last()).isFalse();
    assertThat(event.data())
        .isEqualTo(Map.of("stage", "COMPOSING", "percent", 40, "message", "segment 3"));
  }

  @Test
  void previewReadyIsStoredAndPushed() {
    stored(render);
    MediaPath preview = new MediaPath("renders/r/preview.mp4");

    service.previewReady(render.id(), preview);

    assertThat(saved().state().previewPath()).isEqualTo(preview);
    assertThat(published().name()).isEqualTo("preview-ready");
  }

  @Test
  void completionClosesTheStream() {
    stored(render);

    service.completed(render.id(), OUTPUT, "{}");

    assertThat(saved().state().status()).isEqualTo(RenderStatus.DONE);
    assertThat(published().last()).isTrue();
  }

  @Test
  void failureClosesTheStreamWithTheError() {
    stored(render);

    service.failed(render.id(), "GPU_OUT_OF_MEMORY");

    assertThat(saved().state().error()).isEqualTo("GPU_OUT_OF_MEMORY");
    StreamEvent event = published();
    assertThat(event.name()).isEqualTo("failed");
    assertThat(event.last()).isTrue();
  }

  @Test
  void reportsAfterACancelAreIgnored() {
    stored(render.cancelled(NOW));

    service.progress(render.id(), "COMPOSING", 40, null);
    service.completed(render.id(), OUTPUT, "{}");
    service.failed(render.id(), "stopped");

    verify(renders, never()).save(any());
    verify(events, never()).publish(any(), any());
  }

  @Test
  void reportsForADeletedRenderAreIgnored() {
    when(renders.findById(render.id())).thenReturn(Optional.empty());

    service.progress(render.id(), "COMPOSING", 40, null);

    verify(renders, never()).save(any());
  }
}
