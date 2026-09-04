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
# **Cio' che questo bump lascia indietro, detto invece che taciuto**: la
# 2.1.251 e' stata rilasciata e non e' mai stata verificata su una casa vera
# col passo 4 -- se questa riga arriva in produzione prima di quella lettura,
# la 2.1.251 sara' l'ennesima versione passata senza che nessuno l'abbia
# vista girare. E' esattamente il difetto che il paragrafo qui sotto
# descrive, ripetuto una volta di piu'. La 3.21.0 e' installabile ADESSO:
# la lettura costa un turno di chat e una `GET /api/health`, e va fatta
# prima che questa riga esca.
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
# Se la 2.1.260 desse problemi si torna alla 2.1.251, che e' uscita con la
# 3.21.0 e ha quindi girato su una casa vera -- anche se `ponte.cli` non e'
# ancora stato letto per confermarlo. Il ripiego precedente era la 2.1.234:
# resta valido come secondo passo indietro, ed e' l'ultima che qualcuno
# abbia guardato girare davvero.
RUN apk add --no-cache nodejs npm libgcc libstdc++ ripgrep \
    && npm install -g @anthropic-ai/claude-code@2.1.260 \
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
