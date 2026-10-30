package com.editographer.storage.infrastructure;

import com.editographer.storage.domain.MediaLocator;
import com.editographer.storage.domain.MediaPath;
import com.editographer.storage.domain.MediaReader;
import com.editographer.storage.domain.MediaWriter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Objects;

/** Stores media in the local media folder. Spec: specs/02-architecture.md#storage-replaces-minio */
public final class LocalStorageAdapter implements MediaLocator, MediaReader, MediaWriter {

  private final Path root;

  public LocalStorageAdapter(Path root) {
    this.root = root.toAbsolutePath().normalize();
  }

  @Override
  public Path locate(MediaPath path) {
    return root.resolve(path.value()).normalize();
  }

  @Override
  public boolean exists(MediaPath path) {
    return Files.exists(locate(path));
  }

  @Override
  public InputStream open(MediaPath path) throws IOException {
    return Files.newInputStream(locate(path));
  }

  @Override
  public long size(MediaPath path) throws IOException {
    return Files.size(locate(path));
  }

  @Override
  public void moveIn(Path source, MediaPath target) throws IOException {
    Path destination = locate(target);
    Files.createDirectories(Objects.requireNonNull(destination.getParent()));
    Files.move(source, destination, StandardCopyOption.REPLACE_EXISTING);
  }

  @Override
  public void delete(MediaPath path) throws IOException {
    Path target = locate(path);
    if (Files.exists(target)) {
      Files.walkFileTree(target, new DeletingVisitor());
    }
  }

  private static final class DeletingVisitor extends SimpleFileVisitor<Path> {

    @Override
    public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) throws IOException {
      Files.delete(file);
      return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult postVisitDirectory(Path directory, IOException failure)
        throws IOException {
      if (failure != null) {
        throw failure;
      }
      Files.delete(directory);
      return FileVisitResult.CONTINUE;
    }
  }
}
