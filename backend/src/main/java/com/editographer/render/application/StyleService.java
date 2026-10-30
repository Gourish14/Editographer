package com.editographer.render.application;

import com.editographer.render.domain.StylePreset;
import com.editographer.render.domain.StylePresetRepository;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Lists the style presets. Spec: specs/07-api-and-data.md */
@Service
public class StyleService {

  private final StylePresetRepository styles;

  public StyleService(StylePresetRepository styles) {
    this.styles = styles;
  }

  @Transactional(readOnly = true)
  public List<StylePreset> listStyles() {
    return styles.findAll();
  }
}
