#!/usr/bin/env python3
"""Le misure dei turni, lette con le REGOLE DI DECISIONE scritte dentro.

    python scripts/misure.py --db /percorso/consumi.db  [--giorni 7]
    python scripts/misure.py --url http://casa:8099/api/misure

**Perche' esiste, e perche' e' uno script e non una query.** Il 23/09/2026 una
latenza e' stata misurata a 3,6 secondi con una query improvvisata: la domanda
era sbagliata (la risposta era di due token), e la conclusione ne e' seguita.
Le domande vere sono queste, si calcolano sempre allo stesso modo, e le soglie
stanno qui in chiaro -- cosi' il giorno in cui diranno «non intervenire» non si
potra' far finta di niente.

**Le regole sono state scritte PRIMA di guardare i numeri**, apposta: decidere
dopo averli visti vuol dire farsi convincere di cio' che si pensava gia'.

Non tocca niente. Legge dal file quando il file c'e', e dalla rotta
temporanea `GET /api/misure` quando il file sta dentro il contenitore --
che e' il caso normale su Home Assistant.
"""
import argparse
import os
import pathlib
import sys
import time
from collections import Counter, defaultdict

#: Sotto questo numero di turni una specie non si giudica: una media su tre
#: giri non e' una misura, e' un aneddoto con una cifra decimale.
MINIMO_TURNI = 20

#: Uno strumento MAI chiamato da una specie e' candidato a uscire dal suo
#: catalogo. Il guadagno si calcola prima di toccare niente: i caratteri della
#: definizione, moltiplicati per i giri, moltiplicati per i turni.
#:
#: **Cosa direbbe di no**: se ogni specie chiama quasi tutto, non c'e' niente
#: da togliere -- e lo si sa senza aver rotto nulla.
SOGLIA_MAI_CHIAMATO = 0

#: Oltre questi giri un turno e' «lungo». Il carico si rispedisce INTERO a ogni
#: giro, quindi i giri sono il moltiplicatore della latenza. Non e' una soglia
#: misurata: e' il punto oltre il quale vale la pena guardare.
GIRI_LUNGHI = 5


