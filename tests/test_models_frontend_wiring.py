from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

def test_models_route_js_exists_and_exposes_mount():
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    assert "HirisModelsRoute" in js and "mount" in js
    assert "api/models/config" in js

def test_config_html_includes_script_and_nav():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/models-route.js" in html
    assert 'data-route="models"' in html

def test_main_js_registers_route():
    js = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "#/models" in js
    assert "'models'" in js  # updateNavActive branch

def test_models_route_has_three_sections():
    # fetta E5 Task 7 ("Consumi e Modelli smettono di mentire"): la sezione
    # "Assegnazione per entità" (Chatbot + Brain) esce -- il ramo Chatbot
    # faceva PUT su una rotta inesistente (404 a ogni salvataggio), il ramo
    # Brain scriveva brain_model, una configurazione senza più lettori. Il
    # numero di sezioni scende da quattro a tre; il soggetto del test (il
    # file JS) sopravvive, quindi il test si adegua invece di sparire.
    # Cerchiamo il titolo come LETTERALE passato a buildSectionShell (virgolette
    # dritte), non come prosa nei commenti che spiegano la rimozione (quelli
    # usano virgolette tipografiche): il file continua a *parlare* della
    # sezione uscita, ma non la *rende* più.
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    assert "'Provider attivi'" in js
    assert "'Catena automatica'" in js
    assert "'Assegnazione per entità'" not in js
    assert "'Embeddings'" in js

def test_models_route_puts_full_config_object():
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    # Every write to /api/models/config must send the full {chain_order,
    # provider_models} object (never a partial patch) -- the backend
    # replaces the whole file on PUT. La sezione "Assegnazione per entità",
    # che scriveva anche su api/chatbots/{id}, è uscita alla fetta E5 Task 7:
    # l'unico endpoint di scrittura rimasto in questo file è
    # api/models/config. Cerchiamo la CHIAMATA letterale (non "api/chatbots"
    # come sottostringa, che comparirebbe anche nei commenti che spiegano la
    # rimozione).
    assert "JSON.stringify(state.cfg)" in js
    assert "api('api/chatbots/'" not in js
    assert "fetch('api/chatbots')" not in js
