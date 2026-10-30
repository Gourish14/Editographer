package com.editographer.render.infrastructure;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

/** JPA row for a style preset. Never leaves the infrastructure layer. */
@Entity
@Table(name = "style_preset")
class JpaStylePresetEntity {

  @Id String id;

  @Column(nullable = false)
  String name;

  @Lob
  @Column(nullable = false)
  String defaults;

  protected JpaStylePresetEntity() {}
}