def _leggi(percorso: str, da_ts: float):
    """I turni della finestra, **col loro carico attaccato**, letti
    dall'archivio e non in SQL qui.

    Le query le sapeva gia' fare `UsageStore`: riscriverle qui sarebbe stata
    la stessa lettura in due posti, liberi di divergere -- e il censimento
    l'ha presa al primo giro, segnalando `payloads()` come «usata solo dai
    test». Un lettore che nessuno usa non e' un lettore.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from hiris.app.usage.store import UsageStore

    archivio = UsageStore(percorso)
    try:
        turni = [t for t in archivio.turns(limit=100000) if t["ts"] >= da_ts]
        return [(t, archivio.payloads(t["id"])) for t in turni]
    finally:
        archivio.close()


def _leggi_remoto(url: str, giorni: int, chiave: str = ""):
    """Gli stessi dati, chiesti alla rotta invece che al file.

    **Serve perche' il file non e' raggiungibile**: `consumi.db` vive in
    `/data` dentro il contenitore dell'add-on, e su Home Assistant non c'e' un
    ambiente in cui far girare questo script. La rotta e' temporanea e lo
    dichiara nella sua stessa risposta -- se un giorno smettesse di dirlo,
    vorrebbe dire che e' diventata un'interfaccia senza che nessuno l'abbia
    deciso, e questo script lo fa notare.
    """
    import json as _json
    import urllib.request

    richiesta = urllib.request.Request(f"{url}?giorni={int(giorni)}")
    if chiave:
        for nome, valore in _firma(chiave, url).items():
            richiesta.add_header(nome, valore)
    with urllib.request.urlopen(richiesta, timeout=120) as risposta:
        dati = _json.loads(risposta.read())
    if "temporanea" not in dati:
        print("  NOTA: la rotta non si dichiara piu' temporanea. O e' "
              "diventata un'interfaccia, o qualcuno l'ha dimenticata li'.")
    carichi = dati.get("carichi") or {}
    return [(t, carichi.get(t["id"], [])) for t in dati.get("turni", [])]


def _firma(percorso_chiave: str, url: str) -> dict:
    """Le quattro intestazioni con cui un servizio approvato si presenta.

    **Il contratto si IMPORTA, non si riscrive**: `materia_firmata` vive in
    `api/canali.py`, ed e' scritto li' una volta sola apposta -- se le due
    parti divergessero, ogni firma legittima verrebbe rifiutata e nessuno
    capirebbe perche'. E' la stessa ragione per cui quel docstring esiste.
    """
    import base64
    import uuid
    from urllib.parse import urlparse

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    from hiris.app.api.canali import materia_firmata

    seme = pathlib.Path(percorso_chiave).read_text(encoding="utf-8").strip()
    privata = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(seme, validate=True))
    pubblica = base64.b64encode(privata.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)).decode()

    momento, unico = time.time(), uuid.uuid4().hex
    # Il percorso si firma SENZA la query: `?giorni=` sta nell'URL e non nella
    # materia firmata, come fa il resto del prodotto.
    percorso = urlparse(url).path
    firma = privata.sign(materia_firmata("GET", percorso, momento, unico, b""))
    return {"X-HIRIS-Servizio": pubblica,
            "X-HIRIS-Momento": str(int(momento)),
            "X-HIRIS-Unico": unico,
            "X-HIRIS-Firma": base64.b64encode(firma).decode()}


def _titolo(testo: str) -> None:
    print("\n" + testo)
    print("-" * len(testo))


def leva_1_strumenti(dati) -> None:
    """Quali strumenti chiama davvero ogni specie -- e quali mai."""
    _titolo("LEVA 1 · sottoinsieme degli strumenti per specie")
    per_specie = defaultdict(Counter)
    conta = Counter()
    catalogo = 0
    for turno, carichi in dati:
        conta[turno["species"]] += 1
        per_specie[turno["species"]].update(turno["tools"])
        for c in carichi:
            catalogo = max(catalogo, c["tools_sent"] or 0)
    print(f"  definizioni spedite a ogni giro: {catalogo}")
    for specie, quanti in sorted(conta.items(), key=lambda x: -x[1]):
        usati = per_specie[specie]
        if quanti < MINIMO_TURNI:
            print(f"  {specie:12} {quanti:>4} turni -- TROPPO POCHI per "
                  f"giudicare (servono {MINIMO_TURNI})")
            continue
        mai = catalogo - len(usati) if catalogo else 0
        print(f"  {specie:12} {quanti:>4} turni · {len(usati)} strumenti "
              f"diversi usati · {mai} mai chiamati")
        if mai > SOGLIA_MAI_CHIAMATO:
            print(f"               -> INTERVENIRE: {mai} definizioni spedite "
                  f"a ogni giro e mai usate da questa specie")
        else:
            print("               -> lasciare: usa tutto il catalogo")
        for nome, volte in usati.most_common(5):
            print(f"                  {nome}: {volte}")


def leva_2_prefisso(dati) -> None:
    """Il prefisso stabile e' davvero stabile?"""
    _titolo("LEVA 2 · il prefisso della catena")
    per_specie = defaultdict(set)
    for turno, carichi in dati:
        for c in carichi:
            if c["prefix_hash"]:
                per_specie[turno["species"]].add(c["prefix_hash"])
    if not per_specie:
        print("  nessuna impronta registrata: il ponte non compone il carico")
        print("  -- lo fa la CLI -- e li' non c'e' niente da pesare.")
        return
    for specie, impronte in sorted(per_specie.items()):
        print(f"  {specie:12} {len(impronte)} impronte diverse")
        if len(impronte) == 1:
            print("               -> il prefisso E' stabile. Se la cache non "
                  "colpisce lo stesso, non e' roba nostra: e' il provider")
        else:
            print(f"               -> INTERVENIRE: il prefisso cambia "
                  f"({len(impronte)} forme). La cache non puo' colpire, e il "
                  f"colpevole e' dentro la guida o le definizioni")


def leva_3_mappa(dati) -> None:
    """La mappa e' costo fisso: quanto pesa, e quanti turni le bastano."""
    _titolo("LEVA 3 · la mappa della casa")
    if not dati:
        print("  nessun turno nella finestra.")
        return
    senza = sum(1 for turno, _ in dati if not turno["tools"])
    costo = sum(sum(c["core_chars"] or 0 for c in carichi)
                for _, carichi in dati)
    print(f"  {len(dati)} turni · la mappa e' costata {costo:,} caratteri in "
          f"tutto (il nucleo sommato su ogni giro)")
    print(f"  turni risolti SENZA chiamare nessuno strumento: {senza} "
          f"({senza * 100 // len(dati)}%)")
    print("  -> questa misura da' il COSTO esatto e il beneficio solo per")
    print("     approssimazione: «senza strumenti» e' un indizio che la mappa")
    print("     sia bastata, non una prova. Non decide da sola.")


