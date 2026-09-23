import logging
import os

from aiohttp import web

from .server import create_app

#: **Le librerie che, in `debug`, stampano il corpo della richiesta** (reperto
#: C-2, 23/09/2026). Gli SDK dei fornitori e i client HTTP sotto di loro
#: registrano le opzioni di ogni chiamata, e in quelle opzioni c'e' il corpo
#: intero: prompt di sistema, nucleo della casa, ricordi, conversazione.
#:
#: Il livello `debug` e' **a un clic** nella pagina dell'add-on, e il registro
#: e' esattamente il file che si incolla in una segnalazione: «metti debug e
#: mandami il log» e' la procedura normale di assistenza, non un caso limite.
#:
#: Non e' un elenco qualunque: sono i CLIENT che parlano coi modelli. Se un
#: fornitore nuovo entrasse nel prodotto con un suo SDK, il suo nome va qui.
LIBRERIE_RUMOROSE = ("httpx", "httpcore", "anthropic", "openai", "aiohttp", "urllib3")


def prepara_registri() -> None:
    """Applica `LOG_LEVEL`, col pavimento alle librerie di terze parti.

    **Cosa NON cambia**: il `debug` di HIRIS resta `debug`. Si mette un
    pavimento alle librerie, non al prodotto — chi accende il debug lo accende
    per vedere cosa fa HIRIS, non per leggere come `httpx` serializza un corpo.

    Il pavimento si applica **solo** quando il livello richiesto sta sotto
    `INFO`: sopra non c'e' niente da limitare, e limitare comunque
    nasconderebbe avvisi utili delle librerie stesse.
    """
    richiesto = os.environ.get("LOG_LEVEL", "info").upper()
    # `LOG_LEVEL` viene da un'opzione dell'add-on: prima o poi qualcuno ci
    # scrive qualcosa che non e' un livello, e l'add-on deve partire lo stesso.
    livello = getattr(logging, richiesto, logging.INFO)
    if not isinstance(livello, int):
        livello = logging.INFO
    logging.basicConfig(
        level=livello,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    if livello < logging.INFO:
        for nome in LIBRERIE_RUMOROSE:
            logging.getLogger(nome).setLevel(logging.INFO)


def main() -> None:
    prepara_registri()
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=8099)


if __name__ == "__main__":
    main()
