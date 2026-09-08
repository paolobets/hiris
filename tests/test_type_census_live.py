"""L'istantaneo del pubblicato e' ancora quello di QUESTA casa?

**E' l'altro fallimento, e non e' lo stesso di `test_type_census.py`.** Quello
dice *«il vocabolario non copre cio' che Home Assistant pubblica»* -- e allora
qualcuno deve decidere. Questo dice *«l'istantaneo non e' piu' quello di questa
casa»* -- e allora l'istantaneo va rifatto, e solo dopo si guarda cosa il
censore ne tira fuori. Confonderli farebbe leggere «decidi» dove la risposta e'
«rileggi», che e' il difetto ricorrente di questa codebase applicato a una
prova.

**Gira solo quando la casa risponde**, perche' la suite gira senza la casa e
nessuna prova puo' dipendere dalla rete. Le condizioni sono due, ed e' un
salto -- non un fallimento -- quando mancano:

- la casa e' dichiarata: `HIRIS_HOUSE_URL`, piu' un segno di riconoscimento in
  `HIRIS_HOUSE_TOKEN` o nel file `HIRIS_HOUSE_TOKEN_FILE` (`~/.ha-token` se
  non si dice altro);
- la casa risponde davvero.

Il segno di riconoscimento non compare mai in un messaggio di questa prova:
si legge, si usa, non si stampa.
"""
import asyncio
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import istantaneo_pubblicato as istantaneo

from hiris.app.home_space import type_census


@pytest.fixture(scope="module")
def casa_viva():
    """La lettura della casa vera, o un salto col motivo."""
    url, token = istantaneo.house_url(), istantaneo.house_token()
    if not url or not token:
        pytest.skip("nessuna casa dichiarata (HIRIS_HOUSE_URL e il segno di "
                    "riconoscimento): la suite gira senza la casa")
    try:
        return asyncio.run(istantaneo.read_house(url, token))
    except istantaneo.ReadingFailed as failure:
        pytest.skip(f"la casa non risponde: {failure}")


def test_l_istantaneo_versionato_e_ancora_quello_di_questa_casa(casa_viva):
    """Un istantaneo scaduto non e' un difetto del vocabolario: e' un difetto
    dell'istantaneo, e la differenza fra i due e' tutta questa prova.

    Quando fallisce, il rimedio e' una riga:
    `python scripts/istantaneo_pubblicato.py --scrivi`, poi si guarda cosa il
    censore nomina di nuovo -- **prima si rilegge, poi si decide.**

    Due mutazioni ESEGUITE, e la seconda e' quella che conta:

    1. togliere un dominio da `tests/data/pubblicato-dalla-casa.json` -- la
       prova arrossisce nominando la materia «domini»;
    2. in `scripts/istantaneo_pubblicato.py::distill`, costruire i domini
       leggendo solo le traduzioni (senza i domini VIVI) -- `conversation` e
       `zone` hanno entita' in questa casa e nessuna chiave
       `entity_component`, quindi sparirebbero dalla lettura, e la prova
       arrossisce lo stesso. E' il difetto che la ricognizione aveva
       nominato: un istantaneo dei soli domini tradotti perde proprio quelli
       che nessuno traduce.

    **Una terza prova e' stata scritta e poi TOLTA**: confrontava
    `undecided()` sulla lettura viva con `undecided()` sull'istantaneo. Non
    poteva fallire da sola -- se le sei materie coincidono (ed e' questa prova
    a pretenderlo) i due censimenti coincidono per costruzione. Una prova che
    non puo' arrossire e' il difetto n.1 delle prove di questo progetto, e
    tenerla avrebbe dato l'impressione di una copertura in piu' che non c'era.
    """
    versionato = istantaneo.stored_snapshot()
    diverse = [subject.value for subject, key in type_census.SNAPSHOT_KEYS.items()
               if versionato.get(key) != casa_viva.get(key)]
    assert not diverse, (
        f"l'istantaneo del {versionato.get(type_census.SNAPSHOT_READ_ON)} non e' piu' "
        f"quello di questa casa (HA {casa_viva.get(type_census.SNAPSHOT_HA_VERSION)}): "
        f"e' cambiato in {', '.join(diverse)}. Rigeneralo con "
        "`python scripts/istantaneo_pubblicato.py --scrivi`, POI guarda cosa il "
        "censore nomina di nuovo -- prima si rilegge, poi si decide.")


