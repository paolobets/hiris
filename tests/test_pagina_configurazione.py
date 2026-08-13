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
"""
from pathlib import Path

import pytest
import yaml

BASE = Path(__file__).resolve().parents[1] / "hiris"

# Ogni interruttore e la credenziale senza cui non fa niente. Il Supervisor non
# sa disabilitare un campo finche' un altro non e' valorizzato: l'unica cosa
# che possiamo fare per chi accende un provider e' che trovi SUBITO DOPO il
# posto dove incollare la chiave.
INTERRUTTORE_E_CREDENZIALE = [
    ("provider_claude", "claude_api_key"),
    ("provider_subscription", "claude_code_oauth_token"),
    ("provider_openrouter", "openrouter_api_key"),
    ("provider_openai", "openai_api_key"),
    ("provider_ollama", "local_model"),
]

# Toccarle senza sapere cosa si fa apre la API di HIRIS sulla rete locale.
# Il Supervisor non sa marcare un campo come pericoloso: stare in fondo, e il
# prefisso «Avanzate · » nell'etichetta, sono l'unico segnale disponibile.
IN_FONDO_PERCHE_PERICOLOSE = [
    "log_level",
    "internal_token",
    "supervisor_ingress_cidr",
    "debug_expose_port",
]


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


@pytest.mark.parametrize("interruttore,credenziale", INTERRUTTORE_E_CREDENZIALE)
def test_ogni_provider_ha_la_sua_credenziale_subito_sotto(interruttore, credenziale):
    ordine = list(_config()["options"])
    i, c = ordine.index(interruttore), ordine.index(credenziale)
    assert c == i + 1, (
        f"'{credenziale}' non e' piu' subito sotto '{interruttore}' "
        f"(posizioni {i} e {c}): chi accende il provider non trova dove "
        "mettere la credenziale, ed e' il difetto che la 2.3.0 ha chiuso"
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


def test_il_ponte_ha_un_interruttore_solo():
    """La fine di una storia lunga tre versioni.

    Erano due leve che dovevano essere accese insieme (`bridge_enabled` e
    `chat_via_subscription`, `_chat_subscription_active` = AND). La 2.2.1 le
    aveva rese adiacenti, la 2.3.x le aveva chiamate «(1 di 2)» e «(2 di 2)»;
    la 2.4.0 le fonde, perche' non erano due decisioni. Questo test e' l'unico
    posto che impedisce alla seconda leva di ricomparire dalla porta di
    servizio: una nuova opzione booleana dentro `ponte:` sarebbe di nuovo un
    interruttore da tenere allineato a mano.
    """
    ponte = _config()["options"]["ponte"]
    interruttori = [k for k, v in ponte.items() if isinstance(v, bool)]
    assert interruttori == ["attivo"], (
        f"il ponte deve avere un interruttore solo, e chiamarsi «attivo»: {interruttori}"
    )
    assert "bridge_enabled" not in ponte and "chat_via_subscription" not in ponte


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_l_etichetta_del_ponte_non_dice_piu_di_essere_una_meta(lingua):
    """«(1 di 2)» e «(2 di 2)» erano la cura per una malattia -- due leve da
    accendere insieme -- e se ne vanno con lei. Un nome deve dire cosa fa
    l'interruttore, non che e' un pezzo di qualcos'altro."""
    ponte = _traduzioni(lingua)["ponte"]
    nome = ponte["attivo"]["name"]
    assert nome.strip()
    for meta in ("(1 di 2)", "(2 di 2)", "(1 of 2)", "(2 of 2)"):
        assert meta not in nome, (
            f"{lingua}.yaml: «{meta}» e' tornata in «{nome}», ma il ponte "
            "e' un interruttore solo: quel marcatore descriveva una coppia"
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
    # criterio di `test_prompt_azione._testi_che_legge_l_utente`.)
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


@pytest.mark.parametrize("lingua,prefisso", [("it", "Ponte"), ("en", "Bridge")])
def test_dentro_la_sezione_ponte_le_etichette_non_ripetono_l_intestazione(lingua, prefisso):
    """Il prefisso e l'intestazione fanno lo stesso lavoro: insieme lo fanno due
    volte. Fuori da una sezione il prefisso e' l'unico raggruppamento che il
    Supervisor mostra e quindi serve; dentro, lo porta gia' l'intestazione."""
    ponte = _traduzioni(lingua)["ponte"]
    assert prefisso.lower() in ponte["name"].lower(), (
        "l'intestazione della sezione non nomina piu' il ponte: se sparisce da "
        "li', i nomi dei figli restano senza contesto"
    )
    ripetitivi = [
        chiave for chiave, voce in ponte.items()
        if isinstance(voce, dict) and voce["name"].strip().lower().startswith(prefisso.lower() + " ·")
    ]
    assert not ripetitivi, (
        f"{lingua}.yaml: dentro la sezione «{ponte['name']}» queste voci "
        f"ripetono il prefisso che l'intestazione porta gia': {ripetitivi}"
    )
