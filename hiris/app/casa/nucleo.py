"""Il nucleo -- il testo che il modello ha SEMPRE davanti.

E' il punto in cui muore la sovrapposizione n.1 della mappa del prodotto:
oggi la chat riceve una mappa senza il ritratto, il Brain il ritratto senza
la mappa -- due intelligenze nella stessa casa che ne vedono due diverse
(vedi docs/design/2026-08-05-la-conoscenza-di-hiris.md, §7). Il nucleo e'
**lo stesso per chiunque ragioni**: chat, Brain, agenti.

Con trecento entita' elencarle tutte sfonderebbe il contesto a ogni
messaggio: il nucleo CONTA, non elenca -- "Cucina: 2 luci, 1 sensore", non i
loro `entity_id`. L'unica eccezione sono i ricordi: sono pochi, ed e' l'unica
cosa che non si puo' andare a cercare -- se il modello dovesse *ricordarsi*
di cercarli, se ne dimenticherebbe. Entrano interi.

`componi()` e' PURA: prende dati gia' letti dal chiamante (l'anagrafe, il
comportamento, i ricordi, lo stato vivo) e non apre archivi ne' chiama la
rete. E' cio' che la rende verificabile senza finti elaborati -- vedi
tests/test_nucleo.py.

**Un nucleo troncato in silenzio e' un HIRIS che crede di sapere.** Quando il
tetto di caratteri costringe a tagliare, il taglio e' scritto DENTRO il
nucleo (sezione 5, "cio' che HIRIS ignora"), non solo in un riepilogo che
nessuno legge -- e si tagliano per ultimi i ricordi, perche' sono l'unica
cosa irrecuperabile: la casa e il comportamento si rileggono da Home
Assistant, un ricordo scartato senza dirlo e' perso per sempre.
"""
from __future__ import annotations

from .anagrafe import gerarchia

# Il TIPO di un'entita' si ricava dal dominio del suo entity_id (la parte
# prima del punto) -- lo dichiara Home Assistant nell'id stesso, non un
# elenco nostro. Questa mappa serve solo a renderlo leggibile in italiano
# (singolare, plurale: "1 luce" e non "1 luci" -- il nucleo lo legge anche
# una persona, vedi il brief); un dominio che non conosciamo resta visibile
# col proprio nome invece di sparire, cosi' un tipo nuovo si legge diverso
# ma non si perde.
_NOMI_DOMINIO = {
    "light": ("luce", "luci"),
    "switch": ("interruttore", "interruttori"),
    "sensor": ("sensore", "sensori"),
    "binary_sensor": ("sensore binario", "sensori binari"),
    "cover": ("tapparella", "tapparelle"),
    "climate": ("termostato", "termostati"),
    "lock": ("serratura", "serrature"),
    "fan": ("ventola", "ventole"),
    "media_player": ("lettore multimediale", "lettori multimediali"),
    "camera": ("telecamera", "telecamere"),
    "vacuum": ("aspirapolvere", "aspirapolvere"),
    "alarm_control_panel": ("pannello allarme", "pannelli allarme"),
    "automation": ("automazione", "automazioni"),
    "script": ("script", "script"),
    "scene": ("scena", "scene"),
    "person": ("persona", "persone"),
    "input_boolean": ("interruttore helper", "interruttori helper"),
}

# Stati che rendono un'entita' NOTEVOLE adesso: acceso, aperto, in allarme.
# Il resto e' rumore in una casa da trecento entita' -- una temperatura di
# 19.5 non e' notevole solo perche' e' un numero, uno stato "on"/"open" lo e'
# perche' e' un'eccezione rispetto al riposo.
_STATI_NOTEVOLI = {
    "on", "open", "unlocked", "home", "playing", "alarm", "triggered",
    "detected", "problem", "unavailable", "cleaning",
}

_TRADUZIONE_STATO = {
    "on": "acceso", "off": "spento", "open": "aperta", "closed": "chiusa",
    "home": "in casa", "not_home": "fuori casa", "unlocked": "sbloccata",
    "locked": "bloccata", "playing": "in riproduzione", "paused": "in pausa",
    "unavailable": "non disponibile", "detected": "rilevato",
    "problem": "in problema", "triggered": "in allarme",
}

# "on"/"off" non bastano per una porta o una finestra: "acceso"/"spento"
# affermerebbe un'alimentazione che l'oggetto non ha. Per queste classi
# (dichiarate da Home Assistant, non indovinate dal nome) si traduce come
# apertura -- vedi `_traduci_stato`.
_CLASSI_APERTURA = {"door", "window", "garage_door", "opening", "damper"}

