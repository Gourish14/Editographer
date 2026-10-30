package com.editographer.common.error;

import com.editographer.common.logging.LoggingConstants;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

/**
 * Turns every failure into an RFC 9457 ProblemDetail with a stable errorCode. Spec:
 * specs/11-coding-standards.md#3-backend--spring-boot-4-java-25
 */
@RestControllerAdvice
public final class GlobalExceptionHandler extends ResponseEntityExceptionHandler {

  private static final Logger LOG = LoggerFactory.getLogger(GlobalExceptionHandler.class);
  private static final String ERROR_CODE_PROPERTY = "errorCode";
  private static final String REQUEST_ID_PROPERTY = "requestId";
  private static final String UNEXPECTED_ERROR_DETAIL = "Something went wrong on the server.";

  @ExceptionHandler(ApiException.class)
  public ResponseEntity<Object> handleApiException(ApiException exception) {
    ErrorCode errorCode = exception.errorCode();
    ProblemDetail problem =
        ProblemDetail.forStatusAndDetail(errorCode.status(), exception.getMessage());
    return ResponseEntity.status(errorCode.status()).body(tagged(problem, errorCode));
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<Object> handleUnexpected(Exception exception) {
    LOG.atError()
        .addKeyValue(LoggingConstants.EVENT, "request.failed")
        .addKeyValue(LoggingConstants.ERROR_CODE, ErrorCode.INTERNAL_ERROR.name())
        .setCause(exception)
        .log("Unhandled exception");
    ErrorCode errorCode = ErrorCode.INTERNAL_ERROR;
    ProblemDetail problem =
        ProblemDetail.forStatusAndDetail(errorCode.status(), UNEXPECTED_ERROR_DETAIL);
    return ResponseEntity.status(errorCode.status()).body(tagged(problem, errorCode));
  }

  @Override
  protected ResponseEntity<Object> handleMethodArgumentNotValid(
      MethodArgumentNotValidException exception,
      HttpHeaders headers,
      HttpStatusCode status,
      WebRequest request) {
    String detail =
        exception.getBindingResult().getFieldErrors().stream()
            .map(GlobalExceptionHandler::describe)
            .collect(Collectors.joining("; "));
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(status, detail);
    return ResponseEntity.status(status)
        .headers(headers)
        .body(tagged(problem, ErrorCode.VALIDATION_FAILED));
  }

  @Override
  protected ResponseEntity<Object> handleExceptionInternal(
      Exception exception,
      Object body,
      HttpHeaders headers,
      HttpStatusCode status,
      WebRequest request) {
    ResponseEntity<Object> response =
        super.handleExceptionInternal(exception, body, headers, status, request);
    if (response != null && response.getBody() instanceof ProblemDetail problem) {
      ErrorCode errorCode =
          status.is4xxClientError() ? ErrorCode.REQUEST_INVALID : ErrorCode.INTERNAL_ERROR;
      tagged(problem, errorCode);
    }
    return response;
  }

  private static String describe(FieldError error) {
    return error.getField() + " " + error.getDefaultMessage();
  }

  private static ProblemDetail tagged(ProblemDetail problem, ErrorCode errorCode) {
    problem.setProperty(ERROR_CODE_PROPERTY, errorCode.name());
    String requestId = MDC.get(LoggingConstants.REQUEST_ID);
    if (requestId != null) {
      problem.setProperty(REQUEST_ID_PROPERTY, requestId);
    }
    return problem;
  }
}
