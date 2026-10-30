package com.editographer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

/** Composition root of the backend. Spec: specs/02-architecture.md */
@SpringBootApplication
@ConfigurationPropertiesScan
public class EditographerApplication {

  public static void main(String[] args) {
    SpringApplication.run(EditographerApplication.class, args);
  }
}
