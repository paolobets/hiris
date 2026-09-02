"""La pagina di configurazione dell'add-on e' un ordine, non un insieme.

`test_traduzioni_coprono_le_opzioni.py` sorveglia che ogni opzione **esista**
in tutti i posti dove deve esistere. Questo file sorveglia l'altra meta', quella
che l'utente vede per prima: **dove** ogni opzione sta.

Il difetto che ha motivato questo file (2.3.0): la pagina era cresciuta per
accumulo, nell'ordine in cui la storia del progetto aveva prodotto le opzioni.
L'interruttore `provider_subscription` stava al quarto posto e il token che gli
serve al ventitreesimo; i due interruttori del ponte, che vanno accesi insieme
o non fanno niente, erano separati da due campi numerici; `internal_token` e
`supervisor_ingress_cidr` stavano fra gli embedding e «Tema», con lo stesso
peso visivo di una preferenza di colore.

Un ordine non lascia traccia in nessun test finche' qualcuno non lo scrive: la
prossima opzione aggiunta in coda al file, senza pensarci, rimette la pagina
com'era. Ognuno degli assert qui sotto e' un rilievo di quel riordino, messo
dove non puo' tornare indietro in silenzio.

**VERSIONE B (3.0.0).** Quattordici opzioni sono uscite, e con loro il soggetto
di quattro test di questo file: i cinque interruttori `provider_*` (e quindi la
coppia interruttore-credenziale), le tre voci del blocco `ponte:` (e quindi
l'interruttore unico del ponte e le sue etichette). Non sono stati cancellati e
basta -- questo file esiste perche' l'ordine della pagina non resti senza
traccia -- sono stati **riscritti sul contenuto vero della pagina dopo la
fetta**: quattro credenziali, l'indirizzo di Ollama, il tema, gli embedding
inerti, il blocco avanzate. E ne sono nati due che dicono la cosa nuova: cio'
che e' USCITO da tutti e cinque i posti, e cio' che RESTA.
"""
from pathlib import Path

import pytest
import yaml

BASE = Path(__file__).resolve().parents[1] / "hiris"

# Le quattro credenziali, nell'ordine in cui la pagina le presenta -- che e'
# l'ordine di ripiego di `balanced`, lo stesso che la pagina Modelli propone
# col preset omonimo. Fino alla 2.5.0 ognuna aveva sopra il suo interruttore
# `provider_*`, e il test di questo file pinnava proprio quell'adiacenza (un
# interruttore separato dalla sua credenziale da uno a diciannove campi era il
# difetto della 2.3.0). Gli interruttori sono usciti: non c'e' piu' niente da
# tenere adiacente, e cio' che resta da pinnare e' che le credenziali stiano
# TUTTE INSIEME e in quest'ordine, invece di essere sparse fra il tema e il
# registro come lo erano prima della 2.3.0.
CREDENZIALI_IN_ORDINE = [
    "claude_api_key",
    "claude_code_oauth_token",
    "openrouter_api_key",
    "openai_api_key",
    "local_model",
]

# Toccarle senza sapere cosa si fa apre la API di HIRIS sulla rete locale.
# Il Supervisor non sa marcare un campo come pericoloso: stare in fondo, e il
# prefisso «Avanzate · » nell'etichetta, sono l'unico segnale disponibile.
# Erano quattro: `debug_expose_port` e' uscita con la versione B -- da sola non
# apriva niente, scriveva sette righe di promemoria nel registro.
IN_FONDO_PERCHE_PERICOLOSE = [
    "log_level",
    "internal_token",
    "supervisor_ingress_cidr",
]

# I due gruppi annidati rimasti. Il dizionario annidato e' l'unico
# raggruppamento che il Supervisor rende a schermo, e l'intestazione porta il
# contesto: dentro, i nomi dei figli non lo ripetono. Era il test sulla sezione
# «Ponte», uscita per intero; l'invariante non era del ponte, era della
# nidificazione, e vale ancora dove la nidificazione c'e'.
SEZIONI_ANNIDATE = ["local_model", "memory"]


def _config() -> dict:
    return yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))


