# **L'immagine di base e' fissata per IMPRONTA** (reperto D-3, 23/09/2026),
# e sta QUI e non in `build.yaml` per una ragione misurata sulla casa vera.
#
# Il pin nacque in `build.yaml` con la 3.64.0 e **ne ruppe l'aggiornamento**.
# Il Supervisor valida `build_from` con `RE_DOCKER_IMAGE_BUILD`
# (`supervisor/apps/validate.py`), che non ammette `@` -- quindi non ammette
# un'impronta. E non si ferma: stampa un WARNING e **prosegue coi default**,
# cioe' `ghcr.io/home-assistant/base:latest`, che e' Alpine nuda senza Python.
# La costruzione moriva tre passi piu' sotto con `/bin/ash: pip3: not found`,
# exit 127, e l'errore non nominava la causa. Un cancello che avvisa e tira
# dritto e' peggio di uno che manca: sposta il guaio lontano da dove sta.
#
# Nel Dockerfile Docker l'impronta la accetta -- ed e' anche dove il
# Supervisor stesso chiede di mettere i parametri di costruzione: «App uses
# build.yaml which is deprecated. Move build parameters into the Dockerfile
# directly», stampato a ogni giro.
#
# Uno stadio per architettura e l'ultimo `FROM` sceglie il suo. BuildKit pota
# gli stadi che non servono, quindi la base dell'altra architettura non viene
# nemmeno scaricata -- **verificato su Docker vero** (29.4.3, buildx 0.33.0)
# prima di rilasciare, con la stessa riga di comando che usa il Supervisor.
#
# **`BUILD_ARCH` non ha un default, ed e' deliberato**: senza, una costruzione
# che non lo passasse prenderebbe in silenzio l'architettura sbagliata invece
# di rompersi. Il Supervisor lo passa sempre (`--build-arg BUILD_ARCH=amd64`).
#
# **Cosa costa, detto per intero**: le patch della base non arrivano piu' da
# sole, comprese quelle di sicurezza. Aggiornarla e' un atto deliberato di chi
# rilascia, e `scripts/verifica_componenti.py` guarda queste righe a ogni giro
# perche' «fissato per impronta» non diventi «fermo da un anno».
#
# Come si ribumpano:
#   1. scegliere l'etichetta nuova (es. 3.14-alpine3.22)
#   2. risolverla in impronta:
#      docker buildx imagetools inspect ghcr.io/home-assistant/<arch>-base-python:<etichetta>
#   3. cambiare impronta E commento -- l'etichetta resta scritta sopra perche'
#      un'impronta da sola non dice quale Python ci sia dentro
ARG BUILD_ARCH

# 3.13-alpine3.21
FROM ghcr.io/home-assistant/amd64-base-python@sha256:35d1dcdc69a44fdaaea2f3e14cf762176f03d4cadd6a8c77e8cafa8d2644848b AS base-amd64
# 3.13-alpine3.21
FROM ghcr.io/home-assistant/aarch64-base-python@sha256:de1321d958f9f2ab1ea15c478285a602c0750111a8e4ee11dcb7f250ccf6c590 AS base-aarch64

