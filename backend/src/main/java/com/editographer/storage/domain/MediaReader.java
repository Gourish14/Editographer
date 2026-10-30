package com.editographer.storage.domain;

import java.io.IOException;
import java.io.InputStream;

/** Port that reads media files. */
public interface MediaReader {

  /** Opens a stored file. Throws java.nio.file.NoSuchFileException when it is missing. */
  InputStream open(MediaPath path) throws IOException;

  /** Size in bytes. Throws java.nio.file.NoSuchFileException when the file is missing. */
  long size(MediaPath path) throws IOException;
}
