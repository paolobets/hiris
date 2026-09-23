"""L'immagine di base è fissata per IMPRONTA (reperto D-3, 23/09/2026).

Il pin è nato in `build.yaml` il 23/09/2026 e **ha rotto l'aggiornamento della
3.64.0 sulla casa vera**. Il Supervisor valida `build_from` con una regex che
non ammette `@` — quindi non ammette un'impronta — e il guaio è che **non si
ferma**: registra un `WARNING` e prosegue con i valori di default, cioè
`ghcr.io/home-assistant/base:latest`, che è Alpine nuda senza Python. La
costruzione moriva tre passi dopo con `/bin/ash: pip3: not found`, exit 127, e
l'errore non nominava la causa.

Quindi il pin **si è spostato nel Dockerfile**, dove Docker lo accetta e dove
il Supervisor stesso chiede di metterlo («App uses build.yaml which is
deprecated. Move build parameters into the Dockerfile directly», stampato a
ogni costruzione). Uno stadio per architettura, l'ultimo `FROM` sceglie il suo
con `BUILD_ARCH` — che è un `--build-arg` che il Supervisor passa sempre.

**Cosa costa, detto per intero**: le patch della base non arrivano più da
sole, comprese quelle di sicurezza. Aggiornarla diventa un atto deliberato di
chi rilascia. È il prezzo del pin, ed è la ragione per cui la riga va guardata
a ogni giro — `scripts/verifica_componenti.py` la guarda.

**L'etichetta resta scritta accanto**, nel commento: un'impronta da sola non
dice a nessuno quale versione di Python ci sia dentro.

**Cosa provavano le quattro prove del 23/09, e perché non è bastato.**
Dicevano tutte la stessa specie di cosa — *c'è un'impronta*, *le due
differiscono*, *l'etichetta è nel commento*, *il cancello legge la riga*:
asserivano **il fatto che volevamo**, nessuna asseriva **la proprietà che lo
fa funzionare**, cioè che quello che scriviamo lo accetti chi lo legge. Erano
verdi mentre la cosa era rotta in produzione. Da qui le due prove nuove in
fondo, che eseguono la regex **vera** del Supervisor.
"""
import pathlib
import re

import yaml

RADICE = pathlib.Path(__file__).resolve().parents[1]
BUILD = RADICE / "hiris" / "build.yaml"
DOCKERFILE = RADICE / "hiris" / "Dockerfile"
CONFIG = RADICE / "hiris" / "config.yaml"

#: `FROM ghcr.io/home-assistant/amd64-base-python@sha256:… AS base-amd64`
_RE_STADIO = re.compile(
    r"^FROM\s+ghcr\.io/(\S+?)@(sha256:[0-9a-f]{64})\s+AS\s+base-(\w+)\s*$")

#: La regex con cui il Supervisor valida `build_from`, **copiata dal sorgente
#: vero** e non riscritta: `supervisor/apps/validate.py`,
#: `RE_DOCKER_IMAGE_BUILD` (letta il 23/09/2026; identica anche nelle release
#: precedenti, dove il file stava in `supervisor/addons/validate.py`).
#: Riscriverla «più chiara» la farebbe divergere da quella che decide davvero,
#: che è il modo in cui questo cancello smetterebbe di essere un cancello.
_RE_SUPERVISOR = re.compile(
    r"^([a-zA-Z\-\.:\d{}]+/)*?([\-\w{}]+)/([\-\w{}]+)(:[\.\-\w{}]+)?$")

#: Il valore esatto che il Supervisor ha rifiutato il 23/09/2026, copiato dal
#: suo registro.
_IMPRONTA_RIFIUTATA_3_64_0 = (
    "ghcr.io/home-assistant/amd64-base-python"
    "@sha256:35d1dcdc69a44fdaaea2f3e14cf762176f03d4cadd6a8c77e8cafa8d2644848b")


def _stadi() -> dict:
    """`{arch: {"repository": …, "impronta": …, "etichetta": …}}`.

    L'etichetta si legge dal commento SOPRA la riga, che è dove vive.

    **Una lettura che non trova niente SOLLEVA**, non restituisce vuoto — la
    stessa regola che `scripts/verifica_componenti.py` si è data. Restituire
    `{}` lascerebbe verdi, a vuoto, tutte le prove che ciclano sugli stadi:
    è esattamente la specie di prova che questo file esiste per non avere più.
    """
    righe = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    stadi = {}
    for indice, riga in enumerate(righe):
        trovato = _RE_STADIO.match(riga)
        if not trovato:
            continue
        precedente = righe[indice - 1].strip() if indice else ""
        stadi[trovato.group(3)] = {
            "repository": trovato.group(1),
            "impronta": trovato.group(2),
            "etichetta": (precedente.lstrip("# ").strip()
                          if precedente.startswith("#") else ""),
        }
    if not stadi:
        raise AssertionError(
            f"nessuno stadio di base fissato per impronta in {DOCKERFILE}. "
            "Se la forma e' cambiata, `_RE_STADIO` va aggiornata: senza, "
            "queste prove passerebbero a vuoto invece di rompersi.")
    return stadi


