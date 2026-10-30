package com.editographer;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noFields;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noMethods;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;
import jakarta.persistence.Entity;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.RestController;

/** Hexagonal dependency rules. Spec: specs/11-coding-standards.md#2-architecture-style */
@AnalyzeClasses(packages = "com.editographer", importOptions = ImportOption.DoNotIncludeTests.class)
class ArchitectureTest {

  @ArchTest
  static final ArchRule DOMAIN_STAYS_FREE_OF_FRAMEWORKS_AND_OUTER_LAYERS =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAnyPackage(
              "org.springframework..",
              "jakarta..",
              "org.hibernate..",
              "..api..",
              "..application..",
              "..infrastructure..")
          .allowEmptyShould(true);

  @ArchTest
  static final ArchRule APPLICATION_DOES_NOT_DEPEND_ON_API_OR_INFRASTRUCTURE =
      noClasses()
          .that()
          .resideInAPackage("..application..")
          .should()
          .dependOnClassesThat()
          .resideInAnyPackage("..api..", "..infrastructure..")
          .allowEmptyShould(true);

  @ArchTest
  static final ArchRule API_DOES_NOT_DEPEND_ON_INFRASTRUCTURE =
      noClasses()
          .that()
          .resideInAPackage("..api..")
          .should()
          .dependOnClassesThat()
          .resideInAPackage("..infrastructure..")
          .allowEmptyShould(true);

  @ArchTest
  static final ArchRule JPA_ENTITIES_STAY_IN_INFRASTRUCTURE =
      classes()
          .that()
          .areAnnotatedWith(Entity.class)
          .should()
          .resideInAPackage("..infrastructure..")
          .allowEmptyShould(true);

  @ArchTest
  static final ArchRule CONTROLLERS_LIVE_IN_THE_API_LAYER =
      classes()
          .that()
          .areAnnotatedWith(RestController.class)
          .should()
          .resideInAPackage("..api..")
          .allowEmptyShould(true);

  @ArchTest
  static final ArchRule CONSTRUCTOR_INJECTION_ONLY =
      noFields().should().beAnnotatedWith(Autowired.class).allowEmptyShould(true);

  @ArchTest
  static final ArchRule TRANSACTIONAL_CLASSES_LIVE_IN_APPLICATION =
      noClasses()
          .that()
          .resideOutsideOfPackage("..application..")
          .should()
          .beAnnotatedWith(Transactional.class)
          .allowEmptyShould(true);

  @ArchTest
  static final ArchRule TRANSACTIONAL_METHODS_LIVE_IN_APPLICATION =
      noMethods()
          .that()
          .areDeclaredInClassesThat()
          .resideOutsideOfPackage("..application..")
          .should()
          .beAnnotatedWith(Transactional.class)
          .allowEmptyShould(true);
}
