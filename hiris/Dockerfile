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
#   4. dopo il deploy, la CLI che gira DAVVERO si rilegge nel log, riga
#      «init del ponte», campo `cli=`: e' li' che si verifica che il pin
#      sia arrivato fino al container, invece di fidarsi di questo file
# 24 agosto 2026 — alzata da 2.1.234 a 2.1.241 nel giro di manutenzione che ha
# preceduto la fetta «costruire». **La 2.1.241 non e' ancora stata provata su
# questo container**, e finche' non lo e' questa riga vale meno di quanto
# sembri: il pin garantisce la RIPRODUCIBILITA', non che la versione funzioni.
# Si verifica col passo 4 qui sopra — la riga «init del ponte», campo `cli=` —
# nello stesso giro di verifiche live che la fetta «costruire» ha gia' in
# sospeso (spec §9): il ponte lo esercita qualunque turno di chat, quindi non
# costa un passo in piu'. Se la 2.1.241 dovesse dare problemi, si torna alla
# 2.1.234, che e' l'ultima provata sul serio.
RUN apk add --no-cache nodejs npm libgcc libstdc++ ripgrep \
    && npm install -g @anthropic-ai/claude-code@2.1.241 \
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
