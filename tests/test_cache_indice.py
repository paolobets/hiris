"""La cache del Lookup (Task B7) -- un oggetto di vita lunga separato da
`costruisci_indice()`, che resta pura.

Ogni test qui sotto esiste per una mutazione plausibile dichiarata nel brief
(`.superpowers/sdd/conoscenza/task-B7-brief.md`, sezione "Come si prova che i
test valgono"): il commento sopra ogni test dice quale.
"""
from hiris.app.memory.lookup_cache import LookupCache
from hiris.app.memory.resolver import Lookup


def _casa(entita=()):
    return {"aree": [], "dispositivi": [], "entita": list(entita)}


def _entita(id_, nome=None):
    return {"id": id_, "nome": nome, "alias": []}


# -- conta le costruzioni, non solo i risultati ----------------------------
# Mutazione: "non usare mai la cache anche quando c'e' (il guadagno sparisce
# e nessun test se ne accorge, se i test guardano solo i risultati e non
# quante volte si costruisce)". Questo test conta le costruzioni con uno spia
# su `costruisci_indice`, non sul risultato di `find()`.

def test_due_richieste_identiche_costruiscono_un_solo_indice(monkeypatch):
    chiamate = []
    from hiris.app.memory import lookup_cache as modulo

    originale = modulo.costruisci_indice

    def spia(casa, nomi=None, comportamento=None):
        chiamate.append(1)
        return originale(casa, nomi, comportamento)

    monkeypatch.setattr(modulo, "costruisci_indice", spia)

    cache = LookupCache()
    casa = _casa([_entita("light.a", "Luce A")])
    i1 = cache.get("cerca", casa, "2026-01-01", {})
    i2 = cache.get("cerca", casa, "2026-01-01", {})
    assert len(chiamate) == 1
    assert i1 is i2


# -- l'anagrafe cambia -> ricostruito ---------------------------------------
# Mutazione: "togliere aggiornata_il() dalla chiave".

def test_cambia_aggiornata_il_ricostruisce(monkeypatch):
    chiamate = []
    from hiris.app.memory import lookup_cache as modulo
    originale = modulo.costruisci_indice

    def spia(casa, nomi=None, comportamento=None):
        chiamate.append(1)
        return originale(casa, nomi, comportamento)

    monkeypatch.setattr(modulo, "costruisci_indice", spia)

    cache = LookupCache()
    casa_v1 = _casa([_entita("light.a", "Luce A")])
    casa_v2 = _casa([_entita("light.a", "Luce A"), _entita("light.b", "Luce B")])
    i1 = cache.get("cerca", casa_v1, "2026-01-01", {})
    i2 = cache.get("cerca", casa_v2, "2026-01-02", {})
    assert len(chiamate) == 2
    assert i1 is not i2
    # il contenuto e' davvero quello nuovo, non solo un oggetto diverso
    assert i2.verify("entita", "light.b") is not None
    assert i1.verify("entita", "light.b") is None


# -- i nomi vivi cambiano -> ricostruito, per CONTENUTO ---------------------
# Mutazione: "usare la lunghezza dei nomi invece di un'impronta del
# contenuto". Qui i due dizionari hanno la STESSA lunghezza (1 voce) ma
# contenuto diverso: una chiave basata sulla lunghezza li confonderebbe.

def test_stesso_numero_di_nomi_ma_contenuto_diverso_ricostruisce():
    cache = LookupCache()
    casa = _casa([_entita("light.a", None)])  # senza nome nel registro
    nomi_v1 = {"light.a": "Abat-jour"}
    nomi_v2 = {"light.a": "Lampada"}  # stessa lunghezza (1 voce), nome diverso
    i1 = cache.get("cerca", casa, "2026-01-01", nomi_v1)
    i2 = cache.get("cerca", casa, "2026-01-01", nomi_v2)
    assert i1 is not i2
    assert i1.find("abat-jour")[0]["candidati"][0]["riferimento"] == "light.a"
    assert i2.find("abat-jour") == []
    assert i2.find("lampada")[0]["candidati"][0]["riferimento"] == "light.a"


# -- la cache non e' eterna --------------------------------------------------
# Mutazione: "non invalidare mai (cache eterna)". Cambiando SIA l'anagrafe
# SIA i nomi contemporaneamente, una cache eterna servirebbe comunque il
# primo indice.

def test_non_e_eterna_cambia_e_si_accorge():
    cache = LookupCache()
    casa_v1 = _casa([_entita("light.a", "Luce A")])
    casa_v2 = _casa([_entita("light.c", "Luce C")])
    i1 = cache.get("cerca", casa_v1, "t1", {})
    i2 = cache.get("cerca", casa_v2, "t2", {"x": "y"})
    assert i1 is not i2
    assert i2.verify("entita", "light.a") is None
    assert i2.verify("entita", "light.c") is not None


# -- il comportamento cambia -> ricostruito (T7, R2) ------------------------
# Mutazione (dal brief del task): "togliere `comportamento_letto_il` dalla
# chiave". Stesso `aggiornata_il` (l'anagrafe non e' cambiata), stessa
# `casa`: solo il comportamento -- e la sua data di rilettura -- cambiano.
# Un'automazione rinominata deve invalidare l'indice come fa un'area
# rinominata, non restare invisibile finche' l'anagrafe non cambia anche lei
# (potrebbe non succedere mai nello stesso turno).

