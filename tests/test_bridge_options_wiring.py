"""Test bridge options wiring: config.yaml, run.sh, translations."""
from pathlib import Path
import yaml

BASE = Path(__file__).resolve().parents[1] / "hiris"


def test_bridge_options():
    """Verify bridge options are properly wired end-to-end.

    fetta E3 Task 4: `bridge_fallback` exited -- it gated `_reasoning_sweep`'s
    local-reasoning fallback for expired holistic jobs, which left with
    `_holistic_reason` (the ronda's revisione olistica). `bridge_enabled`/
    `bridge_deadline_min` stay: the chat-via-abbonamento bridge still uses
    them.

    2.4.0: le quattro opzioni del ponte si sono SPOSTATE sotto la chiave madre
    `ponte:` -- e' l'unico raggruppamento che il Supervisor rende a schermo.
    Cambia il percorso dell'opzione, non la variabile d'ambiente: gli assert su
    `run.sh` qui sotto restano identici perche' `BRIDGE_ENABLED` non si e'
    mosso. Questo test si adegua perche' la chiave si e' spostata, non perche'
    dava fastidio: l'invariante che pinna -- le opzioni del ponte esistono in
    tutti e quattro i posti, `bridge_fallback` in nessuno -- e' intatta, e in
    piu' adesso pinna che stiano SOTTO la sezione e non anche in cima."""
    # Test 1: config.yaml has bridge options and schema
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    opzioni, schema = cfg["options"]["ponte"], cfg["schema"]["ponte"]
    assert "bridge_enabled" in opzioni, "bridge_enabled not in config.yaml options.ponte"
    assert "bridge_deadline_min" in opzioni, "bridge_deadline_min not in config.yaml options.ponte"
    assert "bridge_fallback" not in opzioni, "bridge_fallback should have exited config.yaml options"
    assert "bridge_enabled" not in cfg["options"], "bridge_enabled deve stare SOTTO `ponte:`, non anche in cima"

    assert "bridge_enabled" in schema, "bridge_enabled not in config.yaml schema.ponte"
    assert "bridge_deadline_min" in schema, "bridge_deadline_min not in config.yaml schema.ponte"
    assert "bridge_fallback" not in schema, "bridge_fallback should have exited config.yaml schema"

    # Test 2: run.sh exports bridge env vars
    sh = (BASE / "run.sh").read_text(encoding="utf-8")
    assert "BRIDGE_ENABLED" in sh, "BRIDGE_ENABLED not exported in run.sh"
    assert "BRIDGE_DEADLINE_MIN" in sh, "BRIDGE_DEADLINE_MIN not exported in run.sh"
    assert "BRIDGE_FALLBACK" not in sh, "BRIDGE_FALLBACK should have exited run.sh"

    # Test 3: translations contain bridge_enabled, not bridge_fallback
    it_content = (BASE / "translations" / "it.yaml").read_text(encoding="utf-8")
    en_content = (BASE / "translations" / "en.yaml").read_text(encoding="utf-8")
    assert "bridge_enabled" in it_content, "bridge_enabled not in it.yaml"
    assert "bridge_enabled" in en_content, "bridge_enabled not in en.yaml"
    assert "bridge_fallback" not in it_content, "bridge_fallback should have exited it.yaml"
    assert "bridge_fallback" not in en_content, "bridge_fallback should have exited en.yaml"
