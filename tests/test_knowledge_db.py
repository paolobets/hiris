import pytest
from hiris.app.proxy.knowledge_db import KnowledgeDB


def test_save_and_load_classification(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.save_classification(
        entity_id="climate.bagno", area="Bagno", entity_type="climate",
        label_it="Termostato", friendly_name="Termostato Bagno",
        domain="climate", device_class=None,
    )
    loaded = db.load_classifications()
    assert "climate.bagno" in loaded
    assert loaded["climate.bagno"]["entity_type"] == "climate"
    assert loaded["climate.bagno"]["area"] == "Bagno"
    db.close()


def test_upsert_classification_updates_on_conflict(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.save_classification("sensor.temp", "Bagno", "temperature", "Temperatura",
                           "Temp Bagno", "sensor", "temperature")
    db.save_classification("sensor.temp", "Camera", "temperature", "Temperatura",
                           "Temp Camera", "sensor", "temperature", classified_by="user")
    loaded = db.load_classifications()
    assert loaded["sensor.temp"]["area"] == "Camera"
    assert loaded["sensor.temp"]["classified_by"] == "user"
    db.close()


def test_add_and_get_annotation(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.add_annotation("climate.bagno", "agent-001", "Scalda lentamente in inverno")
    annots = db.get_annotations("climate.bagno")
    assert len(annots) == 1
    assert annots[0]["annotation"] == "Scalda lentamente in inverno"
    assert annots[0]["source"] == "agent-001"
    db.close()


def test_get_annotations_empty(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    assert db.get_annotations("light.sala") == []
    db.close()


def test_record_correlation_increments_count(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.record_correlation("climate.bagno", "sensor.temp_bagno", "co-occurs")
    db.record_correlation("climate.bagno", "sensor.temp_bagno", "co-occurs")
    rows = db._conn.execute(
        "SELECT observed_count FROM entity_correlations WHERE entity_a='climate.bagno'"
    ).fetchone()
    assert rows[0] == 2
    db.close()


def test_record_query_hit_increments(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.record_query_hit("climate.bagno", "climate")
    db.record_query_hit("climate.bagno", "climate")
    row = db._conn.execute(
        "SELECT hit_count FROM query_patterns WHERE entity_id='climate.bagno'"
    ).fetchone()
    assert row[0] == 2
    db.close()