FROM base-${BUILD_ARCH}

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
# **La 2.1.263 E' STATA VISTA, e la nota qui sopra e' saldata.** L'annotazione
# precedente diceva «non e' mai stata VISTA girare in questo container»: era
# vera quando fu scritta e ha smesso di esserlo il **09/09/2026 alle 18:02**,
# quando `GET /api/health` sull'add-on 3.23.2 ha risposto
# `ponte.cli: "2.1.263"` (con `apiKeySource: "none"`, cioe' abbonamento).
# Riletta il 10/09/2026: il passo 4 non e' piu' in sospeso da due salti, ne
# resta in sospeso uno solo.
#
# 10 settembre 2026 — alzata da 2.1.266 a 2.1.267 (un'uscita sola). Il cancello
# l'aveva segnalata durante il rilascio della 3.24.0, che e' uscita con
# `HIRIS_COMPONENTI_OK=1`; il proprietario ha poi deciso di alzarla **subito**,
# dentro la 3.24.1, e non di rimandarla ancora. Decisa PRIMA che la suite
# girasse, come chiede la regola.
#
# **La 2.1.267 E' STATA VERIFICATA il 10/09/2026 alle 20:21**, add-on sulla
# 3.24.1: `GET /api/health` ha risposto `ponte.cli: "2.1.267"` (con
# `apiKeySource: "none"`, cioe' abbonamento). Il passo 4 e' saldato **lo stesso
# giorno** in cui il pin e' salito -- non «al prossimo giro», che e' il modo in
# cui questa nota e' rimasta in sospeso per due salti di fila.
#
# Se la 2.1.267 desse problemi si torna alla **2.1.263**: e' l'ultima versione
# PRECEDENTE di cui esista una lettura vera dentro questo container
# (`ponte.cli` il 09/09/2026), ed e' uscita con la 3.23.0. La 2.1.266 non e'
# mai stata confermata -- e' stata scavalcata prima di girare -- e un ripiego
# che non si e' mai visto funzionare non e' un ripiego.
#
# 11 settembre 2026 — alzata da 2.1.267 a **2.1.268** (un'uscita sola), col
# rilascio della 3.26.0, come chiede la regola: il cancello ha parlato durante
# questa fetta e il pin sale col rilascio in cui ha parlato, non al giro dopo.
#
# **La 2.1.268 E' STATA VERIFICATA l'11/09/2026 alle 11:03**, add-on sulla
# 3.26.0: `GET /api/health` ha risposto `ponte.cli: "2.1.268"` (con
# `apiKeySource: "none"`, cioe' abbonamento), dopo un turno di chat. Il passo 4
# e' saldato **il giorno dopo** il rilascio, alla prima verifica dal vivo della
# 3.26.0 -- non «al prossimo giro», che e' il modo in cui questa nota e'
# rimasta in sospeso per due salti di fila.
#
# Se la 2.1.268 desse problemi il ripiego e' la **2.1.267**, che e' stata letta
# davvero dentro questo container il 10/09/2026 alle 20:21.
#
# 12 settembre 2026 — alzata da 2.1.268 a **2.1.269** (un'uscita sola), col
# rilascio della 3.29.0: il cancello dei componenti ha parlato durante la fetta
# delle operazioni e il pin sale col rilascio in cui ha parlato, non al giro
# dopo.
#
# **Il passo 4 di questa nota e' APERTO**: la 2.1.269 non e' ancora stata letta
# dentro il container. Si salda alla prima verifica dal vivo della 3.29.0,
# leggendo `ponte.cli` da `GET /api/health` dopo un turno di chat. Finche' quel
# numero non e' stato letto davvero, questa riga dice «pin alzato», non
# «versione verificata»: sono due fatti diversi, e confonderli e' come questa
# nota e' rimasta in sospeso per due salti di fila.
#
# Se la 2.1.269 desse problemi il ripiego e' la **2.1.268**, verificata
# l'11/09/2026 alle 11:03 (vedi sopra).
#
# 13 settembre 2026 — alzata da 2.1.269 a **2.1.270**, col rilascio della
# 3.30.0: il cancello dei componenti ha parlato di nuovo, e il pin sale col
# rilascio in cui parla.
#
# **Due pin di fila non verificati, e va detto invece che lasciato intuire.**
# La 2.1.269 e' uscita con la 3.29.0 di ieri e **non e' mai stata letta dentro
# il container**: la 3.29.0 e' stata pushata ma l'add-on non e' stato ancora
# aggiornato. Quindi il ripiego di oggi **non e' la 2.1.269** -- una versione
# mai vista girare non e' un ripiego -- ma la **2.1.268**, che e' l'ultima con
# una lettura vera di `ponte.cli` da `GET /api/health` (11/09/2026, 11:03).
#
# Il passo 4 resta APERTO per tutte e due: si salda alla prima verifica dal
# vivo della 3.30.0, leggendo `ponte.cli` dopo un turno di chat. Finche' quel
# numero non e' stato letto, queste righe dicono «pin alzato», non «versione
# verificata»: sono due fatti diversi.
#
# **14 settembre 2026 — il passo 4 e' SALDATO**: `ponte.cli` letto da
# `GET /api/health` sulla casa vera, **2.1.270**. Il debito di due pin non
# verificati e' chiuso, e da qui il ripiego torna a essere l'ultima versione
# davvero letta girare.
#
# 15 settembre 2026 — alzata da 2.1.270 a **2.1.272**, col rilascio della
# 3.46.0. Il cancello ne aveva parlato durante la 3.45.0, che parlava d'altro:
# **il pin sale nel rilascio successivo a quello in cui il cancello parla**, e
# questo e' quello. Ripiego: la **2.1.270**, l'ultima letta dentro il
# container. Il passo 4 torna APERTO per la 2.1.272 e si salda al primo turno
# di chat dopo l'aggiornamento -- a add-on appena riavviato `ponte` e' `null`,
# perche' quel numero nasce da un turno, non dall'avvio.
#
# 18 settembre 2026 — alzata da 2.1.272 a **2.1.276**, col rilascio della
# 3.49.0, **per decisione esplicita del proprietario**. E' un'eccezione alla
# regola della riga sopra: il cancello ha parlato durante la 3.48.x, e la
# regola avrebbe mandato il pin al rilascio dopo questo. Il proprietario ha
# chiesto di aggiornarlo adesso, e questa riga registra chi l'ha deciso invece
# di far sembrare che la regola dicesse cosi'. Ripiego: la **2.1.272**, il pin
# che questa riga sostituisce (la **2.1.270** resta l'ultima davvero letta
# dentro il container). Il passo 4 e' APERTO per la 2.1.276 e si salda al primo
# turno di chat dopo l'aggiornamento.
# **Un percorso FISSO e una prova** (reperto D-4, 22/09/2026).
#
# **`--ignore-scripts` NON si puo' usare qui, ed e' misurato.** La 3.61.0 lo
# aveva aggiunto: la costruzione e' fallita con
#
#     Error: claude native binary not installed.
#
# `@anthropic-ai/claude-code` **ha bisogno** del proprio script di
# post-installazione, che mette a posto il binario nativo. Il costo di vietarlo
# non era zero: era la CLI che non esiste. Resta su `npm ci` nel CI, dove i
# pacchetti sono altri e dove funziona.
#
# **Il `--version` qui sotto l'ha preso al momento della costruzione**, che e'
# il punto per cui esiste: non e' uscito niente di rotto verso nessuno. La
# stessa rete che al reperto A-2 era mancata.
#
# Il COLLEGAMENTO: fino a oggi il sottoprocesso si invocava come `claude` e
# chi lo esegue lo cercava in `PATH`, che non e' una cosa che questo
# prodotto controlla. Adesso c'e' un percorso nostro, accanto al prodotto.
#
# E il `--version` nella STESSA istruzione: spegnere gli script di
# post-installazione e' una cosa che nessuna suite puo' provare. Se
# rompesse la CLI, a rompersi qui e' la COSTRUZIONE DELL'IMMAGINE, e non
# esce niente verso nessuno -- e' la rete che il 22/09 e' mancata al
# reperto A-2, dove una verifica non provabile e' arrivata in produzione.
RUN apk add --no-cache nodejs npm libgcc libstdc++ ripgrep \
    && npm install -g @anthropic-ai/claude-code@2.1.276 \
    && npm cache clean --force \
    && mkdir -p /usr/lib/hiris \
    && ln -sf "$(command -v claude)" /usr/lib/hiris/claude \
    && /usr/lib/hiris/claude --version
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
