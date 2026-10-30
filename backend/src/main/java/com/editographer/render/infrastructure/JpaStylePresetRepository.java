package com.editographer.render.infrastructure;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

interface JpaStylePresetRepository extends JpaRepository<JpaStylePresetEntity, String> {

  List<JpaStylePresetEntity> findAllByOrderByName();
}
