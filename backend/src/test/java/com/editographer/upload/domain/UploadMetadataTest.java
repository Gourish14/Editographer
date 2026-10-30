package com.editographer.upload.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;

class UploadMetadataTest {

  private static final UUID PROJECT = UUID.fromString("00000000-0000-0000-0000-000000000001");

  private static String encoded(String value) {
    return Base64.getEncoder().encodeToString(value.getBytes(StandardCharsets.UTF_8));
  }

  private static String header(String filename) {
    return "projectId " + encoded(PROJECT.toString()) + ",filename " + encoded(filename);
  }

  @Test
  void readsProjectAndFilename() {
    assertThat(UploadMetadata.parse(header("clip.mp4")))
        .contains(new UploadMetadata(PROJECT, "clip.mp4"));
  }

  @Test
  void keepsNonAsciiFilenames() {
    assertThat(UploadMetadata.parse(header("गोवा.mp4")).orElseThrow().filename())
        .isEqualTo("गोवा.mp4");
  }

  @Test
  void toleratesSpacesAndExtraPairs() {
    String value = "filetype dmlkZW8=, " + header("clip.mp4").replace(",", " , ");

    assertThat(UploadMetadata.parse(value)).isPresent();
  }

  @Test
  void dropsAnyPathFromTheFilename() {
    assertThat(UploadMetadata.parse(header("..\\..\\evil/../clip.mp4")).orElseThrow().filename())
        .isEqualTo("clip.mp4");
  }

  @ParameterizedTest
  @NullSource
  @ValueSource(strings = {"", "garbage", "projectId notbase64!,filename notbase64!"})
  void rejectsHeadersWithoutUsableValues(String header) {
    assertThat(UploadMetadata.parse(header)).isEmpty();
  }

  @Test
  void rejectsAProjectIdThatIsNotAUuid() {
    String value = "projectId " + encoded("nope") + ",filename " + encoded("clip.mp4");

    assertThat(UploadMetadata.parse(value)).isEmpty();
  }

  @Test
  void rejectsAFilenameThatIsOnlyAPath() {
    assertThat(UploadMetadata.parse(header("folder/"))).isEmpty();
  }
}
