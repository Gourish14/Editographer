package com.editographer.common.logging;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServletResponse;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class RequestIdFilterTest {

  private final RequestIdFilter filter = new RequestIdFilter();

  private String runWith(String header, AtomicReference<String> mdcDuringRequest) throws Exception {
    MockHttpServletRequest request = new MockHttpServletRequest();
    if (header != null) {
      request.addHeader(LoggingConstants.REQUEST_ID_HEADER, header);
    }
    HttpServletResponse response = new MockHttpServletResponse();
    MockFilterChain chain =
        new MockFilterChain(
            new jakarta.servlet.http.HttpServlet() {
              private static final long serialVersionUID = 1L;

              @Override
              protected void service(
                  jakarta.servlet.http.HttpServletRequest req,
                  jakarta.servlet.http.HttpServletResponse res) {
                mdcDuringRequest.set(MDC.get(LoggingConstants.REQUEST_ID));
              }
            });
    filter.doFilter(request, response, chain);
    return response.getHeader(LoggingConstants.REQUEST_ID_HEADER);
  }

  @Test
  void generatesAnIdWhenNoneIsSupplied() throws Exception {
    AtomicReference<String> seen = new AtomicReference<>();

    String returned = runWith(null, seen);

    assertThat(UUID.fromString(returned)).isNotNull();
    assertThat(seen).hasValue(returned);
  }

  @Test
  void keepsASafeSuppliedId() throws Exception {
    AtomicReference<String> seen = new AtomicReference<>();

    assertThat(runWith("abc-123", seen)).isEqualTo("abc-123");
    assertThat(seen).hasValue("abc-123");
  }

  @Test
  void replacesAnUnsafeSuppliedId() throws Exception {
    AtomicReference<String> seen = new AtomicReference<>();

    String returned = runWith("bad\"id\ninjected", seen);

    assertThat(UUID.fromString(returned)).isNotNull();
  }

  @Test
  void clearsTheMdcAfterTheRequest() throws Exception {
    runWith("abc-123", new AtomicReference<>());

    assertThat(MDC.get(LoggingConstants.REQUEST_ID)).isNull();
  }
}
