ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Chat via abbonamento (Piano 2B): node + Claude CLI. Alpine/musl -> ripgrep di
# sistema (il ripgrep bundle di claude e' glibc). Node 22+ e' in Alpine 3.21.
#
# La CLI e' pinnata a una versione ESATTA, non a un major. Il pin al major
# (`@2`) non rendeva riproducibile un bel niente: risolveva all'ultima 2.x
# pubblicata al momento del build, quindi due immagini della STESSA versione
# di HIRIS potevano contenere due CLI diverse -- e se il ponte cambiava
# comportamento fra una consegna e l'altra, non c'era un colpevole leggibile.
# Con la versione esatta l'immagine costruita oggi e quella costruita fra sei
# mesi contengono la stessa CLI.
#
# Cosa costa, detto per intero: le patch della CLI non arrivano piu' da sole.
# Si resta su questa riga finche' qualcuno non la cambia a mano, comprese le
# correzioni di sicurezza. Aggiornare la CLI diventa un atto deliberato di chi
# rilascia, non un effetto collaterale del build: e' il prezzo del pin, ed e'
# la ragione per cui la riga va guardata a ogni giro di rilascio.
#
# Come si bumpa:
#   1. `npm view @anthropic-ai/claude-code version` -> l'ultima pubblicata
#   2. cambiare il numero nella riga `npm install -g` qui sotto
#   3. bumpare `config.yaml` (il Supervisor offre l'aggiornamento solo se la
#      versione dell'add-on cambia) e scrivere la voce nel CHANGELOG
#   4. dopo il deploy, la CLI che gira DAVVERO si rilegge da
#      `GET /api/health`, campo `ponte.cli`: e' li' che si verifica che il pin
#      sia arrivato fino al container, invece di fidarsi di questo file.
#      Il campo e' `null` finche' nessun turno e' passato -- «non ancora
#      visto», che non e' «assente»: basta una domanda in chat e poi
#      rileggere. Lo stesso oggetto porta `ponte.apiKeySource`, che vale
#      `none` quando si sta usando l'abbonamento e non una chiave a consumo.
# 28 agosto 2026 — alzata da 2.1.241 a 2.1.251 (otto uscite, tutte patch).
# 4 settembre 2026 — alzata da 2.1.251 a 2.1.260 (cinque uscite: 252, 257,
# 258, 259, 260; le altre non sono mai state pubblicate). Alzata SUBITO dopo
# il rilascio della 3.21.0, che portava la 2.1.251: e' il cancello
# `scripts/verifica_componenti.py` ad averla segnalata al push, e la scelta
# fu di non infilare una dipendenza non provata dentro un pacchetto provato.
# Questa riga e' quella decisione mantenuta -- il bump vive qui, da solo,
# fino al prossimo rilascio.
#
# **La 2.1.251 E' STATA VERIFICATA, e questa e' la prima volta che succede.**
# Il 04/09, add-on gia' sulla 3.21.0, un turno di chat e poi
# `GET /api/health`: `ponte.cli` ha risposto `"2.1.251"` (con
# `apiKeySource: "none"`, cioe' abbonamento). Il pin arriva davvero fino
# dentro il container -- cosa che fino a oggi era una speranza, non un fatto:
# ne' la 2.1.241 ne' la 2.1.234 erano mai state lette (vedi il paragrafo qui
# sotto). Il passo 4 non e' piu' un proposito, e' una lettura che qualcuno ha
# fatto.
#
# Resta da fare per la 2.1.260, e vale la stessa riga: dopo il rilascio, un
# turno e una GET.
#
# **Ne' la 2.1.241 ne' la 2.1.234 prima di lei erano mai state verificate su
# questo container.** Il 24 agosto la verifica fu rimandata «al prossimo
# giro» e cinque giorni dopo non era ancora stata fatta -- non per pigrizia,
# ma perche' l'unico modo di farla era leggere una riga di log **mentre** un
# turno passava. Un fatto che si puo' osservare solo di sfuggita e' un fatto
# che prima o poi nessuno osserva.
#
# Da questa versione quel fatto e' una lettura ripetibile: `GET /api/health`,
# campo `ponte.cli` (passo 4 qui sopra). Il pin continua a garantire la
# RIPRODUCIBILITA', non che la versione funzioni -- ma adesso la differenza
# fra le due si misura in un secondo, invece che aspettando il momento giusto.
#
# **La 2.1.260 E' STATA VERIFICATA il 07/09/2026**, add-on sulla 3.22.1:
# `GET /api/health` ha risposto `ponte.cli: "2.1.260"` (con
# `apiKeySource: "none"`). La riga «resta da fare» qui sopra e' quindi saldata:
# e' la seconda volta di fila che il pin viene letto dentro il container invece
# che sperato.
#
# 7 settembre 2026 — alzata da 2.1.260 a 2.1.263 (due uscite: 261 e 263; la
# 262 non e' mai stata pubblicata). Il cancello l'aveva segnalata durante il
# rilascio della 3.22.0, e per la regola del proprietario -- «se la CLI aumenta
# di una versione minima possiamo includerlo nell'aggiornamento; se il cancello
# lo segnala, nel prossimo lo aggiorniamo» -- il salto e' stato tenuto fuori da
# quel pacchetto ed entra qui, deciso PRIMA che la suite girasse.
#
# Resta da fare per la 2.1.263, e vale la stessa riga: dopo il rilascio, un
# turno e una GET.
#
# 9 settembre 2026 — alzata da 2.1.263 a 2.1.266 (due uscite: 265 e 266; la
# 264 non e' mai stata pubblicata). Il cancello l'aveva segnalata due volte --
# durante il rilascio della 3.23.2 e al push successivo -- e per la regola del
# proprietario il salto entra nel rilascio in preparazione (la 3.23.4),
# deciso PRIMA che la suite girasse.
#
# **ATTENZIONE, e va letta prima di fidarsi del ripiego**: la 2.1.263 non e'
# mai stata VISTA girare in questo container. Dal riavvio del 08/09
# `GET /api/health` risponde `ponte: null` -- «non ancora visto», che non e'
# «assente»: nessun turno di chat e' passato da allora. Quindi il passo 4 di
# questa annotazione e' in sospeso da DUE salti, ed e' il motivo per cui il
# ripiego qui sotto nomina la 2.1.260 e non la 2.1.263.
#
# Se la 2.1.266 desse problemi si torna alla **2.1.260**: e' l'ultima versione
# di cui esista una lettura vera (`ponte.cli` il 07/09/2026), ha girato su
# questa casa per due rilasci, ed e' uscita con la 3.22.0. La 2.1.263 sarebbe
# piu' recente ma non e' mai stata confermata: un ripiego che non si e' mai
# visto funzionare non e' un ripiego.
RUN apk add --no-cache nodejs npm libgcc libstdc++ ripgrep \
    && npm install -g @anthropic-ai/claude-code@2.1.266 \
    && npm cache clean --force
ENV USE_BUILTIN_RIPGREP=0

# Copy application source, manifest, and entrypoint
COPY app/ /usr/lib/hiris/app/
COPY config.yaml /usr/lib/hiris/config.yaml
COPY run.sh /usr/lib/hiris/run.sh
RUN chmod +x /usr/lib/hiris/run.sh && \
    find /usr/lib/hiris -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# Internal port — accessed only via HA Supervisor Ingress
EXPOSE 8099

WORKDIR /usr/lib/hiris
CMD ["/usr/lib/hiris/run.sh"]
