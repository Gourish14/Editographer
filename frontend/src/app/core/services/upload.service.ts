import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { Upload } from 'tus-js-client';

const CHUNK_BYTES = 64 * 1024 * 1024;
const RETRY_DELAYS_MS = [0, 1000, 3000, 5000, 10000];

/** Resumable uploads, needed for 16 GB .OSV files. Emits percent complete. */
@Injectable({ providedIn: 'root' })
export class UploadService {
  upload(projectId: string, file: File): Observable<number> {
    return new Observable((subscriber) => {
      const upload = new Upload(file, {
        endpoint: '/api/uploads',
        chunkSize: CHUNK_BYTES,
        retryDelays: RETRY_DELAYS_MS,
        metadata: { projectId, filename: file.name },
        onProgress: (sent, total) => subscriber.next(Math.round((sent / total) * 100)),
        onError: (error) => subscriber.error(error),
        onSuccess: () => subscriber.complete(),
      });
      void upload.findPreviousUploads().then((previous) => {
        if (previous.length > 0) {
          upload.resumeFromPreviousUpload(previous[0]);
        }
        upload.start();
      });
      return () => void upload.abort();
    });
  }
}
