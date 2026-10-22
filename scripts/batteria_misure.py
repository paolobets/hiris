#!/usr/bin/env python3
"""La batteria delle 32 domande, cronometrate e giudicate.

    python scripts/batteria_misure.py --domande ~/.hiris-batteria.json \
        --chiave ~/.hiris-canale-sviluppo.key --url http://casa:8099 \
        --etichetta ponte --esiti ~/esiti-ponte.json

**Le domande non stanno qui**: nominano stanze, luci e automazioni di una casa,
e nel repo non entra nessun nome della casa. Stanno in un file del
proprietario, con accanto il CRITERIO ATTESO scritto prima di chiedere (spec
«le misure complete» §6): una risposta si giudica contro quello, non contro
l'impressione del momento.

**Tre domande hanno effetti veri** (`effetto`: promessa, ricordo, azione): lo
script si ferma e chiede conferma, e dopo dice cosa rimettere a posto. Con
`--automatico` (nessuno alla tastiera) quelle domande non partono affatto
e i giudizi restano da dare: restano al proprietario, non a un default.

Il cronometro va dalla domanda alla risposta: sulla catena `POST /api/chat`
risponde 200; sul ponte 202 e la risposta si ritira da
`/api/chat/reply/{job_id}`. Chi ha risposto davvero lo dice il registro dei
turni, non questo script.

**Una conversazione per domanda** (`--domande-isolate`, sprint «Il giro
snello», 1.1): senza, le domande stanno in un filo solo e ognuna porta la
storia delle precedenti, quindi il prima e il dopo di uno snellimento non si
confrontano. Con l'opzione, dopo ogni risposta il filo di chi firma si svuota
con le rotte della pagina (chiudere, elencare, cancellare): cancellare e non
solo chiudere, perche' i riassunti delle conversazioni chiuse rientrano nel
contesto delle successive (`handlers_chat.compose_chat_context`, «Sessioni
precedenti»). Le risposte restano nel file degli esiti; i token restano nel
registro dei consumi, che la chat non tocca. Un filo che ha gia' conversazioni
non parte: le cancella solo `--svuota-filo`, detto da chi lancia.
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from misure import intestazioni_firmate  # la firma e' una sola, fra gli script

GIUDIZI = ("giusta", "incompleta", "sbagliata")
PASSO_S = 0.5


def carica_domande(percorso: str) -> list[dict]:
    domande = json.loads(pathlib.Path(percorso).expanduser().read_text(encoding="utf-8"))
    senza = [d.get("n") for d in domande if not (d.get("atteso") or "").strip()]
    if senza:
        raise SystemExit(f"domande senza criterio atteso: {senza}. Il criterio "
                         "si scrive PRIMA di chiedere.")
    return domande


def domande_ammesse(domande: list[dict], *, conferme: bool) -> list[dict]:
    """Senza conferme, le domande con un effetto vero non partono."""
    return [d for d in domande if conferme or not d.get("effetto")]


def riassunto(esiti: list[dict]) -> dict:
    buoni = sorted(e["secondi"] for e in esiti if e["stato"] == "ok")
    giudizi = {g: sum(1 for e in esiti if e.get("giudizio") == g) for g in GIUDIZI}
    giudizi["da_giudicare"] = sum(1 for e in esiti
                                  if e["stato"] == "ok" and not e.get("giudizio"))
    return {"riusciti": len(buoni),
            "mediana_s": buoni[len(buoni) // 2] if buoni else None,
            "peggiore_s": buoni[-1] if buoni else None,
            "giudizi": giudizi}


def _bussa(url: str, chiave: str, metodo: str, percorso: str,
           corpo: bytes = b"", attesa: int = 60):
    intestazioni = intestazioni_firmate(chiave, url + percorso, metodo, corpo)
    intestazioni["Content-Type"] = "application/json"
    richiesta = urllib.request.Request(url + percorso, method=metodo,
                                       data=corpo or None, headers=intestazioni)
    try:
        with urllib.request.urlopen(richiesta, timeout=attesa) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as errore:
        return errore.code, errore.read()


def chiedi(url: str, chiave: str, domanda: str, attesa: int = 900):
    inizio = time.perf_counter()
    stato, grezzo = _bussa(url, chiave, "POST", "/api/chat",
                           json.dumps({"message": domanda}).encode(), attesa)
    corpo = json.loads(grezzo) if grezzo else {}
    if stato == 200:
        return time.perf_counter() - inizio, "ok", corpo.get("response", ""), ""
    if stato != 202:
        return time.perf_counter() - inizio, "errore", f"[{stato}]", ""
    job = corpo.get("job_id", "")
    while time.perf_counter() - inizio < attesa:
        time.sleep(PASSO_S)
        _, grezzo = _bussa(url, chiave, "GET", f"/api/chat/reply/{job}")
        passo = json.loads(grezzo) if grezzo else {}
        if passo.get("status") == "done":
            return time.perf_counter() - inizio, "ok", passo.get("reply", ""), job
        if passo.get("status") == "error":
            return time.perf_counter() - inizio, "errore", passo.get("error", ""), job
    return time.perf_counter() - inizio, "scaduto", "", job


def _corpo(grezzo: bytes) -> dict:
    return json.loads(grezzo) if grezzo else {}


def conversazioni(url: str, chiave: str) -> list[dict]:
    """Le conversazioni del filo di chi firma, come le elenca la pagina."""
    stato, grezzo = _bussa(url, chiave, "GET", "/api/chat/conversations")
    if stato != 200:
        raise SystemExit(f"l'elenco delle conversazioni risponde [{stato}]: "
                         f"{_corpo(grezzo).get('error', '')}")
    return _corpo(grezzo).get("conversations", [])


def svuota_filo(url: str, chiave: str, attesa: int = 900) -> int:
    """Chiude la conversazione aperta e cancella tutte quelle del filo.

    Finche' una risposta e' in volo (una domanda scaduta, sul ponte) la
    chiusura risponde 409: si aspetta che arrivi, perche' svuotare adesso la
    farebbe atterrare nella conversazione della domanda dopo. Un rifiuto
    diverso ferma la batteria: proseguire misurerebbe domande con la storia
    dentro. Restituisce quante conversazioni ha cancellato."""
    inizio = time.perf_counter()
    while True:
        stato, grezzo = _bussa(url, chiave, "POST", "/api/chat/conversations", b"{}")
        if stato == 200:
            break
        if stato != 409 or time.perf_counter() - inizio >= attesa:
            raise SystemExit(f"chiudere la conversazione risponde [{stato}]: "
                             f"{_corpo(grezzo).get('error', '')}")
        time.sleep(PASSO_S)
    cancellate = 0
    for c in conversazioni(url, chiave):
        stato, grezzo = _bussa(url, chiave, "DELETE",
                               f"/api/chat/conversations/{c['id']}")
        if stato != 200:
            raise SystemExit(f"cancellare la conversazione {c['id']} risponde "
                             f"[{stato}]: {_corpo(grezzo).get('error', '')}")
        cancellate += 1
    return cancellate


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--domande", required=True)
    a.add_argument("--chiave", required=True)
    a.add_argument("--url", required=True)
    a.add_argument("--etichetta", required=True, help="catena o ponte")
    a.add_argument("--esiti", required=True, help="file FUORI dal repo")
    a.add_argument("--automatico", action="store_true",
                   help="salta le domande con effetti veri, giudizi da dare dopo")
    a.add_argument("--solo", type=int, nargs="*", help="solo questi numeri")
    a.add_argument("--domande-isolate", action="store_true",
                   help="ogni domanda in una conversazione nuova, senza storia")
    a.add_argument("--svuota-filo", action="store_true",
                   help="con --domande-isolate: cancella le conversazioni che "
                        "il filo di chi firma ha gia'")
    s = a.parse_args()
    chiave = str(pathlib.Path(s.chiave).expanduser())
    conferme = not s.automatico
    if s.svuota_filo and not s.domande_isolate:
        raise SystemExit("--svuota-filo vale solo con --domande-isolate")
    if s.domande_isolate:
        gia = conversazioni(s.url, chiave)
        if gia and not s.svuota_filo:
            raise SystemExit(f"il filo di chi firma ha gia' {len(gia)} "
                             "conversazioni: i loro riassunti entrerebbero in "
                             "ogni domanda. Rilancia con --svuota-filo per "
                             "cancellarle.")
        if gia:
            print(f"cancellate {svuota_filo(s.url, chiave)} conversazioni "
                  "che il filo aveva gia'", flush=True)

    esiti = []
    for d in domande_ammesse(carica_domande(s.domande), conferme=conferme):
        if s.solo and d["n"] not in s.solo:
            continue
        if d.get("effetto") and input(
                f"\n#{d['n']} ha un effetto vero ({d['effetto']}): "
                f"«{d['domanda']}». Procedo? [s/N] ").strip().lower() != "s":
            continue
        secondi, stato, risposta, job = chiedi(s.url, chiave, d["domanda"])
        print(f"\n{d['n']:>2}. [{d['aspetto']}] {secondi:.1f}s [{stato}]", flush=True)
        print(f"    domanda: {d['domanda']}")
        print(f"    atteso:  {d['atteso']}")
        print(f"    risposta: {risposta[:600]}", flush=True)
        giudizio = None
        if conferme and stato == "ok" and d.get("giudice") == "hiris":
            scelta = input("    giudizio [g]iusta/[i]ncompleta/[s]bagliata/invio=dopo: ")
            giudizio = {"g": "giusta", "i": "incompleta",
                        "s": "sbagliata"}.get(scelta.strip().lower())
        if d.get("effetto"):
            print(f"    RIMETTI A POSTO: {d['effetto']} creato da questa domanda.")
        esiti.append({**d, "secondi": round(secondi, 2), "stato": stato,
                      "risposta": risposta, "giudizio": giudizio, "job_id": job,
                      "etichetta": s.etichetta, "ts": time.time(),
                      "domanda_isolata": s.domande_isolate})
        pathlib.Path(s.esiti).expanduser().write_text(
            json.dumps(esiti, ensure_ascii=False, indent=1), encoding="utf-8")
        if s.domande_isolate:
            svuota_filo(s.url, chiave)
    print("\n" + json.dumps(riassunto(esiti), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
