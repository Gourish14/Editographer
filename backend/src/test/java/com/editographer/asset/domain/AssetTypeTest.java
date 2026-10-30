package com.editographer.asset.domain;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

class AssetTypeTest {

  @ParameterizedTest
  @CsvSource({
    "clip.mp4,VIDEO",
    "CLIP.MOV,VIDEO",
    "pano.OSV,VIDEO",
    "pano.LRF,VIDEO",
    "photo.jpg,PHOTO",
    "photo.jpeg,PHOTO",
    "photo.PNG,PHOTO",
    "photo.heic,PHOTO",
    "pano.dng,PHOTO",
    "song.mp3,MUSIC",
    "song.wav,MUSIC",
    "song.m4a,MUSIC",
    "song.flac,MUSIC",
    "my.holiday.clip.mp4,VIDEO"
  })
  void recognisesEverySupportedExtension(String filename, AssetType expected) {
    assertThat(AssetType.fromFilename(filename)).contains(expected);
  }

  @ParameterizedTest
  @ValueSource(strings = {"notes.txt", "archive.zip", "noextension", "trailingdot.", ".mp4x"})
  void rejectsEverythingElse(String filename) {
    assertThat(AssetType.fromFilename(filename)).isEmpty();
  }

  @Test
  void extensionIsLowerCasedAndWithoutTheDot() {
    assertThat(AssetType.extensionOf("Clip.MP4")).isEqualTo("mp4");
    assertThat(AssetType.extensionOf("noextension")).isEmpty();
  }
}
