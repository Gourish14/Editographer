package com.editographer.asset.application;

import com.editographer.asset.domain.AnalysisStatus;
import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetId;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.job.application.JobSender;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.worker.domain.AnalyzeJobRequest;
import com.editographer.worker.domain.WorkerClient;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** Sends analysis jobs. Spec: specs/07-api-and-data.md#job-flow step 2 */
@Component
public class AnalyzeJobSender implements JobSender {

  private final AssetRepository assets;
  private final WorkerClient worker;

  public AnalyzeJobSender(AssetRepository assets, WorkerClient worker) {
    this.assets = assets;
    this.worker = worker;
  }

  @Override
  public JobKind kind() {
    return JobKind.ANALYZE;
  }

  @Override
  public boolean send(Job job) {
    Optional<Asset> found = assets.findById(new AssetId(job.refId()));
    if (found.isEmpty()) {
      return false;
    }
    Asset asset = found.get();
    worker.submitAnalyze(
        new AnalyzeJobRequest(
            job.id(),
            asset.id().value(),
            asset.path().value(),
            asset.type().name(),
            cameraProxyPath(asset)));
    assets.save(asset.withAnalysisStatus(AnalysisStatus.RUNNING));
    return true;
  }

  private String cameraProxyPath(Asset asset) {
    return assets.findByProject(asset.projectId()).stream()
        .filter(other -> other.isCameraProxyOf(asset))
        .map(other -> other.path().value())
        .findFirst()
        .orElse(null);
  }
}