def _architetture_dichiarate() -> set:
    return set(yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["arch"])


def test_ogni_architettura_DICHIARATA_ha_il_suo_stadio_di_base():
    """La proprietà, non il fatto: gli stadi non devono essere «due», devono
    essere **quelli che l'add-on dichiara di supportare** in `config.yaml`.
    Una casa su un'architettura senza stadio vedrebbe `FROM base-<arch>`
    risolversi nel nulla — e chi aggiunge un'architettura là dentro senza
    aggiungerla qui non se ne accorgerebbe fino alla prima costruzione vera.

    Mutazione ESEGUITA: togliere lo stadio `base-aarch64` -- rossa.
    Mutazione ESEGUITA: aggiungere `armv7` a `config.yaml` -- rossa.
    Mutazione ESEGUITA: rimettere l'etichetta al posto dell'impronta su
    un'architettura -- rossa (lo stadio sparisce, e qui si vede)."""
    assert set(_stadi()) == _architetture_dichiarate()


def test_ogni_stadio_e_fissato_per_impronta():
    """**Il reperto**: lo stadio di un'architettura deve puntare all'immagine
    di QUELLA architettura. Un repository copiato dall'altra riga si
    costruisce senza un lamento e gira sull'architettura sbagliata.

    **La mutazione che credevo uccidesse questa prova non la uccide**, ed e'
    stato misurato invece che supposto: rimettere l'etichetta al posto
    dell'impronta fa sparire lo stadio dagli occhi di `_RE_STADIO`, quindi
    questa prova non ha piu' niente da esaminare -- a prenderla e'
    `test_ogni_architettura_DICHIARATA_ha_il_suo_stadio_di_base`, che conta
    gli stadi invece di guardarci dentro. Le due prove si coprono a vicenda
    senza sovrapporsi: una che l'insieme sia giusto, l'altra che ogni elemento
    lo sia.

    Mutazione ESEGUITA: far puntare lo stadio `base-aarch64` al repository
    `amd64-base-python` -- rossa.
    Mutazione ESEGUITA (e SOPRAVVISSUTA qui, rossa altrove): rimettere
    l'etichetta al posto dell'impronta su un'architettura."""
    for arch, stadio in _stadi().items():
        assert arch in stadio["repository"], (
            f"lo stadio «base-{arch}» punta a «{stadio['repository']}»: "
            "l'immagine non e' quella della sua architettura")


def test_le_due_architetture_NON_condividono_l_impronta():
    """Ogni architettura ha la sua immagine: la stessa impronta su tutte e due
    vorrebbe dire che qualcuno ha copiato una riga sull'altra, e una delle due
    costruzioni fallirebbe -- o peggio, girerebbe sull'architettura sbagliata.

    **Questa prova e' nata verde e non sapeva fallire** (23/09/2026).
    Confrontava i due riferimenti INTERI, che differiscono sempre -- il nome
    del repository contiene l'architettura -- quindi copiare un'impronta
    sull'altra la lasciava verde. La proprieta' vera sta nelle impronte, non
    nelle stringhe che le contengono.

    Mutazione ESEGUITA: copiare un'impronta sull'altra -- rossa."""
    impronte = [stadio["impronta"] for stadio in _stadi().values()]

    assert len(set(impronte)) == len(impronte), (
        "due architetture hanno la stessa impronta: una delle due "
        "costruzioni fallira', o girera' sull'architettura sbagliata")


def test_l_ETICHETTA_resta_leggibile_accanto_all_impronta():
    """Un'impronta da sola non dice a nessuno quale Python ci sia dentro. Chi
    legge il Dockerfile fra sei mesi deve poter capire cosa sta aggiornando
    senza interrogare un registro.

    Mutazione ESEGUITA: togliere il commento con l'etichetta sopra uno stadio
    -- rossa."""
    for arch, stadio in _stadi().items():
        assert re.fullmatch(r"[\d.]+-alpine[\d.]+", stadio["etichetta"]), (
            f"sopra lo stadio «base-{arch}» non c'e' l'etichetta: «"
            f"{stadio['etichetta']}»")


def test_l_ultimo_FROM_sceglie_lo_stadio_con_BUILD_ARCH():
    """Gli stadi non servono a niente se l'immagine finale non ne sceglie uno.
    E `ARG BUILD_ARCH` deve stare **prima del primo `FROM`**: un `ARG`
    dichiarato dopo non è visibile a un `FROM`, e la costruzione cercherebbe
    uno stadio chiamato `base-`.

    **`BUILD_ARCH` non ha un default, ed è deliberato.** Un default lo
    renderebbe silenzioso sull'architettura sbagliata invece che rotto.

    Mutazione ESEGUITA: spostare `ARG BUILD_ARCH` dopo il primo `FROM` --
    rossa.
    Mutazione ESEGUITA: `FROM base-amd64` fisso al posto della variabile --
    rossa."""
    testo = DOCKERFILE.read_text(encoding="utf-8")
    righe = [riga.strip() for riga in testo.splitlines()]

    posizione_arg = righe.index("ARG BUILD_ARCH")
    primo_from = next(i for i, riga in enumerate(righe)
                      if riga.startswith("FROM "))

    assert posizione_arg < primo_from, (
        "`ARG BUILD_ARCH` sta dopo il primo `FROM`: non sara' visibile")
    assert "\nFROM base-${BUILD_ARCH}\n" in testo, (
        "l'ultimo `FROM` non sceglie lo stadio con `BUILD_ARCH`")


