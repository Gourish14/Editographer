package com.editographer.project.api.dto;

import com.editographer.project.domain.Project;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** Body of POST /api/projects. */
public record CreateProjectRequest(@NotBlank @Size(max = Project.MAX_NAME_LENGTH) String name) {}
