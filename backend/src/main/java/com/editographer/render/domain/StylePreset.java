package com.editographer.render.domain;

/**
 * A named style. Defaults is a JSON document. Spec:
 * specs/05-editing-brain.md#b3-pacing-and-style-presets-pacingpy
 */
public record StylePreset(String id, String name, String defaults) {}