# Il buffer riservato alla sezione "cio' che HIRIS ignora": deve poter contenere
# l'avviso di taglio anche quando il taglio e' avvenuto, quindi si sottrae
# dal budget PRIMA di tagliare, non dopo -- altrimenti l'avviso stesso
# rischierebbe di essere cio' che sfonda il tetto.
_RISERVA_SEZIONE_LACUNE = 400


def _dominio(entity_id: str) -> str:
    return entity_id.split(".", 1)[0] if "." in entity_id else entity_id


def _nome_dominio(dominio: str, n: int) -> str:
    coppia = _NOMI_DOMINIO.get(dominio)
    if coppia is None:
        return dominio
    singolare, plurale = coppia
    return singolare if n == 1 else plurale


def _plurale(n: int, singolare: str, plurale: str) -> str:
    return singolare if n == 1 else plurale


def _traduci_stato(valore, classe: str | None = None) -> str:
    v = str(valore).lower()
    if classe in _CLASSI_APERTURA:
        if v == "on":
            return "aperto"
        if v == "off":
            return "chiuso"
    return _TRADUZIONE_STATO.get(v, str(valore))


def _conta_per_dominio(entita: list[dict]) -> dict[str, int]:
    conteggio: dict[str, int] = {}
    for e in entita:
        dominio = _dominio(e["id"])
        conteggio[dominio] = conteggio.get(dominio, 0) + 1
    # Ordine alfabetico sul dominio: stabile, non dipende dall'ordine in cui
    # i registri sono stati letti o restituiti.
    return {dominio: conteggio[dominio] for dominio in sorted(conteggio)}


def _righe_casa(casa: dict) -> list[str]:
    """Piano per piano, area per area: quante entita' per tipo. Non i nomi
    -- vedi il docstring del modulo sul perche'."""
    piani = gerarchia(casa)
    if not piani:
        return ["Nessun piano registrato."]
    righe = []
    for piano in piani:
        righe.append(f"{piano['nome']}:")
        if not piano["aree"]:
            righe.append("  - (nessuna area)")
            continue
        for area in piano["aree"]:
            conteggio = _conta_per_dominio(area["entita"])
            if conteggio:
                dettaglio = ", ".join(
                    f"{n} {_nome_dominio(dom, n)}" for dom, n in conteggio.items())
            else:
                dettaglio = "nessuna entita'"
            righe.append(f"  - {area['nome']}: {dettaglio}")
    return righe


def _righe_notevole(casa: dict, stato: dict) -> list[str]:
    """Cio' che e' notevole ADESSO: acceso, aperto, in allarme. Serve lo
    stato vivo, che arriva dal chiamante -- il nucleo non lo va a cercare."""
    aree_nome = {a["id"]: a["nome"] for a in casa.get("aree", [])}
    area_del_dispositivo = {d["id"]: d.get("area_id") for d in casa.get("dispositivi", [])}
    righe = []
    for e in casa.get("entita", []):
        if e.get("disabilitata"):
            continue
        entity_id = e["id"]
        if entity_id not in stato:
            continue
        valore = stato[entity_id]
        if str(valore).lower() not in _STATI_NOTEVOLI:
            continue
        area_id = e.get("area_id") or area_del_dispositivo.get(e.get("dispositivo_id"))
        area_nome = aree_nome.get(area_id) if area_id else None
        prefisso = f"{area_nome}: " if area_nome else ""
        stato_leggibile = _traduci_stato(valore, e.get("classe"))
        righe.append(f"- {prefisso}{e.get('nome') or entity_id} ({stato_leggibile})")
    if not righe:
        righe.append("Niente di notevole al momento.")
    return righe


def _righe_comportamento(comportamento: list[dict]) -> list[str]:
    """I NOMI di cio' che la casa fa gia' da sola. Il corpo si va a
    chiedere -- per trecento automazioni non ci sta, e qui serve solo
    sapere che esistono. Chi non ha il corpo lo dichiara in riga."""
    if not comportamento:
        return ["Nessuna automazione o script registrati."]
    righe = []
    for v in comportamento:
        nome = v.get("nome") or v.get("id") or "(senza nome)"
        tipo = v.get("tipo", "?")
        riga = f"- {nome} ({tipo})"
        if v.get("corpo") is None:
            riga += " -- corpo non disponibile, solo il nome"
        righe.append(riga)
    return righe