def _traduzioni(lingua: str) -> dict:
    testo = (BASE / "translations" / f"{lingua}.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(testo)["configuration"]


def test_options_e_schema_sono_nello_stesso_ordine():
    """Non solo le stesse chiavi: le stesse chiavi **in fila uguale**.

    Il Supervisor costruisce il modulo iterando lo `schema:`, ma un umano legge
    `options:`, dove stanno i valori predefiniti. Se i due blocchi divergono
    d'ordine, il file smette di dire quale pagina l'utente vedra' — e nessuno
    se ne accorge, perche' l'insieme delle chiavi resta identico.
    """
    cfg = _config()
    assert list(cfg["options"]) == list(cfg["schema"])
    for nome, valore in cfg["options"].items():
        if isinstance(valore, dict):
            assert list(valore) == list(cfg["schema"][nome]), (
                f"il gruppo annidato '{nome}' ha ordini diversi nei due blocchi"
            )


def test_le_credenziali_aprono_la_pagina_e_stanno_tutte_insieme():
    """Cio' che resta da custodire viene prima di tutto il resto.

    Prima della 2.3.0 le credenziali erano sparse: chi installava HIRIS doveva
    scorrere l'intera pagina per trovare dove incollare una chiave. La 2.3.0 le
    ha messe accanto ai loro interruttori; la versione B ha tolto gli
    interruttori, e quello che resta -- l'unica cosa che questa pagina fa
    ancora -- deve stare in cima e in blocco.
    """
    ordine = list(_config()["options"])
    assert ordine[:len(CREDENZIALI_IN_ORDINE)] == CREDENZIALI_IN_ORDINE, (
        "le credenziali non aprono piu' la pagina, o non sono piu' contigue: "
        f"{ordine}"
    )


def test_le_opzioni_pericolose_restano_in_fondo():
    ordine = list(_config()["options"])
    assert ordine[-len(IN_FONDO_PERCHE_PERICOLOSE):] == IN_FONDO_PERCHE_PERICOLOSE, (
        "il blocco «Avanzate» non e' piu' l'ultimo della pagina: un'opzione "
        f"nuova gli e' finita sotto. Coda attuale: {ordine[-6:]}"
    )


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_le_opzioni_pericolose_lo_dicono_nell_etichetta(lingua):
    """Posizione **e** nome: il prefisso e' la meta' del segnale, e da solo
    sopravvive a un utente che arriva sul campo da una ricerca invece che
    scorrendo la pagina."""
    prefisso = "Avanzate · " if lingua == "it" else "Advanced · "
    tradotte = _traduzioni(lingua)
    for nome in IN_FONDO_PERCHE_PERICOLOSE:
        assert tradotte[nome]["name"].startswith(prefisso), (
            f"{lingua}.yaml: l'etichetta di '{nome}' non dichiara piu' che il "
            f"campo e' avanzato (atteso il prefisso «{prefisso}»)"
        )


def test_il_ponte_non_e_piu_un_interruttore_di_questa_pagina():
    """La fine di una storia lunga quattro versioni.

    Erano due leve che dovevano essere accese insieme (`bridge_enabled` e
    `chat_via_subscription`, `_chat_subscription_active` = AND). La 2.2.1 le
    aveva rese adiacenti, la 2.3.x le aveva chiamate «(1 di 2)» e «(2 di 2)»;
    la 2.4.0 le fonde in `ponte.attivo`, perche' non erano due decisioni; e la
    3.0.0 porta via anche quella, perche' non era una decisione da prendere
    QUI: si prende dove si vede l'effetto, cioe' nella pagina Modelli, dove il
    piano compare in testa alla catena o ne sta fuori.

    Il test che stava qui pinnava «un interruttore solo dentro `ponte:`», ed
    era la rete contro una seconda leva rientrata dalla porta di servizio. La
    rete adesso e' piu' larga e piu' semplice: dentro questa pagina non c'e'
    NESSUN interruttore. Un booleano qui sarebbe per forza una decisione, e le
    decisioni non stanno piu' qui.
    """
    cfg = _config()
    assert "ponte" not in cfg["options"] and "ponte" not in cfg["schema"]

    booleani = []

    def cerca(albero, prefisso=""):
        for chiave, valore in albero.items():
            if isinstance(valore, dict):
                cerca(valore, prefisso + chiave + ".")
            elif isinstance(valore, bool):
                booleani.append(prefisso + chiave)

    cerca(cfg["options"])
    assert booleani == [], (
        f"un interruttore e' tornato nella pagina dell'add-on: {booleani}. "
        "Questa pagina custodisce credenziali, non prende decisioni"
    )


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_nessuna_etichetta_ripete_la_parola_di_un_altro_concetto(lingua):
    """Un concetto, un nome.

    Fino alla 2.2.1 tre interruttori diversi si chiamavano tutti e tre con la
    parola «abbonamento»/«subscription»: «Attiva provider: Abbonamento (Claude
    Max)», «Chat via abbonamento — attiva», «Ponte abbonamento — attiva». Chi
    leggeva non poteva sapere quale servisse a cosa. Adesso le due famiglie si
    chiamano «Piano Claude Max» (come paghi) e «Ponte» (il meccanismo), e la
    parola vecchia non torna: se torna, torna anche l'ambiguita'.
    """
    parola = "abbonamento" if lingua == "it" else "subscription"
    colpevoli = []

    def cerca(albero, prefisso=""):
        for chiave, voce in albero.items():
            if chiave in ("name", "description") or not isinstance(voce, dict):
                continue
            if parola in voce.get("name", "").lower():
                colpevoli.append(prefisso + chiave)
            cerca(voce, prefisso + chiave + ".")   # anche dentro le sezioni

    cerca(_traduzioni(lingua))
    assert not colpevoli, (
        f"{lingua}.yaml: «{parola}» e' tornata nell'etichetta di {colpevoli}. "
        "Era la parola che tre interruttori diversi si contendevano"
    )


def test_chat_policy_e_uscita_da_tutti_e_cinque_i_posti():
    """Un'opzione vive in cinque posti; toglierla da meno di cinque lascia un
    residuo. `chat_policy` era un ordine di backend in CSV che il router
    scartava sempre (`model_chain` lo sovrascrive a ogni costruzione): un campo
    che l'utente poteva compilare senza che succedesse mai niente.
    """
    cfg = _config()
    assert "chat_policy" not in cfg["options"]
    assert "chat_policy" not in cfg["schema"]
    for lingua in ("it", "en"):
        assert "chat_policy" not in _traduzioni(lingua)

    # Nei due file di codice si guardano le righe VIVE: sia `run.sh` sia
    # `server.py` spiegano in un commento perche' l'opzione e' uscita, e un
    # commento che RACCONTA una cosa morta non e' quella cosa viva. (Stesso
    # criterio di `test_action_prompt._testi_che_legge_l_utente`.)
    def _righe_vive(percorso: Path) -> list[str]:
        return [r for r in percorso.read_text(encoding="utf-8").splitlines()
                if not r.lstrip().startswith("#")]

    assert not [r for r in _righe_vive(BASE / "run.sh") if "CHAT_POLICY" in r], (
        "run.sh esporta ancora la variabile d'ambiente di un'opzione uscita"
    )
    assert not [r for r in _righe_vive(BASE / "app" / "server.py")
                if "CHAT_POLICY" in r], (
        "server.py legge ancora la variabile d'ambiente di un'opzione uscita"
    )


def test_le_decisioni_sono_uscite_da_tutti_e_cinque_i_posti():
    """Un'opzione vive in cinque posti; toglierla da meno di cinque lascia un
    residuo. Queste quattordici sono uscite perche' la decisione che
    rappresentavano si prende adesso nella pagina Modelli (o, per due di loro,
    non si prende piu' affatto)."""
    cfg = _config()
    uscite = [
        "provider_claude", "provider_subscription", "provider_openrouter",
        "provider_openai", "provider_ollama", "llm_strategy", "hide_free_models",
        "history_retention_days", "debug_expose_port",
    ]
    for nome_opzione in uscite:
        assert nome_opzione not in cfg["options"], nome_opzione
        assert nome_opzione not in cfg["schema"], nome_opzione
        for lingua in ("it", "en"):
            assert nome_opzione not in _traduzioni(lingua), (nome_opzione, lingua)
    # Le cinque ANNIDATE: il blocco `ponte:` per intero (tre voci), e le due
    # voci di `local_model:` che erano decisioni. Vanno guardate dentro il loro
    # gruppo, perche' come nomi di primo livello non ci sono mai state -- e un
    # test che le cercasse in cima passerebbe senza guardare niente.
    assert "ponte" not in cfg["options"] and "ponte" not in cfg["schema"]
    for lingua in ("it", "en"):
        assert "ponte" not in _traduzioni(lingua), lingua
    assert set(cfg["options"]["local_model"]) == {"url"}
    assert set(cfg["schema"]["local_model"]) == {"url"}
    for lingua in ("it", "en"):
        voci = _traduzioni(lingua)["local_model"]
        assert "model" not in voci and "request_timeout" not in voci, lingua

    # Il quinto posto, per le quattordici: `run.sh`. Le righe VIVE soltanto --
    # il commento in cima al file elenca apposta le variabili uscite, e
    # citarle non e' esportarle.
    run_sh_vivo = [r for r in (BASE / "run.sh").read_text(encoding="utf-8").splitlines()
                   if not r.lstrip().startswith("#")]
    for variabile in ("PROVIDER_CLAUDE", "PROVIDER_SUBSCRIPTION",
                      "PROVIDER_OPENROUTER", "PROVIDER_OPENAI", "PROVIDER_OLLAMA",
                      "LLM_STRATEGY", "HIRIS_HIDE_FREE_MODELS", "BRIDGE_ENABLED",
                      "BRIDGE_DEADLINE_MIN", "CHAT_DAILY_CAP", "LOCAL_MODEL_NAME",
                      "OLLAMA_REQUEST_TIMEOUT", "HISTORY_RETENTION_DAYS",
                      "HIRIS_DEBUG_EXPOSE_PORT"):
        assert not [r for r in run_sh_vivo if variabile in r], variabile


def test_la_pagina_add_on_tiene_solo_cio_che_si_custodisce():
    """Spec §4: le credenziali dove si custodiscono, le decisioni dove si
    prendono. Questo test e' l'elenco di cio' che RESTA, e si rompe se qualcuno
    ci rimette una decisione."""
    cfg = _config()
    assert set(cfg["options"]) == {
        "claude_api_key", "claude_code_oauth_token", "openrouter_api_key",
        "openai_api_key", "local_model", "theme", "memory",
        "log_level", "internal_token", "supervisor_ingress_cidr",
    }


def test_il_promemoria_della_porta_e_uscito_ma_il_meccanismo_no():
    """`debug_expose_port` non apriva niente: stampava sette righe di warning
    che spiegavano come aprire la porta a mano nella sezione Rete di Home
    Assistant. Un promemoria travestito da comando, con zero lettori nel
    codice.

    Cio' che apre davvero la porta -- `ports:` e la sua descrizione -- RESTA, e
    la descrizione ha dovuto assorbire l'avvertimento che il promemoria
    portava: senza, togliere l'opzione avrebbe tolto anche l'unico posto in cui
    il rischio era scritto."""
    cfg = _config()
    assert "8099/tcp" in cfg["ports"]
    descrizione = cfg["ports_description"]["8099/tcp"]
    assert "debug_expose_port" not in descrizione, (
        "la descrizione della porta manda ancora a cercare un'opzione che non "
        "esiste piu': e' lo stesso difetto del messaggio di primo avvio"
    )
    assert "LAN" in descrizione, (
        "la descrizione non dice piu' cosa comporta aprire la porta, e adesso "
        "e' l'unico posto che puo' dirlo"
    )


def test_run_sh_esporta_ogni_opzione_dell_addon():
    """Il quinto posto, quello che si dimentica: la catena e' `config.yaml` →
    `run.sh` → variabile d'ambiente maiuscola → lettore Python. Un'opzione
    aggiunta senza export non arriva mai al codice, e cercarne il nome
    minuscolo nel Python non lo rivela."""
    import re

    cfg = _config()
    attese = set()
    for nome, valore in cfg["options"].items():
        if isinstance(valore, dict):
            attese.update(f"{nome}.{figlio}" for figlio in valore)
        else:
            attese.add(nome)
    # Solo le righe VIVE: il commento che spiega perche' una chiave si e'
    # spostata cita la vecchia forma, e citarla non e' leggerla. (Stesso
    # criterio di `test_chat_policy_e_uscita_da_tutti_e_cinque_i_posti`.)
    run_sh_vivo = "\n".join(
        r for r in (BASE / "run.sh").read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith("#"))
    lette = set(re.findall(r"bashio::config\s+'([^']+)'", run_sh_vivo))
    assert not (attese - lette), (
        f"opzioni che run.sh non esporta, quindi invisibili al codice: "
        f"{sorted(attese - lette)}"
    )
    assert not (lette - attese), (
        f"run.sh esporta opzioni che config.yaml non ha piu': {sorted(lette - attese)}"
    )


@pytest.mark.parametrize("sezione", SEZIONI_ANNIDATE)
@pytest.mark.parametrize("lingua", ["it", "en"])
def test_dentro_una_sezione_le_etichette_non_ripetono_l_intestazione(lingua, sezione):
    """Il prefisso e l'intestazione fanno lo stesso lavoro: insieme lo fanno due
    volte. Fuori da una sezione il prefisso e' l'unico raggruppamento che il
    Supervisor mostra e quindi serve; dentro, lo porta gia' l'intestazione.

    Era scritto sulla sezione «Ponte», uscita per intero con la versione B.
    L'invariante non era del ponte: e' della nidificazione, ed e' su tutte e
    due le sezioni annidate rimaste che va guardato -- la prossima che nasce lo
    trovera' gia' scritto."""
    voce = _traduzioni(lingua)[sezione]
    intestazione = voce["name"]
    assert intestazione.strip(), f"la sezione '{sezione}' non ha un'intestazione"
    # La prima parola dell'intestazione, che e' quella che i figli non devono
    # ripetere («Ollama — dove sta» -> «Ollama», «Embedding — ...» ->
    # «Embedding»). Presa dal file invece che scritta qui: rinominare la
    # sezione non deve far passare il test per la ragione sbagliata.
    prima = intestazione.split()[0].lower().rstrip(":—-")
    # **G2 della revisione del commit 3.0.0: il dodicesimo
    # test-che-non-puo-fallire.** Qui c'era `startswith(prima + " ·")`. Ma il
    # `·` e' riservato alle opzioni di PRIMO livello («Provider · », «Avanzate
    # · ») -- lo dichiara il commento in cima a `it.yaml` -- e dentro le
    # sezioni si usa `—`. Il test era verde su tutte e quattro le
    # parametrizzazioni mentre in quattro casi su quattro la ripetizione che
    # vieta era presente («Ollama — indirizzo» sotto «Ollama — dove sta»,
    # «Embedding — provider (inattivo)» sotto «Embedding — oggi non hanno
    # effetto»): verde su dati che violano la sua stessa tesi.
    #
    # Il separatore NON si vincola: la ripetizione e' della prima parola, e
    # legare il test a un separatore e' esattamente cio' che lo ha reso cieco.
    # I quattro figli sono stati rinominati con la chiusura («Indirizzo»,
    # «Provider (inattivo)», «Modello (inattivo)») invece di dichiarare voluta
    # la ripetizione: dentro una sezione il raggruppamento lo porta gia'
    # l'intestazione, ed e' la regola che questo test esiste per difendere.
    ripetitivi = [
        chiave for chiave, figlio in voce.items()
        if isinstance(figlio, dict)
        and figlio["name"].strip().lower().startswith(prima)
    ]
    assert not ripetitivi, (
        f"{lingua}.yaml: dentro la sezione «{intestazione}» queste voci "
        f"ripetono il prefisso che l'intestazione porta gia': {ripetitivi}"
    )
