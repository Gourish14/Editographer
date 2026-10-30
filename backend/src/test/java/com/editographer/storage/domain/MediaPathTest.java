package com.editographer.storage.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class MediaPathTest {

  @ParameterizedTest
  @ValueSource(strings = {"uploads/p/a.mp4", "renders/r/final.mp4", "a"})
  void acceptsRelativePaths(String value) {
    assertThat(new MediaPath(value).value()).isEqualTo(value);
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "",
        " ",
        "/etc/passwd",
        "../secret",
        "uploads/../../secret",
        "uploads/./a",
        "uploads//a",
        "uploads/",
        "C:/Windows",
        "uploads\\..\\secret"
      })
  void rejectsPathsThatCouldLeaveTheMediaFolder(String value) {
    assertThatThrownBy(() -> new MediaPath(value)).isInstanceOf(IllegalArgumentException.class);
  }
}
