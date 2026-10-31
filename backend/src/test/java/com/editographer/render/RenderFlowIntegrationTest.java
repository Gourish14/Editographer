package com.editographer.render;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.asset.domain.AssetType;
import com.editographer.job.application.JobDispatcher;
import com.editographer.project.domain.Project;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import com.editographer.storage.domain.MediaLocator;
import com.editographer.storage.domain.MediaPath;
import com.editographer.worker.domain.RenderJobRequest;
import com.editographer.worker.domain.WorkerClient;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpRequest.BodyPublishers;
import java.net.http.HttpResponse;
import java.net.http.HttpResponse.BodyHandlers;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

/** The whole render flow over real HTTP, with only the worker faked. [T-107] */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RenderFlowIntegrationTest {

  private static final Pattern ID = Pattern.compile("\"id\":\"([0-9a-f-]{36})\"");
  private static final String TOKEN = "test-token";

  @LocalServerPort private int port;
  @Autowired private ProjectRepository projects;
  @Autowired private AssetRepository assets;
  @Autowired private MediaLocator media;
  @Autowired private JobDispatcher dispatcher;
  @Autowired private JdbcTemplate jdbc;
  @MockitoBean private WorkerClient worker;

  private final HttpClient http =
      HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build();
  private ProjectId projectId;

  @BeforeEach
  void aProjectWithMusicAndAClip() {
    jdbc.update("DELETE FROM job");
    projectId = projects.save(Project.create("flow", Instant.now())).id();
    assets.save(Asset.uploaded(projectId, AssetType.MUSIC, "song.mp3", 1L, Instant.now()));
    assets.save(Asset.uploaded(projectId, AssetType.VIDEO, "clip.mp4", 1L, Instant.now()));
  }

  private URI uri(String path) {
    return URI.create("http://127.0.0.1:" + port + path);
  }

  private HttpResponse<String> get(String path) throws Exception {
    return http.send(HttpRequest.newBuilder(uri(path)).GET().build(), BodyHandlers.ofString());
  }

  private HttpResponse<String> post(String path, String body) throws Exception {
    return http.send(
        HttpRequest.newBuilder(uri(path))
            .header("Content-Type", "application/json")
            .POST(BodyPublishers.ofString(body))
            .build(),
        BodyHandlers.ofString());
  }

  private void report(String path, String body) throws Exception {
    HttpResponse<String> response =
        http.send(
            HttpRequest.newBuilder(uri(path))
                .header("Content-Type", "application/json")
                .header("X-Worker-Token", TOKEN)
                .POST(BodyPublishers.ofString(body))
                .build(),
            BodyHandlers.ofString());
    assertThat(response.statusCode()).as(path + " " + response.body()).isEqualTo(204);
  }

  private String startRender() throws Exception {
    HttpResponse<String> created =
        post(
            "/api/projects/" + projectId.value() + "/renders",
            "{\"ratio\":\"16:9\",\"style\":\"velocity\"}");
    assertThat(created.statusCode()).as(created.body()).isEqualTo(201);
    Matcher id = ID.matcher(created.body());
    assertThat(id.find()).isTrue();
    return id.group(1);
  }

  private String dispatchAndGetJobId() {
    when(worker.isIdle()).thenReturn(true);
    dispatcher.dispatchNext();
    ArgumentCaptor<RenderJobRequest> sent = ArgumentCaptor.forClass(RenderJobRequest.class);
    verify(worker).submitRender(sent.capture());
    return sent.getValue().jobId().toString();
  }

  private CompletableFuture<List<String>> listenToEvents(String renderId) {
    return CompletableFuture.supplyAsync(
        () -> {
          List<String> names = new ArrayList<>();
          HttpRequest request =
              HttpRequest.newBuilder(uri("/api/renders/" + renderId + "/events")).GET().build();
          try (BufferedReader lines =
              new BufferedReader(
                  new InputStreamReader(
                      http.send(request, BodyHandlers.ofInputStream()).body(),
                      StandardCharsets.UTF_8))) {
            String line = lines.readLine();
            while (line != null) {
              if (line.startsWith("event:")) {
                names.add(line.substring("event:".length()).strip());
              }
              line = lines.readLine();
            }
          } catch (java.io.IOException | InterruptedException exception) {
            throw new IllegalStateException(exception);
          }
          return names;
        });
  }

  @Test
  void renderTonightWaitsForItsStartTimeAndKeepsTheFollowPoint() throws Exception {
    String start = Instant.now().plusSeconds(3600).toString();
    HttpResponse<String> created =
        post(
            "/api/projects/" + projectId.value() + "/renders",
            "{\"style\":\"velocity\",\"coolMode\":true,\"startAt\":\""
                + start
                + "\",\"followPoint\":{\"x\":0.25,\"y\":0.5,\"timeSec\":3.5}}");
    assertThat(created.statusCode()).as(created.body()).isEqualTo(201);
    assertThat(created.body())
        .contains("\"startAt\":\"" + start + "\"")
        .contains("\"followPoint\":{\"x\":0.25,\"y\":0.5,\"timeSec\":3.5}");

    when(worker.isIdle()).thenReturn(true);
    dispatcher.dispatchNext();

    verify(worker, never()).submitRender(any());
    assertThat(
            jdbc.queryForObject("SELECT COUNT(*) FROM job WHERE status = 'QUEUED'", Integer.class))
        .isEqualTo(1);
  }

  @Test
  void aFollowPointOutsideTheFrameIsRefused() throws Exception {
    HttpResponse<String> response =
        post(
            "/api/projects/" + projectId.value() + "/renders",
            "{\"followPoint\":{\"x\":2,\"y\":0.5,\"timeSec\":0}}");

    assertThat(response.statusCode()).isEqualTo(400);
  }

  @Test
  void aRenderRunsFromRequestToDownloadWithLiveEvents() throws Exception {
    String renderId = startRender();
    String jobId = dispatchAndGetJobId();
    assertThat(get("/api/renders/" + renderId).body()).contains("\"status\":\"QUEUED\"");

    report(
        "/internal/progress", "{\"jobId\":\"" + jobId + "\",\"stage\":\"PLANNING\",\"percent\":3}");
    CompletableFuture<List<String>> events = listenToEvents(renderId);
    TimeUnit.MILLISECONDS.sleep(300);

    report(
        "/internal/progress",
        "{\"jobId\":\"" + jobId + "\",\"stage\":\"COMPOSING\",\"percent\":40,\"message\":\"m\"}");
    String folder = "renders/" + renderId;
    Path preview = media.locate(new MediaPath(folder + "/preview.mp4"));
    Files.createDirectories(preview.getParent());
    Files.writeString(preview, "preview bytes");
    report(
        "/internal/preview-ready",
        "{\"jobId\":\"" + jobId + "\",\"path\":\"" + folder + "/preview.mp4\"}");
    Files.writeString(media.locate(new MediaPath(folder + "/final.mp4")), "0123456789");
    report(
        "/internal/complete",
        "{\"jobId\":\""
            + jobId
            + "\",\"status\":\"DONE\",\"outputPath\":\""
            + folder
            + "/final.mp4\",\"plan\":{\"version\":1,\"style\":\"velocity\"}}");

    assertThat(events.get(5, TimeUnit.SECONDS))
        .containsExactly("progress", "progress", "preview-ready", "done");

    String body = get("/api/renders/" + renderId).body();
    assertThat(body)
        .contains("\"status\":\"DONE\"")
        .contains("\"progress\":100")
        .contains("\"editPlan\":{\"version\":1,\"style\":\"velocity\"}")
        .contains("\"finalReady\":true");
    assertThat(get("/api/projects/" + projectId.value()).body()).contains(renderId);
    assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM job WHERE status = 'DONE'", Integer.class))
        .isEqualTo(1);

    HttpResponse<String> whole = get("/api/renders/" + renderId + "/download");
    assertThat(whole.statusCode()).isEqualTo(200);
    assertThat(whole.body()).isEqualTo("0123456789");
    assertThat(whole.headers().firstValue("Content-Type")).contains("video/mp4");
    assertThat(whole.headers().firstValue("Content-Disposition").orElseThrow())
        .contains("attachment");

    HttpResponse<String> seek =
        http.send(
            HttpRequest.newBuilder(uri("/api/renders/" + renderId + "/preview"))
                .header("Range", "bytes=8-12")
                .GET()
                .build(),
            BodyHandlers.ofString());
    assertThat(seek.statusCode()).isEqualTo(206);
    assertThat(seek.body()).isEqualTo("bytes");
    assertThat(seek.headers().firstValue("Content-Range")).contains("bytes 8-12/13");

    assertThat(listenToEvents(renderId).get(5, TimeUnit.SECONDS)).containsExactly("done");
  }

  private void ageRunningJob() {
    jdbc.update(
        "UPDATE job SET started_at = ? WHERE status = 'RUNNING'",
        java.sql.Timestamp.from(Instant.now().minusSeconds(3600)));
  }

  @Test
  void recoveryARestartedWorkerGetsTheLostJobAgainAndARepeatedCallbackIsHarmless()
      throws Exception {
    String renderId = startRender();
    String jobId = dispatchAndGetJobId();
    ageRunningJob();
    when(worker.status())
        .thenReturn(
            java.util.Optional.of(
                new com.editographer.worker.domain.WorkerStatus(false, null, null)));

    dispatcher.dispatchNext();

    verify(worker, org.mockito.Mockito.times(2)).submitRender(any());
    assertThat(
            jdbc.queryForObject(
                "SELECT attempts FROM job WHERE id = ?",
                Integer.class,
                java.util.UUID.fromString(jobId)))
        .isEqualTo(2);

    Files.createDirectories(media.locate(new MediaPath("renders/" + renderId + "/x")).getParent());
    Files.writeString(media.locate(new MediaPath("renders/" + renderId + "/final.mp4")), "bytes");
    String done =
        "{\"jobId\":\""
            + jobId
            + "\",\"status\":\"DONE\",\"outputPath\":\"renders/"
            + renderId
            + "/final.mp4\"}";
    report("/internal/complete", done);
    report("/internal/complete", done);

    assertThat(get("/api/renders/" + renderId).body()).contains("\"status\":\"DONE\"");
    assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM job WHERE status = 'DONE'", Integer.class))
        .isEqualTo(1);
  }

  @Test
  void recoveryAJobTheWorkerKeepsLosingFailsItsRenderInsteadOfWaitingForever() throws Exception {
    String renderId = startRender();
    when(worker.isIdle()).thenReturn(true);
    when(worker.status())
        .thenReturn(
            java.util.Optional.of(
                new com.editographer.worker.domain.WorkerStatus(false, null, null)));
    for (int attempt = 0; attempt < 3; attempt++) {
      dispatcher.dispatchNext();
      ageRunningJob();
    }

    dispatcher.dispatchNext();

    assertThat(get("/api/renders/" + renderId).body()).contains("\"status\":\"FAILED\"");
    assertThat(
            jdbc.queryForObject("SELECT COUNT(*) FROM job WHERE status = 'FAILED'", Integer.class))
        .isEqualTo(1);
  }

  @Test
  void aQueuedRenderCanBeCancelledAndIsThenNeverSent() throws Exception {
    String renderId = startRender();

    assertThat(post("/api/renders/" + renderId + "/cancel", "").body())
        .contains("\"status\":\"CANCELLED\"");
    assertThat(post("/api/renders/" + renderId + "/cancel", "").statusCode()).isEqualTo(409);

    when(worker.isIdle()).thenReturn(true);
    dispatcher.dispatchNext();
    org.mockito.Mockito.verify(worker, org.mockito.Mockito.never()).submitRender(any());
  }

  @Test
  void regenerateMakesASecondRender() throws Exception {
    String renderId = startRender();

    HttpResponse<String> version = post("/api/renders/" + renderId + "/regenerate", "");

    assertThat(version.statusCode()).isEqualTo(201);
    assertThat(version.body()).doesNotContain("\"id\":\"" + renderId);
  }

  @Test
  void invalidSettingsAreRefusedWithAReason() throws Exception {
    HttpResponse<String> response =
        post("/api/projects/" + projectId.value() + "/renders", "{\"ratio\":\"3:2\"}");

    assertThat(response.statusCode()).isEqualTo(400);
    assertThat(response.body()).contains("VALIDATION_FAILED").contains("ratio");
  }

  @Test
  void aPreviewBeforeItExistsIsAConflict() throws Exception {
    String renderId = startRender();

    HttpResponse<String> response = get("/api/renders/" + renderId + "/preview");

    assertThat(response.statusCode()).isEqualTo(409);
    assertThat(response.body()).contains("RENDER_NOT_READY");
  }

  @Test
  void allEightStylesAreListedWithTheirDefaults() throws Exception {
    String body = get("/api/styles").body();

    assertThat(body)
        .contains("\"id\":\"auto\"")
        .contains("\"id\":\"velocity\"")
        .contains("\"id\":\"sports\"")
        .contains("\"fxIntensity\":0.9");
  }

  @Test
  void systemStatusReportsADownWorkerInsteadOfFailing() throws Exception {
    HttpResponse<String> response = get("/api/system");

    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.body()).contains("\"workerOnline\":false");
  }
}