def test_l_istantaneo_e_questa_fixture_nominano_gli_stessi_stati(casa_viva):
    """R5 (revisione del tratto v3.23.0..HEAD, 08/09/2026): `tests/_house_
    translations.py` affermava di «rigenerarsi con la casa» tramite
    `scripts/istantaneo_pubblicato.py`. Non e' vero: quello script scrive
    SOLO `tests/data/pubblicato-dalla-casa.json`, mai `_house_translations.py`,
    e prima di questa prova nessuna verifica dal vivo confrontava le PAROLE
    (o anche solo gli stati) di quella fixture con la casa vera -- la prova
    qui sopra confronta le SEI MATERIE dell'istantaneo, che non portano
    parole.

    Questa prova chiude la meta' verificabile del limite: non le parole
    italiane (`frontend/get_translations` non e' riletto qui, e non lo sara'
    finche' nessuna prova ne ha bisogno per altro), ma la STRUTTURA -- quali
    stati esistono, per quale tipo. Se Home Assistant aggiunge o toglie uno
    stato a un dominio che questa fixture nomina, questa prova lo dice; se
    Home Assistant cambia solo la PAROLA di uno stato esistente (misurato:
    e' il caso reale che ha motivato R5, `triggered` -> «Scattato»), questa
    prova resta verde e la fixture invecchia in silenzio -- limite dichiarato,
    non chiuso.

    Mutazione ESEGUITA: in `tests/_house_translations.derived_state_keys`,
    aggiungere uno stato inventato (`"component.light.entity_component._.
    state.sfarfallio": "Sfarfallio"`) a `PUBLISHED_STATE_WORDS` -- la prova
    arrossisce nominando `light` e lo stato in piu' che l'istantaneo non ha.
    """
    from tests._house_translations import derived_state_keys

    derivati = derived_state_keys()
    live = casa_viva.get("stati_per_tipo") or {}
    diverse = []
    for domain, per_class in derivati.items():
        for device_class, states in per_class.items():
            live_states = set(live.get(domain, {}).get(device_class, []))
            solo_fixture = set(states) - live_states
            solo_casa = live_states - set(states)
            if solo_fixture or solo_casa:
                diverse.append(f"{domain}.{device_class}: solo fixture={sorted(solo_fixture)}, "
                               f"solo casa={sorted(solo_casa)}")
    assert not diverse, (
        "gli stati di `_house_translations.py` non coincidono piu' con quelli "
        "che la casa pubblica -- corregere la fixture a mano:\n  "
        + "\n  ".join(diverse))


def test_la_casa_e_la_stessa_versione_e_la_stessa_lingua(casa_viva):
    """Le due cose che fanno invecchiare una tabella di traduzioni, e che
    l'istantaneo porta con se' per la stessa ragione per cui `PublishedTypes`
    le porta: una tabella che non sa di quale casa e' non si sa vecchia.

    Mutazione ESEGUITA: cambiare `versione_ha` in `2026.8.0` nell'istantaneo
    versionato -- la prova arrossisce sulle due versioni affiancate.
    """
    versionato = istantaneo.stored_snapshot()
    assert (versionato.get(type_census.SNAPSHOT_HA_VERSION),
            versionato.get(type_census.SNAPSHOT_LANGUAGE)) == (
        casa_viva.get(type_census.SNAPSHOT_HA_VERSION),
        casa_viva.get(type_census.SNAPSHOT_LANGUAGE))


def test_l_istantaneo_versionato_e_json_leggibile():
    """Gira SEMPRE, casa o non casa: un istantaneo illeggibile farebbe saltare
    la prova viva (che salta quando la casa non c'e') e passare quella cieca
    per il motivo sbagliato.

    Mutazione ESEGUITA: scrivere `{` dentro il file -- la prova arrossisce con
    un `JSONDecodeError`.
    """
    letto = json.loads(istantaneo.SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert set(type_census.SNAPSHOT_KEYS.values()) <= set(letto)
