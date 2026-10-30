package com.editographer.common.error;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.editographer.common.logging.RequestIdFilter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@WebMvcTest(controllers = GlobalExceptionHandlerTest.FailingController.class)
@Import({
  GlobalExceptionHandlerTest.FailingController.class,
  GlobalExceptionHandler.class,
  RequestIdFilter.class
})
class GlobalExceptionHandlerTest {

  @Autowired private MockMvc mvc;

  @Test
  void apiExceptionBecomesProblemDetailWithItsErrorCode() throws Exception {
    mvc.perform(get("/test/not-found"))
        .andExpect(status().isNotFound())
        .andExpect(header().string("Content-Type", "application/problem+json"))
        .andExpect(jsonPath("$.errorCode").value("PROJECT_NOT_FOUND"))
        .andExpect(jsonPath("$.detail").value("No such project"))
        .andExpect(jsonPath("$.requestId").isNotEmpty());
  }

  @Test
  void validationFailureNamesTheField() throws Exception {
    mvc.perform(
            post("/test/validated")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errorCode").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.detail").value("name must not be blank"));
  }

  @Test
  void unexpectedExceptionIsMaskedAsInternalError() throws Exception {
    mvc.perform(get("/test/boom"))
        .andExpect(status().isInternalServerError())
        .andExpect(jsonPath("$.errorCode").value("INTERNAL_ERROR"))
        .andExpect(jsonPath("$.detail").value("Something went wrong on the server."));
  }

  @Test
  void frameworkErrorsAlsoCarryAnErrorCode() throws Exception {
    mvc.perform(post("/test/not-found"))
        .andExpect(status().isMethodNotAllowed())
        .andExpect(jsonPath("$.errorCode").value("REQUEST_INVALID"));
  }

  record NamedRequest(@NotBlank String name) {}

  @RestController
  static class FailingController {

    @GetMapping("/test/not-found")
    void notFound() {
      throw new ApiException(ErrorCode.PROJECT_NOT_FOUND, "No such project");
    }

    @GetMapping("/test/boom")
    void boom() {
      throw new IllegalStateException("secret internal detail");
    }

    @PostMapping("/test/validated")
    void validated(@Valid @RequestBody NamedRequest request) {}
  }
}
