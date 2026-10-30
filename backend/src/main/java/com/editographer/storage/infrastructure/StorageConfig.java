package com.editographer.storage.infrastructure;

import com.editographer.common.config.AppProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Chooses the storage implementation. Spec: specs/02-architecture.md#storage-replaces-minio */
@Configuration
public class StorageConfig {

  @Bean
  public LocalStorageAdapter localStorageAdapter(AppProperties properties) {
    return new LocalStorageAdapter(properties.mediaDir());
  }
}
