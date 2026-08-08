"""fetta E4 Task 4 ("un bot solo"): `ImpostazioniChat` sostituisce l'entita'
Chatbot. Il punto non e' solo lo shape -- e' che "mancare" non e' piu' uno
stato rappresentabile: `carica()` non solleva mai e non restituisce mai
`None`, a differenza di `engine.get_default_chatbot()` che poteva restituire
`None` se il seed non era mai girato (il degrado silenzioso che questo task
chiude, vedi handlers_chat.py)."""
import json

from hiris.app.impostazioni_chat import (
    ID_CHAT_DEFAULT, DEFAULT_SYSTEM_PROMPT, ImpostazioniChat,
)


def test_default_e_completo_senza_argomenti():
    imp = ImpostazioniChat()
    assert imp.nome == "HIRIS"
    assert imp.system_prompt == DEFAULT_SYSTEM_PROMPT
    assert imp.model == "auto"
    assert imp.response_mode == "auto"
    assert imp.thinking_budget == 0
    assert imp.max_chat_turns == 0
    assert imp.restrict_to_home is False


def test_carica_senza_file_restituisce_i_default_nel_codice(tmp_path):
    """Nessun file sul disco -- il caso che prima faceva degradare
    handlers_chat.py: qui non solleva, non restituisce None, produce gli
    stessi default di `ImpostazioniChat()`."""
    imp = ImpostazioniChat.carica(str(tmp_path))
    assert imp == ImpostazioniChat()


def test_salva_poi_carica_ritorna_gli_stessi_valori(tmp_path):
    originale = ImpostazioniChat(
        nome="Casa",
        system_prompt="Sei utile e conciso.",
        model="claude-haiku-4-5-20251001",
        response_mode="compact",
        thinking_budget=1024,
        max_chat_turns=5,
        restrict_to_home=True,
    )
    originale.salva(str(tmp_path))

    ricaricato = ImpostazioniChat.carica(str(tmp_path))
    assert ricaricato == originale


def test_salva_scrittura_atomica_tmp_poi_replace(tmp_path):
    """Stessa disciplina di ChatbotEngine._save(): passa da un file .tmp,
    mai una scrittura diretta sul file finale."""
    ImpostazioniChat(nome="X").salva(str(tmp_path))
    assert (tmp_path / "impostazioni_chat.json").exists()
    assert not (tmp_path / "impostazioni_chat.json.tmp").exists()


def test_carica_file_corrotto_non_solleva_usa_i_default(tmp_path, caplog):
    (tmp_path / "impostazioni_chat.json").write_text("{ non e' json valido", encoding="utf-8")
    with caplog.at_level("ERROR"):
        imp = ImpostazioniChat.carica(str(tmp_path))
    assert imp == ImpostazioniChat()
    assert any("Impostazioni chat illeggibili" in rec.message for rec in caplog.records)


def test_carica_file_parziale_riempie_i_campi_mancanti_coi_default(tmp_path):
    """Un file scritto da una versione futura/passata con solo alcuni campi
    non deve far esplodere il caricamento -- ogni campo assente prende il
    proprio default nel codice, non KeyError."""
    (tmp_path / "impostazioni_chat.json").write_text(
        json.dumps({"nome": "Solo il nome"}), encoding="utf-8",
    )
    imp = ImpostazioniChat.carica(str(tmp_path))
    assert imp.nome == "Solo il nome"
    assert imp.system_prompt == DEFAULT_SYSTEM_PROMPT
    assert imp.model == "auto"
    assert imp.max_chat_turns == 0


def test_carica_system_prompt_vuoto_in_file_ricade_sul_default(tmp_path):
    """Una stringa vuota persistita (non l'assenza della chiave) deve
    comunque ricadere sul prompt di default -- mai una chat con prompt
    letteralmente vuoto."""
    (tmp_path / "impostazioni_chat.json").write_text(
        json.dumps({"system_prompt": ""}), encoding="utf-8",
    )
    imp = ImpostazioniChat.carica(str(tmp_path))
    assert imp.system_prompt == DEFAULT_SYSTEM_PROMPT


def test_id_chat_default_e_hiris_default():
    """Lo stesso id che il frontend gia' usa come fallback locale
    (static/chat/state.js, hiris-chat-card.js) -- non un valore nuovo che il
    client deve imparare."""
    assert ID_CHAT_DEFAULT == "hiris-default"
