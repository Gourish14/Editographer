package com.editographer.project.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class ProjectTest {

  private static final Instant NOW = Instant.parse("2026-10-30T10:00:00Z");

  @Test
  void createStripsTheNameAndAssignsAnId() {
    Project project = Project.create("  Goa trip  ", NOW);

    assertThat(project.name()).isEqualTo("Goa trip");
    assertThat(project.id()).isNotNull();
    assertThat(project.createdAt()).isEqualTo(NOW);
  }

  @Test
  void rejectsABlankName() {
    assertThatThrownBy(() -> Project.create("   ", NOW))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void rejectsANameLongerThanTheColumn() {
    String tooLong = "x".repeat(Project.MAX_NAME_LENGTH + 1);

    assertThatThrownBy(() -> Project.create(tooLong, NOW))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void acceptsANameAtTheLimit() {
    String longest = "x".repeat(Project.MAX_NAME_LENGTH);

    assertThat(Project.create(longest, NOW).name()).hasSize(Project.MAX_NAME_LENGTH);
  }
}
