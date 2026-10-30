package com.editographer.storage.domain;

import java.io.IOException;
import java.nio.file.Path;

/** Port that changes media files. */
public interface MediaWriter {

  /** Moves a finished file into storage, replacing any file already at the target. */
  void moveIn(Path source, MediaPath target) throws IOException;

  /** Removes a file or a whole folder. Does nothing when the path does not exist. */
  void delete(MediaPath path) throws IOException;
}
