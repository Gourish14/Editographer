package com.editographer.render.domain;

import java.util.List;

/** Port for reading style presets. */
public interface StylePresetRepository {

  List<StylePreset> findAll();

  boolean existsById(String id);
}
