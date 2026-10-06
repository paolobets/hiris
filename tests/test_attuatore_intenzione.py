"""L'`intenzione` dell'attuatore ha la forma che l'officina accetta (Tappa 6,
Task 5, D5 approvata il 05/10/2026).

Misurato sul commit di partenza `5bce65d`: il contratto dell'attuatore
(`mind/proposer_turn.ANSWER_CONTRACT`) chiedeva l'innesco come FRASE e
«richiesto» libero, mentre `workshop.propose` -- e lo schema dello strumento
`propose` (`home_space/tools.PROPOSE_TOOL_DEF`) -- vogliono l'innesco come
LISTA di oggetti e «richiesto» da un vocabolario chiuso. L'esempio del
contratto, passato da `workshop._invalid_form`, era rifiutato con ««innesco»
deve essere una lista, non str.»: **ogni proposta costruibile dell'attuatore
era rifiutata dalla forma**, dopo aver speso il turno.

Il contratto adesso si DERIVA dallo schema (e dai vocabolari chiusi che
l'officina impone), e la risposta si valida con la stessa porta
dell'officina PRIMA di arrivarci. Le prove chiedono allo schema, non a una
lista ricopiata.

Mutazioni ESEGUITE (05/10/2026), ciascuna poi ripristinata e verificata con
`git status`:
- sul contratto di partenza: rosse le prove dell'esempio («innesco» deve essere
  una lista, non str.), dei campi e di «richiesto» -- il rosso del TDD;
- aggiunto «helper_x» a `advisor.STRUCTURES` (il vocabolario di «richiesto»
  nello schema): il contratto lo nomina senza toccare ne' il contratto ne' le
  prove, che restano verdi;
- la stessa mutazione con le alternative di «richiesto» ricopiate a mano nel
  contratto: rossa la prova di «richiesto» -- la derivazione e' cio' che la
  tiene verde;
- tolta la validazione con la porta dell'officina da `apply_actuation`: rossa
  la prova dell'intenzione invalida (l'esito passava).
"""
import json
import re

from hiris.app.action.construction.workshop import _invalid_form, form_refusal
from hiris.app.home_space.tools import PROPOSE_TOOL_DEF
from hiris.app.mind import proposer_turn as at
from hiris.app.proxy.ha_client import HAClient

_SCHEMA = PROPOSE_TOOL_DEF["input_schema"]
_TOKEN = r'(?:"[^"]*"|true|false|\.\.\.)'
_ALTERNATIVES = re.compile(rf"({_TOKEN})(?:\s*\|\s*{_TOKEN})+")


def _intent_block() -> str:
    """Il testo dell'oggetto `intenzione` dentro il contratto, parentesi
    comprese."""
    text = at.ANSWER_CONTRACT
    start = text.index('"intenzione":')
    start = text.index("{", start)
    depth = 0
    for position in range(start, len(text)):
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                return text[start:position + 1]
    raise AssertionError("l'intenzione del contratto non si chiude")


def _intent_example() -> dict:
    """L'esempio del contratto come dato: di ogni `a | b | ...` resta la prima
    alternativa, che e' quella che un modello copierebbe."""
    return json.loads(_ALTERNATIVES.sub(r"\1", _intent_block()))


def _alternatives(field: str) -> list[str]:
    match = re.search(rf'"{field}":\s*({_TOKEN}(?:\s*\|\s*{_TOKEN})*)', _intent_block())
    assert match, f"il contratto non nomina «{field}»"
    return [json.loads(token) for token in re.findall(r'"[^"]*"', match.group(1))]


def test_l_ESEMPIO_del_contratto_passa_dalla_porta_dell_officina():
    """Il cuore di D5: cio' che il contratto insegna al modello e' cio' che
    l'officina accetta. Prima `_invalid_form` (la porta della forma), poi la
    porta intera con gesto e dominio."""
    example = _intent_example()
    assert _invalid_form(example) is None, _invalid_form(example)
    assert form_refusal(example, HAClient.CONFIGURABLE_DOMAINS) is None


def test_il_contratto_porta_ogni_campo_dello_schema_salvo_quelli_esclusi():
    """La derivazione: un campo nuovo nello schema entra nel contratto da
    solo. E la prova che la derivazione non si e' rotta: i campi trovati sono
    piu' dei due obbligatori."""
    example = _intent_example()
    expected = set(_SCHEMA["properties"]) - set(at.INTENT_EXCLUDED)
    assert set(example) == expected
    assert len(expected) > len(_SCHEMA["required"])
    for field in _SCHEMA["required"]:
        assert field in example


def test_RICHIESTO_offre_esattamente_il_vocabolario_dello_schema():
    assert _alternatives("richiesto") == list(_SCHEMA["properties"]["richiesto"]["enum"])


def test_GESTO_e_DOMINIO_offrono_i_vocabolari_che_l_officina_impone():
    """Lo schema li descrive a parole; l'officina li impone
    (`OPERATIONS`, `HAClient.CONFIGURABLE_DOMAINS`). Il contratto offre
    quelli imposti, chiesti all'officina."""
    from hiris.app.action.construction.workshop import OPERATIONS
    assert _alternatives("gesto") == list(OPERATIONS)
    assert _alternatives("dominio") == list(HAClient.CONFIGURABLE_DOMAINS)


def _osservazioni():
    return [{"soggetto": "dev1", "misura": "prelievo", "chiave": None, "innesco": 1,
             "base": 19, "cosa": "il prelievo si stacca dal solito",
             "cosa_cambierebbe": "spostare i consumi nelle ore di sole"}]


def _proposta(intenzione):
    return json.dumps({"esiti": [{
        "osservazione": 0, "gesto": "proposta", "trovato": "una regola alle 14",
        "costruibile": True, "intenzione": intenzione}]})


def test_un_INTENZIONE_che_l_officina_rifiuterebbe_e_un_esito_motivato():
    """L'innesco come frase -- la forma che il vecchio contratto chiedeva --
    si rifiuta QUI, col motivo dell'officina, e non dopo aver chiamato
    `workshop.propose`. Non e' un'eccezione: e' un problema fra i problemi."""
    esito = at.apply_actuation(_osservazioni(), _proposta(
        {"gesto": "crea", "dominio": "automation", "innesco": "alle 14"}))
    assert esito["attuazione"] is None
    assert any("«innesco» deve essere una lista" in p for p in esito["problemi"]), \
        esito["problemi"]


def test_un_DOMINIO_che_l_officina_non_sa_costruire_si_rifiuta():
    esito = at.apply_actuation(_osservazioni(), _proposta(
        {"gesto": "crea", "dominio": "light"}))
    assert esito["attuazione"] is None
    assert any("non so costruire" in p for p in esito["problemi"]), esito["problemi"]


def test_un_INTENZIONE_con_la_forma_giusta_passa():
    esito = at.apply_actuation(_osservazioni(), _proposta(
        {"gesto": "crea", "dominio": "automation",
         "innesco": [{"trigger": "time", "at": "14:00:00"}],
         "azioni": [{"action": "switch.turn_on",
                     "target": {"entity_id": "switch.lavatrice"}}]}))
    assert esito["problemi"] == []
    assert esito["attuazione"]["esiti"][0]["intenzione"]["gesto"] == "crea"
