package com.editographer.render.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.editographer.project.domain.ProjectId;
import com.editographer.storage.domain.MediaPath;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.EnumSource;
import org.junit.jupiter.params.provider.ValueSource;

class RenderTest {

  private static final Instant NOW = Instant.parse("2026-10-30T10:00:00Z");
  private static final RenderSettings SETTINGS =
      new RenderSettings("9:16", "4K", 30, "auto", "fast", null, null, false, 7L, null, null);

  private final Render render = Render.queued(ProjectId.newId(), SETTINGS, NOW);

  @Test
  void aFollowPointMustSitInsideTheFrame() {
    assertThatThrownBy(() -> new RenderSettings.FollowPoint(1.2, 0.5, 0, null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new RenderSettings.FollowPoint(0.5, 0.5, -1, null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void aNewRenderIsQueuedAtZero() {
    assertThat(render.state().status()).isEqualTo(RenderStatus.QUEUED);
    assertThat(render.state().progress()).isZero();
    assertThat(render.isFinished()).isFalse();
  }

  @Test
  void aStageNamingAStatusMovesTheRenderToIt() {
    Render moved = render.progressed("COMPOSING", 40);

    assertThat(moved.state().status()).isEqualTo(RenderStatus.COMPOSING);
    assertThat(moved.state().stage()).isEqualTo("COMPOSING");
    assertThat(moved.state().progress()).isEqualTo(40);
  }

  @Test
  void anUnknownStageKeepsTheStatus() {
    Render moved = render.progressed("COMPOSING", 40).progressed("DELIVER", 98);

    assertThat(moved.state().status()).isEqualTo(RenderStatus.COMPOSING);
    assertThat(moved.state().stage()).isEqualTo("DELIVER");
  }

  @Test
  void aStageCannotClaimTheRenderFinished() {
    assertThat(render.progressed("DONE", 50).isFinished()).isFalse();
  }

  @Test
  void doneStoresOutputPlanAndCompletion() {
    MediaPath output = new MediaPath("renders/r/final.mp4");

    Render done = render.done(output, "{}", NOW);

    assertThat(done.state().status()).isEqualTo(RenderStatus.DONE);
    assertThat(done.state().progress()).isEqualTo(100);
    assertThat(done.state().outputPath()).isEqualTo(output);
    assertThat(done.state().editPlan()).isEqualTo("{}");
    assertThat(done.state().finishedAt()).isEqualTo(NOW);
    assertThat(done.isFinished()).isTrue();
  }

  @Test
  void failedKeepsTheErrorAndCancelledFinishes() {
    assertThat(render.failed("boom", NOW).state().error()).isEqualTo("boom");
    assertThat(render.cancelled(NOW).state().status()).isEqualTo(RenderStatus.CANCELLED);
    assertThat(render.cancelled(NOW).isFinished()).isTrue();
  }

  @Test
  void previewIsKeptWhileTheRenderContinues() {
    MediaPath preview = new MediaPath("renders/r/preview.mp4");

    Render withPreview = render.progressed("COMPOSING", 30).withPreview(preview);

    assertThat(withPreview.state().previewPath()).isEqualTo(preview);
    assertThat(withPreview.state().status()).isEqualTo(RenderStatus.COMPOSING);
  }

  @Test
  void folderIsPerRender() {
    assertThat(Render.folder(render.id()).value()).isEqualTo("renders/" + render.id().value());
  }

  @Test
  void regeneratingChangesOnlyTheSeed() {
    assertThat(SETTINGS.withSeed(8L).seed()).isEqualTo(8L);
    assertThat(SETTINGS.withSeed(8L).withSeed(7L)).isEqualTo(SETTINGS);
  }

  @ParameterizedTest
  @EnumSource(
      value = RenderStatus.class,
      names = {"DONE", "FAILED", "CANCELLED"})
  void finishedStatuses(RenderStatus status) {
    assertThat(status.isFinished()).isTrue();
  }

  @ParameterizedTest
  @CsvSource({
    "1:2,4K,30,fast",
    "9:16,2K,30,fast",
    "9:16,4K,25,fast",
    "9:16,4K,30,turbo",
  })
  void rejectsValuesOutsideTheSpec(String ratio, String quality, int fps, String mode) {
    assertThatThrownBy(
            () ->
                new RenderSettings(
                    ratio, quality, fps, "auto", mode, null, null, false, 1L, null, null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @ParameterizedTest
  @ValueSource(strings = {"16:9", "9:16", "1:1", "4:5", "4:3", "21:9"})
  void acceptsEveryRatioFromTheSpec(String ratio) {
    assertThat(
            new RenderSettings(ratio, "8K", 60, "auto", "max", 30, "p", true, 1L, null, null)
                .ratio())
        .isEqualTo(ratio);
  }

  @ParameterizedTest
  @ValueSource(ints = {0, -5})
  void rejectsANonPositiveLength(int length) {
    assertThatThrownBy(
            () ->
                new RenderSettings(
                    "9:16", "4K", 30, "auto", "fast", length, null, false, 1L, null, null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @ParameterizedTest
  @ValueSource(ints = {-1, 101})
  void rejectsProgressOutsideZeroToAHundred(int percent) {
    assertThatThrownBy(() -> render.progressed("COMPOSING", percent))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
