package com.editographer.render.infrastructure;

import com.editographer.render.domain.StylePreset;
import com.editographer.render.domain.StylePresetRepository;
import java.util.List;
import org.springframework.stereotype.Component;

/** JPA implementation of the style preset port. */
@Component
final class StylePresetRepositoryAdapter implements StylePresetRepository {

  private final JpaStylePresetRepository jpa;

  StylePresetRepositoryAdapter(JpaStylePresetRepository jpa) {
    this.jpa = jpa;
  }

  @Override
  public List<StylePreset> findAll() {
    return jpa.findAllByOrderByName().stream()
        .map(row -> new StylePreset(row.id, row.name, row.defaults))
        .toList();
  }

  @Override
  public boolean existsById(String id) {
    return jpa.existsById(id);
  }
}
