package com.editographer;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class EditographerApplicationTests {

  @Autowired private JdbcTemplate jdbc;

  @Test
  void flywayCreatesEveryTableFromTheDataSpec() {
    List<String> tables =
        jdbc.queryForList(
            "SELECT LOWER(table_name) FROM information_schema.tables"
                + " WHERE table_schema = 'PUBLIC'",
            String.class);

    assertThat(tables).contains("project", "asset", "render_job", "job", "style_preset");
  }

  @Test
  void deletingAProjectCascadesToItsAssetsAndRenders() {
    String projectId = "00000000-0000-0000-0000-000000000001";
    jdbc.update(
        "INSERT INTO project (id, name, created_at) VALUES (?, 'p', CURRENT_TIMESTAMP)", projectId);
    jdbc.update(
        "INSERT INTO asset (id, project_id, type, filename, path, size_bytes, analysis_status,"
            + " created_at) VALUES (RANDOM_UUID(), ?, 'VIDEO', 'a.mp4', 'a.mp4', 1, 'PENDING',"
            + " CURRENT_TIMESTAMP)",
        projectId);
    jdbc.update(
        "INSERT INTO render_job (id, project_id, ratio, quality, fps, style, mode, cool_mode, seed,"
            + " status, progress, created_at) VALUES (RANDOM_UUID(), ?, '9:16', '4K', 30, 'Auto',"
            + " 'Fast', FALSE, 1, 'QUEUED', 0, CURRENT_TIMESTAMP)",
        projectId);

    jdbc.update("DELETE FROM project WHERE id = ?", projectId);

    assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM asset", Integer.class)).isZero();
    assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM render_job", Integer.class)).isZero();
  }
}