def test_build_yaml_NON_fissa_piu_la_base():
    """Una cosa sola in un posto solo. Se `build_from` tornasse in
    `build.yaml`, la base sarebbe dichiarata in **due** posti liberi di
    divergere -- e quello dei due che il Supervisor legge è quello che
    rifiuta.

    Mutazione ESEGUITA: rimettere `build_from` in `build.yaml` -- rossa."""
    build = yaml.safe_load(BUILD.read_text(encoding="utf-8"))

    assert "build_from" not in build, (
        "`build.yaml` torna a fissare la base: il pin vive nel Dockerfile, e "
        "il Supervisor non accetta un'impronta qui (vedi la prova sotto)")


def test_il_controllo_del_SUPERVISOR_e_quello_vero():
    """**La prova che mancava il 23/09/2026**, in due righe.

    Senza questa, la prova qui sotto passerebbe anche con una regex
    addolcita: un controllo che accetta tutto e' un controllo che non c'e'.
    Qui si chiede alla regex di **rifiutare il valore esatto che ha rotto la
    3.64.0** e di accettare la forma che invece funzionava.

    Mutazione ESEGUITA: aggiungere `@` alla classe di caratteri di
    `_RE_SUPERVISOR` -- rossa."""
    assert not _RE_SUPERVISOR.match(_IMPRONTA_RIFIUTATA_3_64_0), (
        "la regex accetta l'impronta: non e' piu' quella del Supervisor, e "
        "questo cancello non sta guardando niente")
    assert _RE_SUPERVISOR.match(
        "ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21")


def test_cio_che_build_yaml_DICHIARA_passa_la_validazione_del_Supervisor():
    """Il cancello per il futuro. Oggi `build_from` non c'e' e questa prova
    non ha niente da esaminare; il giorno in cui qualcuno lo rimette --
    perche' gli serve, e puo' servirgli -- questa riga dice subito se il
    Supervisor lo accetta, invece di lasciarlo scoprire a una casa che non si
    aggiorna piu'.

    Il Supervisor **non fallisce** su un valore non valido: stampa un
    `WARNING` e usa i default. Ecco perche' serve leggerlo qui e non la'.

    Mutazione ESEGUITA: rimettere in `build.yaml` il `build_from` per impronta
    della 3.64.0 -- rossa."""
    build = yaml.safe_load(BUILD.read_text(encoding="utf-8"))
    dichiarato = build.get("build_from")

    valori = ([dichiarato] if isinstance(dichiarato, str)
              else list(dichiarato.values()) if dichiarato else [])
    for valore in valori:
        assert _RE_SUPERVISOR.match(valore), (
            f"il Supervisor rifiutera' «{valore}» e costruira' con "
            "`ghcr.io/home-assistant/base:latest`, che non ha Python")


def test_il_cancello_del_rilascio_LEGGE_le_basi_dal_Dockerfile():
    """Il prezzo del pin e' che le patch non arrivano da sole: senza qualcuno
    che guardi, «fissato per impronta» diventa «fermo da un anno».

    **Questa prova cercava due parole nel sorgente del cancello** -- e le due
    parole c'erano gia' per altre ragioni (`Dockerfile` per il pin della CLI,
    `base-python` dentro un commento), quindi restava verde anche se il
    cancello avesse smesso di guardare le basi. Adesso **interroga il lettore
    vero** e gli chiede cosa ha trovato: e' un comportamento, non un testo.

    Mutazione ESEGUITA: togliere la lettura delle basi da `leggi_i_file` --
    rossa.
    Mutazione ESEGUITA: far leggere le basi da `build.yaml` invece che dal
    Dockerfile -- rossa."""
    import sys
    sys.path.insert(0, str(RADICE / "scripts"))
    try:
        import verifica_componenti
    finally:
        sys.path.pop(0)

    basi = verifica_componenti.leggi_i_file()["basi"]

    assert set(basi) == _architetture_dichiarate(), (
        "il cancello non sorveglia tutte le architetture dichiarate")
    for arch, base in basi.items():
        assert base["dove"] == "hiris/Dockerfile", (
            f"il cancello legge la base di «{arch}» da «{base['dove']}», "
            "dove il pin non vive piu'")
        assert base["impronta"] == _stadi()[arch]["impronta"], (
            f"il cancello legge un'impronta diversa da quella dello stadio "
            f"«base-{arch}»")
