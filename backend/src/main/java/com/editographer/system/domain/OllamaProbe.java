package com.editographer.system.domain;

/** Port that checks whether the local LLM runtime answers. */
public interface OllamaProbe {

  boolean isRunning();
}
