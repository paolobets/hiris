"""I provider dei modelli: chi ha una credenziale, e chi puo' rispondere.

Nasce dal primo commit del Task 9 della Tappa 7 (D8), per solo spostamento:
i tre calcoli che vivevano dentro `server.py` -- le credenziali e chi
risponde all'avvio (`_on_startup`), chi risponde adesso (`_recompute_chain`).
La tabella dei provider arriva qui nei commit successivi del Task 9.
"""
from .model_resolution import subscription_has_token


def credentials_present(*, api_key: str, openai_api_key: str,
                        openrouter_api_key: str, local_model_url: str) -> dict[str, bool]:
    """Le credenziali, e nient'altro: per ogni provider, se la credenziale c'e'."""
    return {
        "subscription": subscription_has_token(),
        "claude": bool(api_key),
        "openai": bool(openai_api_key),
        "openrouter": bool(openrouter_api_key),
        # La credenziale di Ollama e' il SOLO indirizzo. Prima era
        # `url and model`, cioe' il NOME DEL MODELLO faceva parte del test di
        # credenziale -- ma l'indirizzo e' cio' che si custodisce e il modello
        # e' cio' che si decide, e da questa fetta il modello vive
        # nell'archivio (Task 9). Conseguenza dichiarata: un'installazione con
        # URL presente e modello vuoto passa da «Ollama non credenziato» a
        # «Ollama credenziato, senza modello scelto» -- e la pagina lo mostra
        # invece di nasconderlo. Fino al Task 9 quello stato ha un BUCO
        # dichiarato: il runner di Ollama nasce ancora solo con
        # `url AND model`, quindi Ollama puo' stare in catena senza un backend
        # dietro. La semina della catena non ce lo porta (`_chain_as_it_was`
        # lo tiene fuori): ci si arriva solo mettendocelo a mano dalla pagina
        # Modelli.
        #
        # Task 9: il buco è CHIUSO, e non rimettendo il modello dentro la
        # credenziale (sarebbero di nuovo due concetti in un posto solo) ma
        # separando i due fatti: la credenziale resta l'indirizzo, e chi può
        # RISPONDERE si misura a parte (`can_answer_at_startup`) -- con quel
        # fatto si filtra la catena effettiva e si costruisce il runner. La
        # pagina mostra Ollama credenziato, fuori dalla catena, e dice che
        # manca il modello.
        "ollama": bool(local_model_url),
    }


def can_answer_at_startup(credentials: dict[str, bool], local_model_url: str,
                          ollama_model: str) -> dict[str, bool]:
    """Chi può davvero RISPONDERE, all'avvio.

    Non è una seconda rappresentazione della
    credenziale: sono due fatti diversi, e per quattro provider su cinque
    coincidono. Per Ollama no -- l'indirizzo è ciò che si custodisce, il
    modello è ciò che si decide -- e la differenza è esattamente il buco che
    il Task 7 aveva dichiarato: con la sola credenziale, Ollama poteva finire
    in `model_chain` senza un runner dietro, cioè comparire come anello
    numerato in una pagina che descrive il runtime mentre
    `LLMRouter._ordered_backends_with_name` lo saltava in silenzio.
    """
    return {**credentials,
            "ollama": bool(local_model_url and ollama_model)}


def can_answer_now(backend_map: dict, cfg: dict) -> dict[str, bool]:
    """Chi può rispondere ADESSO: la stessa regola dell'avvio
    (`can_answer_at_startup`), RILETTA invece che ricordata.

    Un backend costruito, e -- per Ollama -- un
    modello scelto: il runner locale esiste con il solo indirizzo, ma senza
    un modello sarebbe un anello che `_ordered_backends_with_name` salta in silenzio
    mentre la pagina lo disegna numerato (il buco che il Task 9 ha chiuso).
    """
    risponde = {name: b is not None for name, b in backend_map.items()}
    if risponde.get("ollama"):
        risponde["ollama"] = bool((cfg.get("ollama") or {}).get("modello"))
    return risponde
