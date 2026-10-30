package com.editographer.upload;

import static org.assertj.core.api.Assertions.assertThat;

import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.project.domain.Project;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import com.editographer.storage.domain.MediaLocator;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpRequest.BodyPublishers;
import java.net.http.HttpResponse;
import java.net.http.HttpResponse.BodyHandlers;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;

/** A real tus client conversation over HTTP, including a resume. [T-105] */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UploadFlowIntegrationTest {

  private static final byte[] CONTENT = "pretend this is a sixteen gigabyte clip".getBytes();
  private static final int FIRST_CHUNK = 10;
  private static final String TUS_VERSION = "1.0.0";

  @LocalServerPort private int port;
  @Autowired private ProjectRepository projects;
  @Autowired private AssetRepository assets;
  @Autowired private MediaLocator media;
  @Autowired private JdbcTemplate jdbc;

  private final HttpClient http =
      HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build();
  private ProjectId projectId;

  @BeforeEach
  void createProject() {
    projectId = projects.save(Project.create("uploads", Instant.now())).id();
  }

  private URI uri(String path) {
    return URI.create("http://127.0.0.1:" + port + path);
  }

  private static String b64(String value) {
    return Base64.getEncoder().encodeToString(value.getBytes(StandardCharsets.UTF_8));
  }

  private String metadata(String project, String filename) {
    return "projectId " + b64(project) + ",filename " + b64(filename);
  }

  private HttpResponse<String> create(String metadata) throws Exception {
    HttpRequest request =
        HttpRequest.newBuilder(uri("/api/uploads"))
            .header("Tus-Resumable", TUS_VERSION)
            .header("Upload-Length", String.valueOf(CONTENT.length))
            .header("Upload-Metadata", metadata)
            .POST(BodyPublishers.noBody())
            .build();
    return http.send(request, BodyHandlers.ofString());
  }

  private HttpResponse<String> patch(URI location, int offset, byte[] chunk) throws Exception {
    HttpRequest request =
        HttpRequest.newBuilder(location)
            .header("Tus-Resumable", TUS_VERSION)
            .header("Upload-Offset", String.valueOf(offset))
            .header("Content-Type", "application/offset+octet-stream")
            .method("PATCH", BodyPublishers.ofByteArray(chunk))
            .build();
    return http.send(request, BodyHandlers.ofString());
  }

  private long serverOffset(URI location) throws Exception {
    HttpRequest request =
        HttpRequest.newBuilder(location)
            .header("Tus-Resumable", TUS_VERSION)
            .method("HEAD", BodyPublishers.noBody())
            .build();
    HttpResponse<Void> response = http.send(request, BodyHandlers.discarding());
    return Long.parseLong(response.headers().firstValue("Upload-Offset").orElseThrow());
  }

  private URI startUpload(String filename) throws Exception {
    HttpResponse<String> created = create(metadata(projectId.value().toString(), filename));
    assertThat(created.statusCode()).isEqualTo(201);
    return uri("").resolve(created.headers().firstValue("Location").orElseThrow());
  }

  @Test
  void anInterruptedUploadResumesAndBecomesAPendingAssetWithAQueuedJob() throws Exception {
    URI location = startUpload("Goa Clip.MP4");

    assertThat(patch(location, 0, Arrays.copyOf(CONTENT, FIRST_CHUNK)).statusCode()).isEqualTo(204);
    assertThat(assets.findByProject(projectId)).isEmpty();

    long resumeFrom = serverOffset(location);
    assertThat(resumeFrom).isEqualTo(FIRST_CHUNK);
    byte[] rest = Arrays.copyOfRange(CONTENT, FIRST_CHUNK, CONTENT.length);
    assertThat(patch(location, (int) resumeFrom, rest).statusCode()).isEqualTo(204);

    List<Asset> stored = assets.findByProject(projectId);
    assertThat(stored).hasSize(1);
    Asset asset = stored.getFirst();
    assertThat(asset.filename()).isEqualTo("Goa Clip.MP4");
    assertThat(asset.sizeBytes()).isEqualTo(CONTENT.length);
    assertThat(asset.path().value())
        .startsWith("uploads/" + projectId.value() + "/")
        .endsWith(".mp4");
    assertThat(Files.readAllBytes(media.locate(asset.path()))).isEqualTo(CONTENT);
    assertThat(
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM job WHERE kind = 'ANALYZE' AND status = 'QUEUED'"
                    + " AND ref_id = ?",
                Integer.class,
                asset.id().value()))
        .isEqualTo(1);
  }

  @Test
  void aFinishedUploadLeavesNothingInTheTusFolder() throws Exception {
    URI location = startUpload("clip.mp4");

    patch(location, 0, CONTENT);

    HttpRequest head =
        HttpRequest.newBuilder(location)
            .header("Tus-Resumable", TUS_VERSION)
            .method("HEAD", BodyPublishers.noBody())
            .build();
    assertThat(http.send(head, BodyHandlers.discarding()).statusCode()).isEqualTo(404);
  }

  @Test
  void anUnsupportedFileIsRefusedBeforeUploading() throws Exception {
    HttpResponse<String> response = create(metadata(projectId.value().toString(), "virus.exe"));

    assertThat(response.statusCode()).isEqualTo(415);
    assertThat(response.body()).contains("ASSET_UNSUPPORTED");
  }

  @Test
  void anUnknownProjectIsRefusedBeforeUploading() throws Exception {
    HttpResponse<String> response =
        create(metadata(ProjectId.newId().value().toString(), "clip.mp4"));

    assertThat(response.statusCode()).isEqualTo(404);
    assertThat(response.body()).contains("PROJECT_NOT_FOUND");
  }

  @Test
  void missingMetadataIsRefused() throws IOException, InterruptedException, Exception {
    HttpResponse<String> response = create("nonsense");

    assertThat(response.statusCode()).isEqualTo(400);
    assertThat(response.body()).contains("UPLOAD_FAILED");
  }
}
