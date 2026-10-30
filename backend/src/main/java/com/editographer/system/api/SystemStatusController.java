package com.editographer.system.api;

import com.editographer.system.application.SystemStatusService;
import com.editographer.system.domain.SystemStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** System health for the UI and start.bat. Spec: specs/07-api-and-data.md */
@RestController
public final class SystemStatusController {

  private final SystemStatusService service;

  public SystemStatusController(SystemStatusService service) {
    this.service = service;
  }

  @GetMapping("/api/system")
  public SystemStatus status() {
    return service.currentStatus();
  }
}
