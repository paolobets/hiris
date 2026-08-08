# Il canale di invio (send_notification, build_app_deeplink, build_push_data,
# il supporto Apprise) e' stato spostato in ..notifiche: non e' uno strumento,
# e' il canale push dell'add-on, usato anche da moduli fuori da tools/
# (server.py, task_engine.py, brain/health_scan.py). Qui resta solo la
# definizione del tool per l'LLM.

TOOL_DEF = {
    "name": "send_notification",
    "description": (
        "Send a notification to the user. Use THIS tool for ANY notification — do NOT "
        "call_ha_service on persistent_notification/notify. "
        "Channels: 'ha_persistent' = a persistent notification card in the Home Assistant "
        "dashboard (supports title + message; to remove one later, pass its notification_id "
        "together with an empty message to dismiss it); "
        "'ha_push' = mobile push (supports title); "
        "'apprise' = all configured Apprise URLs (Telegram/WhatsApp/ntfy/etc.); "
        "'retropanel' = Retro Panel kiosk toast."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": (
                    "Notification body text. Leave empty ONLY to dismiss an existing "
                    "persistent notification (together with its notification_id)."
                ),
            },
            "title": {
                "type": "string",
                "description": "Optional title/heading (used by 'ha_persistent' and 'ha_push').",
            },
            "channel": {
                "type": "string",
                "enum": ["ha_persistent", "ha_push", "apprise", "retropanel"],
                "description": "Delivery channel (see tool description).",
            },
            "notification_id": {
                "type": "string",
                "description": (
                    "Optional stable id for a persistent notification, so it can be "
                    "updated (same id overwrites) or dismissed later."
                ),
            },
        },
        "required": ["channel"],
    },
}
