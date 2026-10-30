package com.editographer.render.api;

import com.editographer.render.api.dto.StyleResponse;
import com.editographer.render.application.StyleService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Lists style presets. Spec: specs/07-api-and-data.md */
@RestController
public final class StyleController {

  private final StyleService service;

  public StyleController(StyleService service) {
    this.service = service;
  }

  @GetMapping("/api/styles")
  public List<StyleResponse> list() {
    return service.listStyles().stream().map(StyleResponse::from).toList();
  }
}