def _righe_ricordi(ricordi: list[dict]) -> list[str]:
    """I ricordi ENTRANO INTERI, con chi li ha detti -- l'unica eccezione
    al "conta, non elencare" (vedi docstring del modulo)."""
    if not ricordi:
        return ["Nessun ricordo registrato."]
    righe = []
    for r in ricordi:
        detto_da = r.get("detto_da") or "qualcuno"
        righe.append(f"- \"{r['testo']}\" (detto da {detto_da})")
    return righe


def _righe_lacune(avvisi: list[str]) -> list[str]:
    if not avvisi:
        return ["Nessuna lacuna nota."]
    return [f"- {a}" for a in avvisi]


def _avviso_taglio(esclusi_per_pool: dict[str, int], ordine_taglio, tetto: int) -> str:
    """La frase che dichiara il taglio DENTRO il nucleo -- non solo nel
    riepilogo. Ricostruita da zero ogni volta che `esclusi_per_pool` cambia,
    cosi' non puo' mai restare disallineata da cio' che e' stato tagliato
    davvero.

    `ordine_taglio` porta la frase (singolare, plurale) GIA' concordata --
    generi diversi ("riga ... inclusa" contro "elemento ... incluso") non si
    possono comporre con un participio unico senza sbagliarne meta'.
    """
    parti = []
    for nome_pool, singolare, plurale in ordine_taglio:
        n = esclusi_per_pool.get(nome_pool, 0)
        if n:
            parti.append(f"{n} {_plurale(n, singolare, plurale)}")
    return f"Il nucleo superava il tetto di {tetto} caratteri: " + "; ".join(parti) + "."


def _assembla(sezioni: list[tuple[str, list[str]]]) -> str:
    blocchi = []
    for titolo, righe in sezioni:
        blocco = titolo if not righe else titolo + "\n" + "\n".join(righe)
        blocchi.append(blocco)
    return "\n\n".join(blocchi)


