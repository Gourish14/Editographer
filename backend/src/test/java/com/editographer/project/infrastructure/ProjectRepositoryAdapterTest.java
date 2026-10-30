package com.editographer.project.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.editographer.project.domain.Project;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.context.annotation.Import;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(ProjectRepositoryAdapter.class)
class ProjectRepositoryAdapterTest {

  private static final Instant OLDER = Instant.parse("2026-10-29T10:00:00Z");
  private static final Instant NEWER = Instant.parse("2026-10-30T10:00:00Z");

  @Autowired private ProjectRepository repository;

  @Test
  void savedProjectCanBeReadBackUnchanged() {
    Project project = Project.create("Goa trip", NEWER);

    repository.save(project);

    assertThat(repository.findById(project.id())).contains(project);
  }

  @Test
  void findAllReturnsTheNewestProjectFirst() {
    Project older = repository.save(Project.create("older", OLDER));
    Project newer = repository.save(Project.create("newer", NEWER));

    assertThat(repository.findAll()).containsExactly(newer, older);
  }

  @Test
  void findByIdIsEmptyForAnUnknownProject() {
    assertThat(repository.findById(ProjectId.newId())).isEmpty();
  }

  @Test
  void existsByIdReflectsWhatIsStored() {
    Project project = repository.save(Project.create("a", NEWER));

    assertThat(repository.existsById(project.id())).isTrue();
    assertThat(repository.existsById(ProjectId.newId())).isFalse();
  }

  @Test
  void deleteByIdRemovesTheProject() {
    Project project = repository.save(Project.create("a", NEWER));

    repository.deleteById(project.id());

    assertThat(repository.findById(project.id())).isEmpty();
  }
}
