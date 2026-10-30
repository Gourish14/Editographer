package com.editographer.upload.application;

import com.editographer.upload.domain.UploadMetadata;
import java.nio.file.Path;

/** A fully received upload that is ready to become an asset. */
public record CompletedUpload(
    String uploadUri, UploadMetadata metadata, Path file, long sizeBytes) {}
