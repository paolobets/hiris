import os

from hiris.app.proxy.knowledge_db import KnowledgeDB


def test_default_db_filename_is_home_map(tmp_path):
    db = KnowledgeDB(os.path.join(str(tmp_path), "home_map.db"))
    # constructing it creates the file with the new name
    assert os.path.exists(os.path.join(str(tmp_path), "home_map.db"))
    db.close()
