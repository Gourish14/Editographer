package com.editographer.storage.infrastructure;

import java.nio.file.Path;

class LocalStorageAdapterTest extends MediaStorageContractTest<LocalStorageAdapter> {

  @Override
  LocalStorageAdapter createStorage(Path workDir) {
    return new LocalStorageAdapter(workDir);
  }
}
