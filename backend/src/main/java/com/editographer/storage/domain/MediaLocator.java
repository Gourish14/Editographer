package com.editographer.storage.domain;

import java.nio.file.Path;

/** Port that finds media files on disk. */
public interface MediaLocator {

  Path locate(MediaPath path);

  boolean exists(MediaPath path);
}