def componi(casa: dict, comportamento: list[dict], ricordi: list[dict],
            stato: dict, tetto: int = 6000,
            non_disponibili: tuple[str, ...] = ()) -> tuple[str, dict]:
    """Compone il nucleo: la stessa casa per chiunque ragioni.

    Pura -- nessun I/O, nessuna rete. Restituisce `(testo, riepilogo)`:
    il riepilogo (`caratteri`, `troncato`, `ricordi_esclusi`, `avvisi`) non
    puo' mentire su cio' che il testo non contiene, perche' e' costruito
    dagli stessi tagli che il testo dichiara -- vedi `test_nucleo.py`.

    L'ordine, deciso e fisso: 1) la casa (conteggi), 2) cio' che e' notevole
    adesso, 3) cio' che la casa fa gia' da sola, 4) cio' che le persone
    hanno detto, 5) cio' che HIRIS ignora (incluso l'eventuale taglio).

    `non_disponibili` sono i registri dell'anagrafe che non hanno risposto
    all'ultima lettura (`ArchivioCasa.non_disponibili()`). Senza, la sezione
    "cio' che HIRIS ignora" non potrebbe nominare la lacuna piu' grave che
    esista: una casa letta a meta' che il nucleo racconterebbe come una casa
    piccola. Una casa non ancora letta non e' una casa cambiata.

    Quando serve tagliare per stare sotto `tetto`, si tagliano prima i
    conteggi meno utili (casa), poi cio' che la casa fa da sola, poi cio'
    che e' notevole adesso, e per ultimi -- solo se resta ancora da tagliare
    -- i ricordi: sono l'unica cosa che non si ricostruisce da Home
    Assistant.
    """
    avvisi: list[str] = []

    if non_disponibili:
        avvisi.append(
            "registri di Home Assistant che non hanno risposto all'ultima "
            f"lettura: {', '.join(sorted(non_disponibili))}. "
            "Cio' che manca qui sotto potrebbe esistere lo stesso.")

    corpi_mancanti = [v for v in comportamento if v.get("corpo") is None]
    if corpi_mancanti:
        n = len(corpi_mancanti)
        nomi = ", ".join(v.get("nome") or v.get("id") or "?" for v in corpi_mancanti)
        voce = _plurale(n, "voce di comportamento", "voci di comportamento")
        avvisi.append(f"{n} {voce} senza corpo disponibile (solo il nome): {nomi}.")

    righe_casa = _righe_casa(casa)
    righe_notevole = _righe_notevole(casa, stato)
    righe_comportamento = _righe_comportamento(comportamento)
    righe_ricordi = _righe_ricordi(ricordi)

    # L'ordine di STAMPA e' fisso (vedi docstring); l'ordine di TAGLIO e'
    # diverso -- dal meno utile (casa) al piu' prezioso (ricordi), che si
    # tocca solo se resta ancora da tagliare dopo tutto il resto.
    sez_casa = ("## La casa", righe_casa)
    sez_notevole = ("## Notevole adesso", righe_notevole)
    sez_comportamento = ("## Cio' che la casa fa gia' da sola", righe_comportamento)
    sez_ricordi = ("## Cio' che le persone hanno detto", righe_ricordi)

    ordine_stampa = [sez_casa, sez_notevole, sez_comportamento, sez_ricordi]
    # (chiave, righe) -- l'ordine qui e' l'ordine di taglio: dal meno utile
    # al piu' prezioso.
    ordine_taglio = [
        ("casa", righe_casa),
        ("comportamento", righe_comportamento),
        ("notevole", righe_notevole),
        ("ricordi", righe_ricordi),
    ]
    # (chiave, frase singolare, frase plurale) GIA' concordate col genere
    # del sostantivo -- vedi il docstring di `_avviso_taglio`.
    etichette_taglio = [
        ("casa", "riga di conteggio della casa non inclusa",
                 "righe di conteggio della casa non incluse"),
        ("comportamento", "voce di comportamento non inclusa",
                          "voci di comportamento non incluse"),
        ("notevole", "elemento notevole non incluso",
                     "elementi notevoli non inclusi"),
        ("ricordi", "ricordo non incluso (il piu' vecchio prima)",
                    "ricordi non inclusi (i piu' vecchi prima)"),
    ]

    troncato = False
    esclusi_per_pool: dict[str, int] = {}
    budget = max(0, tetto - _RISERVA_SEZIONE_LACUNE)

    for nome_pool, righe_pool in ordine_taglio:
        while righe_pool and len(_assembla(ordine_stampa)) > budget:
            righe_pool.pop()  # dalla coda: l'ultima voce e' la meno prioritaria
            troncato = True
            esclusi_per_pool[nome_pool] = esclusi_per_pool.get(nome_pool, 0) + 1
        if len(_assembla(ordine_stampa)) <= budget:
            break

    # L'indice dell'avviso di taglio dentro `avvisi`, se e quando esiste --
    # serve a poterlo RISCRIVERE (rete di sicurezza sotto) senza rischiare
    # di sovrascrivere un avviso diverso che gli stesse accanto (es. i
    # corpi mancanti), che una sostituzione posizionale "ultimo elemento"
    # romperebbe silenziosamente se il taglio scattasse solo piu' avanti.
    indice_avviso_taglio = None
    if troncato:
        avvisi.append(_avviso_taglio(esclusi_per_pool, etichette_taglio, tetto))
        indice_avviso_taglio = len(avvisi) - 1

    sez_lacune = ("## Cio' che HIRIS ignora", _righe_lacune(avvisi))
    testo = _assembla(ordine_stampa + [sez_lacune])

    # Rete di sicurezza: se anche cosi' il testo sfora (l'avviso stesso puo'
    # pesare piu' della riserva stimata), si tagliano ancora ricordi -- gia'
    # l'ultima cosa nell'ordine di taglio -- finche' non rientra. Non deve
    # mai essere l'avviso a far sfondare il tetto in modo silenzioso.
    while len(testo) > int(tetto * 1.1) and righe_ricordi:
        righe_ricordi.pop()
        esclusi_per_pool["ricordi"] = esclusi_per_pool.get("ricordi", 0) + 1
        troncato = True
        messaggio = _avviso_taglio(esclusi_per_pool, etichette_taglio, tetto)
        if indice_avviso_taglio is None:
            avvisi.append(messaggio)
            indice_avviso_taglio = len(avvisi) - 1
        else:
            avvisi[indice_avviso_taglio] = messaggio
        sez_lacune = ("## Cio' che HIRIS ignora", _righe_lacune(avvisi))
        testo = _assembla(ordine_stampa + [sez_lacune])

    ricordi_esclusi = esclusi_per_pool.get("ricordi", 0)

    riepilogo = {
        "caratteri": len(testo),
        "troncato": troncato,
        "ricordi_esclusi": ricordi_esclusi,
        "avvisi": avvisi,
    }
    return testo, riepilogo