def test_cambia_comportamento_letto_il_ricostruisce(monkeypatch):
    chiamate = []
    from hiris.app.memory import lookup_cache as modulo
    originale = modulo.costruisci_indice

    def spia(casa, nomi=None, comportamento=None):
        chiamate.append(1)
        return originale(casa, nomi, comportamento)

    monkeypatch.setattr(modulo, "costruisci_indice", spia)

    cache = LookupCache()
    casa = _casa()
    comportamento_v1 = [{"id": "automation.x", "tipo": "automazione", "nome": "Vecchio nome"}]
    comportamento_v2 = [{"id": "automation.x", "tipo": "automazione", "nome": "Nuovo nome"}]
    i1 = cache.get("cerca", casa, "t1", {}, comportamento_v1, "c1")
    i2 = cache.get("cerca", casa, "t1", {}, comportamento_v2, "c2")
    assert len(chiamate) == 2
    assert i1 is not i2
    # il contenuto e' davvero quello nuovo, non solo un oggetto diverso
    assert i1.find("vecchio nome") != []
    assert i2.find("vecchio nome") == []
    assert i2.find("nuovo nome") != []


def test_stesso_comportamento_letto_il_riusa_lindice():
    """Il rovescio: se NE' l'anagrafe NE' il comportamento sono cambiati, si
    riusa -- il guadagno della cache non deve sparire perche' ora la chiave
    ha un componente in piu'."""
    cache = LookupCache()
    casa = _casa()
    comportamento = [{"id": "automation.x", "tipo": "automazione", "nome": "Sveglia"}]
    i1 = cache.get("cerca", casa, "t1", {}, comportamento, "c1")
    i2 = cache.get("cerca", casa, "t1", {}, comportamento, "c1")
    assert i1 is i2


# -- il ramo "anagrafe non letta" non si confonde con quello pieno ---------
# Mutazione: "condividere lo stesso indice fra il ramo anagrafe letta e non
# letta". `aggiornata_il=None` (non letta) e un valore vero non devono MAI
# dare lo stesso indice, anche passando la stessa identica `casa={}`.

def test_anagrafe_non_letta_non_si_confonde_con_anagrafe_vuota_letta_davvero():
    cache = LookupCache()
    vuota = _casa([])
    i_non_letta = cache.get("ricorda", vuota, None)
    i_letta_vuota = cache.get("ricorda", vuota, "2026-01-01")
    assert i_non_letta is not i_letta_vuota


# -- _cerca e _ricorda non si scambiano indici -------------------------------
# Mutazione: "condividere lo stesso indice fra _cerca (con nomi di ripiego) e
# _ricorda (senza)". Stessa `casa`, stesso `aggiornata_il`: l'unica
# differenza e' lo `spazio` e i nomi di ripiego -- devono restare due voci.

def test_cerca_e_ricorda_non_condividono_lo_stesso_indice():
    cache = LookupCache()
    casa = _casa([_entita("light.a", None)])
    nomi_vivi = {"light.a": "Abat-jour"}
    i_cerca = cache.get("cerca", casa, "2026-01-01", nomi_vivi)
    i_ricorda = cache.get("ricorda", casa, "2026-01-01")
    assert i_cerca is not i_ricorda
    # e il contenuto e' davvero diverso: solo "cerca" vede l'abat-jour
    assert i_cerca.find("abat-jour") != []
    assert i_ricorda.find("abat-jour") == []


# -- una voce per chiave, non una sola casella -------------------------------
# Mutazione: "tenere una sola casella invece di una voce per chiave (il
# rimbalzo fra i due chiamanti)". Alternare cerca/ricorda a stato invariato
# non deve MAI ricostruire: con una sola casella condivisa, la seconda
# chiamata a "cerca" dopo un giro su "ricorda" rimbalzerebbe e ricostruirebbe.

def test_alternare_cerca_e_ricorda_non_fa_rimbalzare_la_cache(monkeypatch):
    chiamate = []
    from hiris.app.memory import lookup_cache as modulo
    originale = modulo.costruisci_indice

    def spia(casa, nomi=None, comportamento=None):
        chiamate.append(1)
        return originale(casa, nomi, comportamento)

    monkeypatch.setattr(modulo, "costruisci_indice", spia)

    cache = LookupCache()
    casa = _casa([_entita("light.a", "Luce A")])
    a1 = cache.get("cerca", casa, "t1", {})
    r1 = cache.get("ricorda", casa, "t1")
    a2 = cache.get("cerca", casa, "t1", {})
    r2 = cache.get("ricorda", casa, "t1")
    assert len(chiamate) == 2  # una per spazio, non quattro
    assert a1 is a2
    assert r1 is r2


def test_e_davvero_un_oggetto_indice():
    cache = LookupCache()
    esito = cache.get("cerca", _casa(), "t1", {})
    assert isinstance(esito, Lookup)
