package com.editographer.worker.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.editographer.asset.domain.AssetId;
import com.editographer.common.error.GlobalExceptionHandler;
import com.editographer.job.domain.JobStatus;
import com.editographer.storage.domain.MediaPath;
import com.editographer.worker.application.JobCompletion;
import com.editographer.worker.application.WorkerCallbackService;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

@WebMvcTest(InternalCallbackController.class)
@Import(GlobalExceptionHandler.class)
class InternalCallbackControllerTest {

  private static final UUID ID = UUID.fromString("00000000-0000-0000-0000-000000000007");
  private static final String ANALYZED =
      "{\"assetId\":\"" + ID + "\",\"analysisPath\":\"cache/h/analysis.json\",\"width\":1920}";

  @Autowired private MockMvc mvc;
  @MockitoBean private WorkerCallbackService callbacks;

  private static MockHttpServletRequestBuilder postJson(String path, String body) {
    return post(path).contentType(MediaType.APPLICATION_JSON).content(body);
  }

  @Test
  void aRequestWithoutATokenIsRefused() throws Exception {
    mvc.perform(postJson("/internal/asset-analyzed", ANALYZED))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.errorCode").value("WORKER_TOKEN_INVALID"));
    verify(callbacks, never()).assetAnalyzed(any(), any());
  }

  @Test
  void aRequestWithTheWrongTokenIsRefused() throws Exception {
    mvc.perform(postJson("/internal/complete", "{}").header("X-Worker-Token", "wrong"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void analyzedCallbackReachesTheService() throws Exception {
    mvc.perform(
            postJson("/internal/asset-analyzed", ANALYZED).header("X-Worker-Token", "test-token"))
        .andExpect(status().isNoContent());
    verify(callbacks).assetAnalyzed(eq(new AssetId(ID)), any());
  }

  @Test
  void completeCallbackReachesTheService() throws Exception {
    String body = "{\"jobId\":\"" + ID + "\",\"status\":\"FAILED\",\"error\":\"boom\"}";

    mvc.perform(postJson("/internal/complete", body).header("X-Worker-Token", "test-token"))
        .andExpect(status().isNoContent());
    verify(callbacks).jobCompleted(new JobCompletion(ID, JobStatus.FAILED, null, null, "boom"));
  }

  @Test
  void completeRefusesAStatusOtherThanDoneOrFailed() throws Exception {
    String body = "{\"jobId\":\"" + ID + "\",\"status\":\"RUNNING\"}";

    mvc.perform(postJson("/internal/complete", body).header("X-Worker-Token", "test-token"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errorCode").value("VALIDATION_FAILED"));
  }

  @Test
  void completeStoresThePlanAsJsonText() throws Exception {
    String body =
        "{\"jobId\":\""
            + ID
            + "\",\"status\":\"DONE\",\"outputPath\":\"renders/r/final.mp4\","
            + "\"plan\":{\"version\":1}}";

    mvc.perform(postJson("/internal/complete", body).header("X-Worker-Token", "test-token"))
        .andExpect(status().isNoContent());
    verify(callbacks)
        .jobCompleted(
            new JobCompletion(
                ID, JobStatus.DONE, new MediaPath("renders/r/final.mp4"), "{\"version\":1}", null));
  }

  @Test
  void progressReachesTheService() throws Exception {
    String body = "{\"jobId\":\"" + ID + "\",\"stage\":\"COMPOSING\",\"percent\":40}";

    mvc.perform(postJson("/internal/progress", body).header("X-Worker-Token", "test-token"))
        .andExpect(status().isNoContent());
    verify(callbacks).progress(ID, "COMPOSING", 40, null);
  }

  @Test
  void progressRefusesAPercentAboveAHundred() throws Exception {
    String body = "{\"jobId\":\"" + ID + "\",\"stage\":\"COMPOSING\",\"percent\":101}";

    mvc.perform(postJson("/internal/progress", body).header("X-Worker-Token", "test-token"))
        .andExpect(status().isBadRequest());
  }

  @Test
  void previewReadyReachesTheService() throws Exception {
    String body = "{\"jobId\":\"" + ID + "\",\"path\":\"renders/r/preview.mp4\"}";

    mvc.perform(postJson("/internal/preview-ready", body).header("X-Worker-Token", "test-token"))
        .andExpect(status().isNoContent());
    verify(callbacks).previewReady(ID, new MediaPath("renders/r/preview.mp4"));
  }
}
