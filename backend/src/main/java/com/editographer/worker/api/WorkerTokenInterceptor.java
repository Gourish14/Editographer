package com.editographer.worker.api;

import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * Lets only the worker call /internal/*. Spec:
 * specs/07-api-and-data.md#internal-worker--backend-header-x-worker-token
 */
public final class WorkerTokenInterceptor implements HandlerInterceptor {

  private static final String TOKEN_HEADER = "X-Worker-Token";

  private final byte[] expected;

  public WorkerTokenInterceptor(String token) {
    this.expected = token.getBytes(StandardCharsets.UTF_8);
  }

  @Override
  public boolean preHandle(
      HttpServletRequest request, HttpServletResponse response, Object handler) {
    String supplied = request.getHeader(TOKEN_HEADER);
    if (supplied == null
        || !MessageDigest.isEqual(expected, supplied.getBytes(StandardCharsets.UTF_8))) {
      throw new ApiException(ErrorCode.WORKER_TOKEN_INVALID, "Missing or wrong worker token");
    }
    return true;
  }
}
