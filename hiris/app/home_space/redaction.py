"""Il sigillo dei segreti: cio' che il proprietario ha dichiarato segreto non
esce dal confine in chiaro.

**Perche' esiste.** Finche' HIRIS leggeva le automazioni dal file, `!secret`
non veniva risolto: il caricatore lo rendeva `<secret nome>` -- «il valore vero
non lo conosciamo, sta apposta altrove». Dal 10/09/2026 il corpo si legge da
Home Assistant (`automation/config`), e li' il YAML e' **gia' risolto**:
verificato sul sorgente della libreria che HA usa (`annotatedyaml/loader.py`),
`secret_yaml` torna `secrets[secret]` -- il valore vero -- e
`components/config/automation.py` non oscura niente. Il segnaposto tocca a noi.

**La fonte e' `secrets.yaml`, non i nomi delle chiavi.** E' il posto in cui il
proprietario ha dichiarato cosa e' segreto. Riconoscere `password`, `token`,
`api_key` sarebbe indovinare dai nomi, e su un confine di riservatezza
un'euristica sbaglia **in silenzio**: e' esattamente cio' che il corollario di
`CLAUDE.md` vieta -- quando c'e' una fonte dichiarativa, quella e' la risposta.

**Del segreto si tiene l'impronta, mai il testo.** Serve solo a confrontare, e
un valore in chiaro dentro un oggetto vivo prima o poi finisce in un `repr`, in
una traccia di eccezione o in un rapporto. L'impronta costa niente e non si
puo' ripubblicare.

**Si oscura per valore, non per posizione**: un segreto in fondo a una lista
dentro un dizionario e' lo stesso segreto. Il prezzo dichiarato e' che una
stringa **identica** a un segreto viene oscurata anche dove segreta non e' --
si sbaglia dalla parte che non pubblica.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SecretSeal:
    """Le impronte dei segreti dichiarati, e la sostituzione al confine.

    `readable` distingue **«ho guardato e non ci sono segreti»** da **«non ho
    potuto guardare»**: sono due fatti diversi, e chi archivia un corpo deve
    poterli separare -- col secondo non si archivia e si dichiara il buco,
    esattamente come `specchio_vivo` fra i registri non disponibili.
    """

    def __init__(self, fingerprints: dict[str, str], *, readable: bool) -> None:
        self._names_by_fingerprint = dict(fingerprints)
        self._readable = readable

    @property
    def readable(self) -> bool:
        return self._readable

    @classmethod
    def from_file(cls, path: Path | str) -> SecretSeal:
        """Legge `secrets.yaml` e ne tiene le sole impronte.

        Un file assente e uno illeggibile danno lo stesso esito -- non
        leggibile -- perche' per chi deve decidere se pubblicare un corpo sono
        la stessa cosa: non si e' potuto controllare. La differenza fra
        «creare» e «riparare» qui non serve a nessuno, e inventarla
        costringerebbe ogni chiamante a un ramo in piu' che non usa.

        `yaml.safe_load` e non il caricatore tollerante dei file di Home
        Assistant: `secrets.yaml` e' una mappa piatta `nome: valore`, senza
        tag propri di HA. Non solleva mai: un guasto qui fermerebbe la lettura
        del comportamento, che e' un danno peggiore.
        """
        try:
            content = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls({}, readable=False)
        except Exception as error:
            logger.warning("segreti: %s non leggibile (%s: %s)",
                           path, type(error).__name__, error)
            return cls({}, readable=False)
        if content is None:
            return cls({}, readable=True)
        if not isinstance(content, dict):
            logger.warning("segreti: %s non e' una mappa nome->valore", path)
            return cls({}, readable=False)
        fingerprints = {_fingerprint(str(value)): str(name)
                        for name, value in content.items()
                        if isinstance(value, str | int | float) and str(value)}
        return cls(fingerprints, readable=True)

    def redact(self, value):
        """Sostituisce ogni valore segreto col suo segnaposto, a qualunque
        profondita'. Le chiavi dei dizionari non si toccano: un segreto usato
        come CHIAVE non e' un caso che Home Assistant produca, e sostituirla
        cambierebbe la forma della configurazione invece del suo contenuto.
        """
        if isinstance(value, str):
            name = self._names_by_fingerprint.get(_fingerprint(value))
            return f"<secret {name}>" if name else value
        if isinstance(value, dict):
            return {k: self.redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        return value
