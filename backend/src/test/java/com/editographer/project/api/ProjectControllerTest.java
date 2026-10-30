package com.editographer.project.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.common.error.GlobalExceptionHandler;
import com.editographer.project.application.ProjectService;
import com.editographer.project.domain.Project;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ProjectController.class)
@Import(GlobalExceptionHandler.class)
class ProjectControllerTest {

  private static final Instant NOW = Instant.parse("2026-10-30T10:00:00Z");
  private static final String UNKNOWN_ID = "00000000-0000-0000-0000-000000000009";

  @Autowired private MockMvc mvc;
  @MockitoBean private ProjectService service;

  @Test
  void listReturnsProjects() throws Exception {
    Project project = Project.create("Goa trip", NOW);
    when(service.listProjects()).thenReturn(List.of(project));

    mvc.perform(get("/api/projects"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0].id").value(project.id().value().toString()))
        .andExpect(jsonPath("$[0].name").value("Goa trip"))
        .andExpect(jsonPath("$[0].createdAt").value("2026-10-30T10:00:00Z"));
  }

  @Test
  void createReturns201WithALocation() throws Exception {
    Project project = Project.create("Goa trip", NOW);
    when(service.createProject("Goa trip")).thenReturn(project);

    mvc.perform(
            post("/api/projects")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Goa trip\"}"))
        .andExpect(status().isCreated())
        .andExpect(header().string("Location", "/api/projects/" + project.id().value()))
        .andExpect(jsonPath("$.name").value("Goa trip"));
  }

  @Test
  void createRejectsABlankName() throws Exception {
    mvc.perform(
            post("/api/projects")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"   \"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errorCode").value("VALIDATION_FAILED"));
    verify(service, never()).createProject(any());
  }

  @Test
  void createRejectsANameLongerThanTheColumn() throws Exception {
    String tooLong = "x".repeat(Project.MAX_NAME_LENGTH + 1);

    mvc.perform(
            post("/api/projects")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"" + tooLong + "\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errorCode").value("VALIDATION_FAILED"));
  }

  @Test
  void getReturnsAProject() throws Exception {
    Project project = Project.create("Goa trip", NOW);
    when(service.getProject(project.id())).thenReturn(project);

    mvc.perform(get("/api/projects/" + project.id().value()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("Goa trip"));
  }

  @Test
  void getMapsAMissingProjectTo404() throws Exception {
    when(service.getProject(any()))
        .thenThrow(new ApiException(ErrorCode.PROJECT_NOT_FOUND, "missing"));

    mvc.perform(get("/api/projects/" + UNKNOWN_ID))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.errorCode").value("PROJECT_NOT_FOUND"));
  }

  @Test
  void getRejectsAnIdThatIsNotAUuid() throws Exception {
    mvc.perform(get("/api/projects/not-a-uuid"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errorCode").value("REQUEST_INVALID"));
  }

  @Test
  void deleteReturns204() throws Exception {
    mvc.perform(delete("/api/projects/" + UNKNOWN_ID)).andExpect(status().isNoContent());
  }

  @Test
  void deleteMapsAMissingProjectTo404() throws Exception {
    doThrow(new ApiException(ErrorCode.PROJECT_NOT_FOUND, "missing"))
        .when(service)
        .deleteProject(any());

    mvc.perform(delete("/api/projects/" + UNKNOWN_ID))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.errorCode").value("PROJECT_NOT_FOUND"));
  }
}