def leva_4_latenza(dati) -> None:
    """Chi fa molti giri, e con quali sequenze."""
    _titolo("LEVA 4 · i giri, cioe' la latenza")
    if not dati:
        print("  nessun turno nella finestra.")
        return
    per_specie = defaultdict(list)
    for turno, _ in dati:
        per_specie[turno["species"]].append(turno)
    for specie, turni in sorted(per_specie.items()):
        giri = [t["iterations"] for t in turni]
        durate = sorted(t["duration_ms"] for t in turni)
        medi = sum(giri) / len(giri)
        mediana = durate[len(durate) // 2]
        print(f"  {specie:12} {len(turni):>4} turni · giri medi {medi:.1f} · "
              f"durata mediana {mediana / 1000:.1f}s · peggiore "
              f"{durate[-1] / 1000:.1f}s")
        if medi > GIRI_LUNGHI:
            print(f"               -> GUARDARE: oltre {GIRI_LUNGHI} giri di "
                  f"media, e ogni giro rispedisce tutto il carico")
    print("\n  le sequenze che si ripetono (un recupero che non trova al "
          "primo colpo):")
    ripetute = Counter()
    for turno, _ in dati:
        nomi = turno["tools"]
        for i in range(len(nomi) - 1):
            if nomi[i] == nomi[i + 1]:
                ripetute[nomi[i]] += 1
    for nome, volte in ripetute.most_common(5):
        print(f"    {nome} chiamato di fila: {volte} volte")
    if ripetute:
        print("    -> e' la risposta alla domanda «serve un'altra tecnologia»:")
        print("       se il recupero sbaglia spesso, il problema e' come la")
        print("       conoscenza e' indicizzata, non quanto se ne manda")
    else:
        print("    nessuna: il recupero trova al primo colpo")


def leva_5_canali(dati) -> None:
    """Ponte e catena mandano la stessa cosa, a parita' di specie?"""
    _titolo("LEVA 5 · i quattro canali")
    somme = defaultdict(lambda: [0, 0, 0, 0])
    for turno, carichi in dati:
        for c in carichi:
            voce = somme[(turno["species"], turno["channel"])]
            voce[0] += c["tools_chars"] or 0
            voce[1] += c["guide_chars"] or 0
            voce[2] += c["core_chars"] or 0
            voce[3] += 1
    per_specie = defaultdict(list)
    for (specie, canale), voce in somme.items():
        per_specie[specie].append((canale, voce))
    if not per_specie:
        print("  nessun carico registrato nella finestra.")
        return
    for specie, canali in sorted(per_specie.items()):
        if len(canali) < 2:
            print(f"  {specie:12} un canale solo: niente da confrontare")
            continue
        print(f"  {specie:12} {len(canali)} canali:")
        for canale, (s, g, n, quanti) in sorted(canali):
            print(f"      {canale:18} strumenti {s // quanti:>8} · guida "
                  f"{g // quanti:>7} · nucleo {n // quanti:>7}")
        print("      -> se le parti divergono oltre il rumore, i composer sono")
        print("         scivolati di nuovo (tests/test_composition_order.py)")


def chi_ha_chiesto(dati) -> None:
    """La fondamenta: oggi una chat sola, domani piu' d'una."""
    _titolo("CHI HA CHIESTO")
    conta = Counter()
    for turno, _ in dati:
        soggetto = turno["subject"]
        chi = "nessuna persona" if not soggetto else (
            f"{soggetto.get('nome')} ({soggetto.get('specie')})")
        conta[(turno["species"], chi)] += 1
    for (specie, chi), quanti in sorted(conta.items()):
        print(f"  {specie:12} {chi:34} {quanti:>5} turni")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argomenti = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    argomenti.add_argument("--db", help="il consumi.db da leggere")
    argomenti.add_argument("--url", help="la rotta temporanea, es. "
                                         "http://192.168.1.95:8099/api/misure")
    argomenti.add_argument("--chiave", default="",
                           help="la chiave Ed25519 con cui firmare (la rotta "
                                "sta dietro il perimetro)")
    argomenti.add_argument("--giorni", type=int, default=7)
    scelte = argomenti.parse_args()

    if not scelte.db and not scelte.url:
        raise SystemExit("serve --db oppure --url")
    if scelte.url:
        dati = _leggi_remoto(scelte.url, scelte.giorni, scelte.chiave)
    else:
        if not os.path.exists(scelte.db):
            raise SystemExit(f"non trovo {scelte.db}")
        dati = _leggi(scelte.db, time.time() - scelte.giorni * 86400)
    print(f"MISURE · ultimi {scelte.giorni} giorni · {len(dati)} turni")
    if len(dati) < MINIMO_TURNI:
        print(f"\n  ATTENZIONE: sotto {MINIMO_TURNI} turni non si giudica "
              "niente. Lascia girare ancora.")
    leva_1_strumenti(dati)
    leva_2_prefisso(dati)
    leva_3_mappa(dati)
    leva_4_latenza(dati)
    leva_5_canali(dati)
    chi_ha_chiesto(dati)


if __name__ == "__main__":
    main()
