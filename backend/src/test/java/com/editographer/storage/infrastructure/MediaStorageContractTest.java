package com.editographer.storage.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.editographer.storage.domain.MediaLocator;
import com.editographer.storage.domain.MediaPath;
import com.editographer.storage.domain.MediaReader;
import com.editographer.storage.domain.MediaWriter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** Every storage implementation must pass this. Spec: specs/11-coding-standards.md#1 */
abstract class MediaStorageContractTest<T extends MediaLocator & MediaReader & MediaWriter> {

  private static final MediaPath TARGET = new MediaPath("uploads/p/a.mp4");

  @TempDir Path temp;
  private T storage;
  private Path source;

  abstract T createStorage(Path workDir);

  @BeforeEach
  void setUp() throws IOException {
    storage = createStorage(temp.resolve("media"));
    source = Files.writeString(temp.resolve("incoming"), "clip");
  }

  @Test
  void movedFileCanBeReadBack() throws IOException {
    storage.moveIn(source, TARGET);

    assertThat(storage.exists(TARGET)).isTrue();
    assertThat(storage.size(TARGET)).isEqualTo(4L);
    try (InputStream stream = storage.open(TARGET)) {
      assertThat(new String(stream.readAllBytes(), StandardCharsets.UTF_8)).isEqualTo("clip");
    }
    assertThat(source).doesNotExist();
  }

  @Test
  void moveReplacesAnExistingFile() throws IOException {
    storage.moveIn(source, TARGET);
    Path newer = Files.writeString(temp.resolve("newer"), "longer clip");

    storage.moveIn(newer, TARGET);

    assertThat(storage.size(TARGET)).isEqualTo(11L);
  }

  @Test
  void missingFileReportsNoSuchFile() {
    assertThat(storage.exists(TARGET)).isFalse();
    assertThatThrownBy(() -> storage.open(TARGET)).isInstanceOf(NoSuchFileException.class);
    assertThatThrownBy(() -> storage.size(TARGET)).isInstanceOf(NoSuchFileException.class);
  }

  @Test
  void deleteRemovesAWholeFolder() throws IOException {
    storage.moveIn(source, TARGET);

    storage.delete(new MediaPath("uploads/p"));

    assertThat(storage.exists(TARGET)).isFalse();
    assertThat(storage.exists(new MediaPath("uploads/p"))).isFalse();
  }

  @Test
  void deletingSomethingMissingDoesNothing() throws IOException {
    storage.delete(new MediaPath("uploads/nothing"));

    assertThat(storage.exists(new MediaPath("uploads/nothing"))).isFalse();
  }
}
