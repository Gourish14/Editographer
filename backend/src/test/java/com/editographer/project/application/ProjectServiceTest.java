package com.editographer.project.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.project.domain.Project;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class ProjectServiceTest {

  private static final Instant NOW = Instant.parse("2026-10-30T10:00:00Z");

  private final ProjectRepository repository = mock(ProjectRepository.class);
  private final ProjectService service =
      new ProjectService(repository, Clock.fixed(NOW, ZoneOffset.UTC));

  @Test
  void createStampsTheProjectWithTheClockAndSavesIt() {
    when(repository.save(any())).thenAnswer(call -> call.getArgument(0));

    Project created = service.createProject("Goa trip");

    assertThat(created.name()).isEqualTo("Goa trip");
    assertThat(created.createdAt()).isEqualTo(NOW);
    verify(repository).save(created);
  }

  @Test
  void listReturnsWhatTheRepositoryReturns() {
    List<Project> stored = List.of(Project.create("a", NOW), Project.create("b", NOW));
    when(repository.findAll()).thenReturn(stored);

    assertThat(service.listProjects()).isEqualTo(stored);
  }

  @Test
  void getReturnsAnExistingProject() {
    Project stored = Project.create("a", NOW);
    when(repository.findById(stored.id())).thenReturn(Optional.of(stored));

    assertThat(service.getProject(stored.id())).isEqualTo(stored);
  }

  @Test
  void getFailsWithProjectNotFound() {
    ProjectId id = ProjectId.newId();
    when(repository.findById(id)).thenReturn(Optional.empty());

    assertThatThrownBy(() -> service.getProject(id))
        .isInstanceOfSatisfying(
            ApiException.class,
            error -> assertThat(error.errorCode()).isEqualTo(ErrorCode.PROJECT_NOT_FOUND));
  }

  @Test
  void deleteRemovesAnExistingProject() {
    ProjectId id = ProjectId.newId();
    when(repository.existsById(id)).thenReturn(true);

    service.deleteProject(id);

    verify(repository).deleteById(id);
  }

  @Test
  void deleteFailsWithProjectNotFoundAndRemovesNothing() {
    ProjectId id = ProjectId.newId();
    when(repository.existsById(id)).thenReturn(false);

    assertThatThrownBy(() -> service.deleteProject(id))
        .isInstanceOfSatisfying(
            ApiException.class,
            error -> assertThat(error.errorCode()).isEqualTo(ErrorCode.PROJECT_NOT_FOUND));
    verify(repository, never()).deleteById(any());
  }
}
