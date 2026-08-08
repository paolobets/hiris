import logging
import aiohttp
from .proxy.ha_client import HAClient

try:
    import apprise as _apprise_lib
    _APPRISE_AVAILABLE = True
except ImportError:
    _apprise_lib = None  # type: ignore[assignment]
    _APPRISE_AVAILABLE = False

logger = logging.getLogger(__name__)

# Canale dedicato (Android) per raggruppare e rendere gestibili le notifiche
# HIRIS; ignorato su iOS. Oltre questa soglia il testo va anche in `subject`,
# che la Companion Android mostra come corpo lungo leggibile.
_PUSH_CHANNEL = "HIRIS"
_SUBJECT_MIN_CHARS = 160

# Collegamento proprio della Companion (documentato in
# companion.home-assistant.io/docs/integrations/url-handler/): apre l'app e
# naviga al percorso della web app di Home Assistant. `?server=default` usa il
# primo server disponibile, cosi' chi ne ha piu' di uno non si vede chiedere
# quale a ogni notifica.
_DEEPLINK_PREFIX = "homeassistant://navigate"
_DEEPLINK_SERVER = "server=default"


def build_app_deeplink(click_path: str | None) -> str | None:
    """Trasforma un percorso del frontend nel collegamento della Companion.

    `/hassio/ingress/<slug>` diventa
    `homeassistant://navigate/hassio/ingress/<slug>?server=default`.

    Serve perche' nei campi `url` (iOS) e `clickAction` (Android) i soli
    percorsi relativi accettati sono quelli delle dashboard Lovelace: la
    Companion iOS non sa navigare `/hassio/ingress/<slug>`, lo passa al sistema
    operativo e ne esce il selettore "salva il sito" con pagina vuota. Il
    collegamento invece apre l'app e naviga dentro il frontend, senza dipendere
    dall'indirizzo esterno di Home Assistant.

    Ritorna None se il percorso non e' ricavabile (Supervisor irraggiungibile,
    slug assente), cosi' il chiamante omette del tutto il collegamento."""
    path = (click_path or "").strip()
    if not path:
        return None
    if not path.startswith("/"):
        path = "/" + path
    separatore = "&" if "?" in path else "?"
    return f"{_DEEPLINK_PREFIX}{path}{separatore}{_DEEPLINK_SERVER}"


def build_push_data(config: dict, message: str) -> dict:
    """Payload `data` extra per un push mobile (`ha_push`).

    - collegamento sul TAP del corpo alla UI ingress di HIRIS
      (`config["ingress_click_path"]` = `/hassio/ingress/<slug>`), cosi' la
      notifica apre HIRIS e non la Dashboard home. La Companion legge il campo
      della propria piattaforma e i due campi portano forme diverse:
      `clickAction` (Android) il percorso relativo, che la Companion Android
      risolve nativamente nel frontend; `url` (iOS) il collegamento
      `homeassistant://navigate/...`, l'unica forma che la Companion iOS sa
      aprire per un percorso che non e' una dashboard Lovelace.
    - un canale dedicato "HIRIS" (Android) sempre presente.
    - per il testo lungo, `subject` con il messaggio (Android, corpo leggibile).

    Ritorna sempre almeno `{"channel": ...}`; senza click path il collegamento
    viene semplicemente omesso (nessuna regressione)."""
    d: dict = {"channel": _PUSH_CHANNEL}
    click = (config or {}).get("ingress_click_path")
    deeplink = build_app_deeplink(click)
    if click and deeplink:
        d["clickAction"] = click
        d["url"] = deeplink
    if message and len(message) > _SUBJECT_MIN_CHARS:
        d["subject"] = message
    return d


async def send_notification(
    ha: HAClient,
    message: str,
    channel: str,
    config: dict,
    *,
    title: str | None = None,
    notification_id: str | None = None,
) -> bool:
    """Send a notification via the specified channel.

    Notifications are informational (they never actuate devices), so this path is
    intentionally NOT gated by the gateway semaforo — it is the sanctioned way for
    the agent/gateway to reach the user, including Home Assistant persistent
    (dashboard) notifications, which are otherwise unreachable via call_ha_service.
    """
    message = message or ""
    # Normalize legacy channel aliases
    if channel == "ha":
        channel = "ha_push"
    if channel == "telegram":
        channel = "apprise"

    if channel == "ha_persistent":
        # Dismiss an existing persistent notification: empty message + id.
        if not message and notification_id:
            return await ha.call_service(
                "persistent_notification", "dismiss", {"notification_id": notification_id}
            )
        if not message:
            logger.warning("ha_persistent: 'message' required to create a persistent notification")
            return False
        data: dict = {"message": message}
        if title:
            data["title"] = title
        if notification_id:
            data["notification_id"] = notification_id
        return await ha.call_service("persistent_notification", "create", data)

    if channel == "ha_push":
        if not message:
            logger.warning("ha_push: 'message' required")
            return False
        service = config.get("ha_notify_service", "notify.notify")
        try:
            domain, svc = service.split(".", 1)
        except ValueError:
            logger.error("Invalid ha_notify_service format: %s (expected 'domain.service')", service)
            return False
        data = {"message": message}
        if title:
            data["title"] = title
        data["data"] = build_push_data(config, message)
        return await ha.call_service(domain, svc, data)

    if channel == "apprise":
        if not _APPRISE_AVAILABLE:
            logger.error("apprise library not installed — run: pip install apprise>=1.9.0")
            return False
        urls: list[str] = config.get("apprise_urls") or []
        if not urls:
            logger.warning("Apprise not configured: apprise_urls is empty")
            return False
        apobj = _apprise_lib.Apprise()
        for url in urls:
            apobj.add(url)
        result = await apobj.async_notify(body=message, title=title or "")
        return bool(result)

    if channel == "retropanel":
        rp_url = config.get("retropanel_url", "http://retropanel:8098")
        payload = {"message": message}
        if title:
            payload["title"] = title
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{rp_url}/api/notify", json=payload) as resp:
                return resp.status in (200, 204)

    logger.warning("Unknown notification channel: %s", channel)
    return False
