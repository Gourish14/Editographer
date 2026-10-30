package com.editographer.render.application;

import com.editographer.asset.domain.AnalysisStatus;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.job.application.JobSender;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderId;
import com.editographer.render.domain.RenderRepository;
import com.editographer.worker.domain.RenderJobRequest;
import com.editographer.worker.domain.WorkerClient;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * Sends render jobs with the assets analysis has finished. ANALYZE jobs have priority, so assets
 * still being analyzed when the render was requested are done by now. Spec:
 * specs/07-api-and-data.md#job-flow step 4
 */
@Component
public class RenderJobSender implements JobSender {

  private final RenderRepository renders;
  private final AssetRepository assets;
  private final WorkerClient worker;

  public RenderJobSender(RenderRepository renders, AssetRepository assets, WorkerClient worker) {
    this.renders = renders;
    this.assets = assets;
    this.worker = worker;
  }

  @Override
  public JobKind kind() {
    return JobKind.RENDER;
  }

  @Override
  public boolean send(Job job) {
    Optional<Render> found =
        renders.findById(new RenderId(job.refId())).filter(render -> !render.isFinished());
    if (found.isEmpty()) {
      return false;
    }
    Render render = found.get();
    List<RenderJobRequest.AssetInput> inputs =
        assets.findByProject(render.projectId()).stream()
            .filter(asset -> asset.analysisStatus() == AnalysisStatus.DONE)
            .map(RenderJobRequest.AssetInput::from)
            .toList();
    worker.submitRender(
        new RenderJobRequest(
            job.id(), render.id().value(), render.projectId().value(), render.settings(), inputs));
    return true;
  }
}
