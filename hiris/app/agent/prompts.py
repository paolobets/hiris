"""I prompt del runner del ponte (agent/runner.py), il percorso
chat-via-abbonamento.

fetta E4 Task 8 ("un bot solo"): `_SYSTEM` e `build_holistic_prompt` -- il
prompt della "revisione olistica sull'abbonamento" -- sono usciti con il ramo
che li chiamava. Chiedevano al modello un verdetto e UNA azione a basso
rischio in un blocco ```json```: due cose che HIRIS 2.0 non fa piu' (l'azione
e' uscita con la fetta E2, l'organismo proattivo con la E3) per un job
(`kind="holistic"`) che nessuno puo' piu' accodare.

fetta "il ponte riceve il nucleo" (parita' A, Task 2): il ponte non riceve
piu' soltanto `history` + `system_prompt`. Riceve anche il `contesto` -- la
STESSA stringa che il ramo sincrono passa al runner, composta da
`handlers_chat.componi_contesto_chat` (nucleo + sessioni precedenti). Da qui
in poi questo file compone il system prompt del ponte NELLO STESSO ORDINE del
ramo sincrono (`claude_runner.py`, `ClaudeRunner.chat`): BASE -> persona ->
modificatori -> guida -> contesto. Le costanti di BASE si IMPORTANO da
`..claude_runner`: una seconda copia qui sarebbe la "funzione doppia" vietata
da CLAUDE.md:70-72. (Nessun ciclo: `claude_runner.py` importa solo stdlib,
`anthropic` e `.backends.pricing` -- mai `agent/`.)

Fix round 1, Critical 1: di BASE il ponte compone la sola META' VERA. Vedi
`build_chat_messages` e il commento sopra `BASE_IDENTITA` in claude_runner.py.
"""
# fix della review totale della fetta (m-3): `BASE_SYSTEM_PROMPT` NON e' piu'
# importata. Questo file non la usa -- il ternario di `build_chat_messages`
# compone `BASE_IDENTITA + BASE_REGOLE_STRUMENTI` -- e l'unico lettore che le
# restava era un assert (`prompts.BASE_SYSTEM_PROMPT is BASE_SYSTEM_PROMPT`,
# tests/test_ponte_riceve_il_nucleo.py), cioe' un import tenuto in vita dal
# test che lo pinnava. I due assert sulle META' restano, e sono quelli che
# contano: sono i simboli che il ponte compone davvero.
from ..claude_runner import (
    BASE_IDENTITA,
    BASE_REGOLE_STRUMENTI,
    RESTRICT_PROMPT,
    COMPACT_PROMPT,
    MINIMAL_PROMPT,
)

# Review finale fetta E3, difetto I-1/I-2 dal lato abbonamento: la versione
# precedente diceva al modello «Hai accesso a strumenti per leggere lo stato
# reale della casa (entita', aree, meteo, storico) e, quando serve, per
# agire ... Le azioni possono richiedere una conferma dell'utente» -- tre
# falsita' in tre righe. Questo runner ragiona in PURO TESTO: non riceve alcun
# catalogo di strumenti (l'MCP interno che glieli serviva e' uscito alla fetta
# E2 Task 3 -- vedi il docstring in cima a agent/runner.py, e
# `_chat_claude_args`, che non passa ne' `--mcp-config` ne' `--allowedTools`),
# HIRIS non agisce (fette E2/E3), e le conferme sono uscite con l'impianto OTP
# (fetta E2 Task 5).
#
# fetta E4, fix della review totale (m11): questa riga del prompt diceva
# «HIRIS conosce e non agisce». La formula e' vera del PRODOTTO, non di QUESTO
# percorso: il capoverso immediatamente precedente ha appena detto al modello
# che qui non puo' leggere NULLA della casa. E' una stringa di prompt, non un
# commento: il modello la legge con la stessa autorita' con cui gli neghiamo
# gli strumenti, e «conosce» gli darebbe il permesso di credere di sapere.
# Resta solo «non agisce», che qui e' vero due volte.
#
# fetta «comandare» (Task 6): «non agisce» ha smesso di essere vero DUE
# volte, ed e' rimasto vero UNA. Il Task 5 ha dato a HIRIS `esegui` (catalogo
# unico, `casa/strumenti.py`): il prodotto agisce. Questo turno no -- qui non
# c'e' nessuno strumento da chiamare -- e la differenza fra le due cose e'
# tutta nella frase. «HIRIS non agisce» era una proprieta' del PRODOTTO
# affermata da un percorso che parla solo di se': lo stesso errore di scala
# che il fix m11 qui sopra ha corretto su «conosce», ripetuto sull'altra
# meta' della formula. Il testo dice ora cio' che questo turno puo': non
# accendere, non spegnere, non chiamare un servizio -- «perche' lo strumento
# che lo fa qui non c'e', non perche' HIRIS non sappia farlo». La seconda
# proposizione non e' cortesia: senza, un modello che leggesse questa riga
# come una proprieta' del prodotto negherebbe la capacita' anche all'utente
# che gliela chiede per il turno dopo.
#
# Cio' che NON e' cambiato di una virgola e' l'altra meta': in questo turno
# gli strumenti non ci sono davvero, e un modello che si credesse capace di
# agire annuncerebbe accensioni mai avvenute -- il «preso nota» senza aver
# salvato, in un'altra forma. Per questo `esegui` entra anche nell'elenco
# degli strumenti che il testo NOMINA PER NEGARLI: se il prompt di sopra lo
# ordina, qui quell'ordine non si applica.
#
# Serve anche a CORREGGERE il prompt che la precede: il system prompt delle
# impostazioni della chat (`impostazioni_chat.DEFAULT_SYSTEM_PROMPT`, via
# `handlers_chat._build_system_prompt`) e' scritto per il percorso SINCRONO e
# nomina in backtick alcuni degli strumenti. Di la' gli strumenti di
# `casa/strumenti.py` esistono davvero; QUI no. Senza questa smentita
# esplicita -- che sta DOPO la persona, ed e' il motivo per cui l'ordine di
# composizione conta -- il modello leggerebbe «usa `cerca` e `guarda`» senza
# alcun modo di scoprire che non ci sono: di nuovo il "preso nota" senza aver
# salvato, in un'altra forma. La disciplina e' quella del nucleo: dichiarare
# cio' che si ignora invece di fingerlo.
#
# Fix round 1, Critical 1: fino a poco fa la smentita doveva coprire anche
# `BASE_SYSTEM_PROMPT`, che il Task 2 aveva cominciato a passare INTERO al
# ponte -- ordini come «Usa SEMPRE gli strumenti per dati sulla casa» e
# «chiama ricorda subito» rivolti a un percorso senza strumenti. Non piu': la
# meta' che nomina gli strumenti (`BASE_REGOLE_STRUMENTI`) qui NON viene
# emessa affatto (vedi `build_chat_messages`). La smentita di testo restava
# l'unica difesa contro un ORDINE di chiamare uno strumento inesistente, ed e'
# esattamente il bug per cui `ricorda` e' nato: un ordine non emesso e' una
# difesa, una frase che lo contraddice e' una speranza.
#
# fetta "il ponte riceve il nucleo" (parita' A, Task 2): la frase «non puoi
# LEGGERE lo stato della casa ... o una sezione con lo stato della casa, qui
# non ci sono» e' uscita, perche' da questo task e' FALSA -- il contesto del
# nucleo arriva davvero, e una sezione con lo stato della casa c'e'. Dirla
# ancora sarebbe la falsita' SPECULARE: lo stesso difetto di prima, girato al
# contrario. Cio' che resta vero, e che il prompt continua a dire, e' che non
# si puo' GUARDARE ADESSO: la fotografia e' stata presa una volta sola, quando
# il messaggio e' stato accodato, e in questo turno non si aggiorna.
# L'affermazione e' ancorata al TURNO e non a un'ora perche' il nucleo non
# timbra (`casa/nucleo.py::componi` e' pura e non compone nessuna data): un
# orario nel prompt sarebbe inventato, mentre "in questo turno" e' l'unica
# formulazione che non puo' diventare falsa.
_GUIDA_SENZA_STRUMENTI = (
    "In questa conversazione NON hai alcuno strumento di HIRIS: non puoi "
    "guardare adesso lo stato della casa (entita', aree, dispositivi, meteo, "
    "storico) e non puoi salvare nuovi ricordi ne' andare a cercarne altri "
    "adesso. Se il prompt qui sopra nomina "
    "degli strumenti (per esempio `cerca`, `guarda`, `ricorda`, `richiama`, "
    "`esegui`) o "
    "ti ordina di chiamarli, qui non ci sono: quelle istruzioni non si "
    "applicano. Non inventare stati, valori o entita', e non dire di aver "
    "guardato o di aver preso nota di qualcosa.\n"
    "In questo turno non puoi nemmeno far succedere niente in casa: non puoi "
    "accendere, spegnere o chiamare un servizio di Home Assistant, perche' "
    "lo strumento che lo fa (`esegui`) qui non c'e' -- non perche' HIRIS non "
    "sappia farlo. Non c'e' nessuna conferma da "
    "chiedere, perche' non c'e' nessuna azione in attesa.\n"
    "Se per rispondere servirebbe un valore aggiornato ADESSO, DILLO in una "
    "frase -- che in questa conversazione non puoi andare a guardarlo -- "
    "invece di tirare a indovinare."
)

# fetta "il ponte riceve il nucleo" (parita' A, Task 2), Step 3: il ramo della
# fetta B, scritto ORA e deliberatamente NON raggiungibile dalla produzione.
# E' un ORFANO DICHIARATO: `strumenti_attivi` resta False in tutta la fetta A
# (`agent/runner.py::_reason_chat` non lo passa), quindi il suo unico lettore
# oggi e' un test (tests/test_ponte_riceve_il_nucleo.py). Esiste ora, e non
# dopo, perche' riscrivere questo prompt una TERZA volta e' esattamente il
# difetto che il docstring in cima al file documenta: cosi' la fetta B cambia
# un argomento invece di riscrivere la composizione (vedi
# docs/superpowers/plans/2026-08-10-il-ponte-riceve-gli-strumenti.md).
#
# fetta "il ponte riceve gli strumenti" (parita' B, Task 3): l'orfano e' stato
# RACCOLTO -- `_reason_chat` passa `strumenti_attivi` e questo testo esce
# davvero, quando la sonda dice che gli strumenti ci sono. Cio' che gli
# impedisce di diventare falso non e' piu' un pin sull'assenza degli strumenti
# ma l'INVARIANTE nei due versi (tests/test_strumenti_al_ponte.py):
# `--mcp-config` nell'argv <=> questo testo nel system. Mai l'uno senza l'altro.
#
# **La correzione di questo testo (riserva 1 della sezione D del progetto).**
# La fetta A non poteva sapere con quale nome il modello avrebbe visto gli
# strumenti, e aveva scritto «Possono comparire col prefisso del server (per
# esempio `mcp__hiris__cerca`)». Ora il nome e' deciso e la frase e' TROPPO
# DEBOLE per essere vera: `_chat_claude_args` passa
# `--allowedTools mcp__hiris__cerca,mcp__hiris__guarda,mcp__hiris__ricorda,
# mcp__hiris__richiama` (i nomi di `runner.nomi_mcp()`, derivati da
# `casa/strumenti.py`), quindi la forma prefissata non e' una possibilita' fra
# due: e' l'UNICA in cui gli strumenti gli sono serviti e l'unica che potra'
# chiamare. Un «possono comparire» lascerebbe il modello a credere che
# `cerca` nudo sia altrettanto valido -- e una chiamata a un nome che non
# esiste e' proprio il modo in cui questo prodotto ha gia' prodotto un «preso
# nota» senza aver salvato. Il testo nomina quindi i nomi VERI, e
# ricollega a loro i nomi nudi che la persona (il system prompt delle
# impostazioni della chat) continua a usare.
#
# fetta «comandare» (Task 6). Tre cose cambiano qui, e una NON cambia.
#
# ① I nomi sono cinque: `mcp__hiris__esegui` e' nell'argv da `33da82b`
#   (`--allowedTools` deriva da `runner.nomi_mcp()`, che deriva dal catalogo
#   unico), e l'invariante argv <=> prompt vuole che il testo lo nomini --
#   e' cio' che pinna `test_col_ramo_attivo_il_prompt_afferma_gli_strumenti_
#   prefissati` in tests/test_agent_runner_inaddon.py. Fra questo commit e
#   quello il prompt affermava CINQUE strumenti serviti e ne nominava
#   QUATTRO, per giunta dichiarando «HIRIS non agisce comunque»: quel test
#   era `xfail(strict=True)` apposta, cosi' il debito si esigeva da solo.
#
# ② «STESSI quattro strumenti» -> «STESSI strumenti». Il numero nel testo del
#   prompt non aggiungeva niente al ricollegamento dei nomi nudi (che si fa
#   elencandoli, non contandoli) e sarebbe l'ennesima dichiarazione da tenere
#   allineata a mano.
#
# ③ Il capoverso «HIRIS non agisce comunque: non accendi, non spegni ...» e'
#   USCITO, ed e' la ragione per cui questo task esiste: era un ordine di non
#   usare uno strumento che il turno successivo serve davvero. Al suo posto
#   c'e' la sola cosa che questo testo -- quello dei NOMI -- ha il compito di
#   dire su `esegui`: che gli id vanno presi da `mcp__hiris__cerca` e non
#   ricavati dal nome. E' l'errore piu' probabile («la luce della cucina»
#   passata come id) ed e' un problema di NOMI, cioe' materia di questa
#   guida. Le altre regole dell'azione -- raccontare cosa e' successo,
#   l'ambiguita', il ricordo-preferenza -- NON stanno qui ma in
#   `claude_runner.BASE_REGOLE_STRUMENTI`, che su questo ramo e' emessa e sul
#   percorso sincrono pure: scriverle qui le avrebbe date al ponte e negate
#   alla chat vera (vedi il commento sopra `BASE_IDENTITA` in claude_runner.py).
#
# Cio' che NON cambia: «non dire di aver guardato o di aver preso nota se non
# hai chiamato lo strumento» -- che acquista un terzo caso, «di aver acceso
# qualcosa». E' la stessa regola di sempre, e da questa fetta ha una vittima
# in piu' da proteggere.
#
# fetta «lo schedulatore» (Task 6). Da 6 a 9: entrano `prometti`,
#   `promesse`, `disdici` -- lo stesso "li nomini, il modello li chiama coi
#   nomi prefissati" di sopra, non un secondo giro di logica. `prometti` NON
#   e' un secondo `esegui`: mette da parte un'azione o una domanda per un
#   istante futuro, verificata SUBITO contro questa installazione -- il testo
#   lo dice esplicitamente (ADESSO / PIU' TARDI) perche' il modello non lo
#   confonda con l'unico strumento che scrive nella casa nel turno stesso.
_GUIDA_CON_STRUMENTI = (
    "In questa conversazione HAI gli strumenti di HIRIS. Nell'elenco degli "
    "strumenti li trovi col prefisso del server che te li serve, ed e' quella "
    "l'unica forma in cui puoi chiamarli: `mcp__hiris__cerca` e "
    "`mcp__hiris__guarda` per lo stato della casa, `mcp__hiris__legami` per "
    "sapere chi tocca una cosa (quali automazioni, script, scene o gruppi la "
    "usano), `mcp__hiris__ricorda` e `mcp__hiris__richiama` per la memoria di "
    "cio' che le persone ti hanno detto, `mcp__hiris__esegui` per far "
    "succedere qualcosa in casa ADESSO, `mcp__hiris__prometti` per mettere "
    "da parte un'azione o una domanda per PIU' TARDI (verificata subito "
    "contro questa casa, non quando arriva il momento di mantenerla), "
    "`mcp__hiris__promesse` per sapere cosa e' ancora in sospeso o com'e' "
    "andata, `mcp__hiris__disdici` per annullare una promessa non ancora "
    "mantenuta. Quando il prompt qui sopra parla di `cerca`, "
    "`guarda`, `legami`, `ricorda`, `richiama`, `esegui`, `prometti`, "
    "`promesse` o `disdici` parla di questi "
    "STESSI strumenti, non di altri: usa il nome prefissato per chiamarli.\n"
    "Quando serve un valore CORRENTE chiama lo strumento invece di rispondere "
    "con cio' che leggi nel contesto qui sotto: guarda adesso. Non inventare "
    "stati, valori o entita', e non dire di aver guardato, di aver preso "
    "nota o di aver acceso qualcosa se non hai chiamato lo strumento.\n"
    "Gli id delle entita' che passi a `mcp__hiris__esegui` sono quelli ESATTI "
    "di questa casa: non li inventi e non li ricavi dal nome. Se hai solo il "
    "NOME di una cosa chiama prima `mcp__hiris__cerca` e usa l'id che ti "
    "risponde.\n"
    "Gli id fra parentesi che vedi nell'albero della casa -- `Nome (id: X)` -- "
    "sono gia' gli identificatori esatti: se un'area, un piano o "
    "un'automazione li porta con se', usali direttamente e non chiamare "
    "`mcp__hiris__cerca` per qualcosa che hai gia'.\n"
    "Se devi risolvere piu' nomi nella stessa richiesta, chiama "
    "`mcp__hiris__cerca` UNA sola volta con tutto il testo invece di una "
    "chiamata per nome.\n"
    "Se devi fare piu' letture indipendenti -- piu' `mcp__hiris__guarda`, "
    "piu' `mcp__hiris__legami` -- chiamale IN PARALLELO nella stessa "
    "risposta: il ciclo conta un giro per risposta, non per chiamata.\n"
    "Se invece la richiesta riguarda una STANZA, un piano, un'etichetta o un "
    "dispositivo, passali a `mcp__hiris__esegui` cosi' come sono (`aree`, "
    "`piani`, `etichette`, `dispositivi`) e NON raccogliere gli id a mano: li "
    "risolve Home Assistant, che e' l'unico a saperli tutti. Raccoglierli a "
    "mano significa spegnerne quattordici su quindici e dire di averle spente "
    "tutte."
)

# Le due frasi sul CONTESTO, complementari fra loro: una sola delle due entra
# nel prompt, e quale lo decide il `contesto` ricevuto.
#
# Perche' stanno FUORI dalle due guide invece che dentro: un job accodato
# PRIMA di questo deploy arriva al runner senza la chiave `contesto` (silenzio
# dichiarato ①, vedi `agent/runner.py::_reason_chat`). Se «la fotografia qui
# sotto» vivesse dentro `_GUIDA_SENZA_STRUMENTI`, quel job leggerebbe un
# prompt che promette una fotografia che non c'e' -- la stessa falsita' che
# questo task esiste per chiudere, riaperta dal caso limite. Tenendole
# separate la guida resta UNA (un solo posto dove si dice cosa il modello ha e
# non ha) e la frase sul contesto dice sempre il vero.
# fetta "il ponte riceve gli strumenti" (parita' B, Task 3, fix round 1,
# Important 1): questo testo esce da SEMPRE su entrambi i rami -- e' l'ULTIMA
# cosa che il modello legge prima del blocco `## La casa` -- ma era scritto
# quando il ramo con gli strumenti non esisteva. Due sue clausole, accese le
# quattro chiamate, diventavano un CONTRORDINE alla riga che le precede di
# poche parole (`_GUIDA_CON_STRUMENTI`: «quando serve un valore CORRENTE
# chiama lo strumento ... guarda adesso»), ed erano per giunta FALSE al
# presente. Sono uscite:
#
#   - «non e' aggiornabile in questo turno»: col ramo attivo la fotografia
#     E' aggiornabile -- si chiama `mcp__hiris__guarda`. Sul ramo di degrado
#     la frase e' ridondante, non necessaria: `_GUIDA_SENZA_STRUMENTI` dice
#     gia' «non puoi guardare adesso lo stato della casa» e «se per
#     rispondere servirebbe un valore aggiornato ADESSO, DILLO». Verificato
#     riga per riga prima di togliere, non assunto.
#   - «Se ti chiedono cosa ti hanno detto, cercalo li' dentro invece di
#     rispondere che non puoi richiamarlo»: nata come COMPENSAZIONE
#     dell'assenza di `richiama` (fetta A, fix round 1, Important 1). Col
#     ramo attivo `richiama` c'e', e mandare il modello a frugare nella
#     fotografia invece di chiamarlo produce esattamente il sintomo che il
#     tester non saprebbe distinguere da «gli strumenti non funzionano»:
#     `status: connected` nel log e NESSUNA `tools/call`. Cio' che la
#     compensazione doveva ottenere resta detto due volte in questo stesso
#     testo -- «ricordi e sessioni precedenti compresi» e «Usala per
#     rispondere» -- e il pin che vietava di negare la memoria
#     (`"richiamare ricordi" not in system`) e' intatto.
#
# Cio' che RESTA e' vero su entrambi i rami: la fotografia esiste, e' presa
# all'accodamento, non contiene tutto, e non va spacciata per una lettura
# fatta adesso (col ramo attivo una lettura fatta adesso esiste davvero: e'
# il risultato dello strumento, non questo blocco).
# Fix del 2026-08-18, da una risposta vera sbagliata. Alla domanda «stato
# casa» il modello ha premesso «dallo snapshot che ho, non e' una lettura in
# tempo reale», ha elencato la fotografia e si e' OFFERTO di guardare adesso.
# Aveva gli strumenti: doveva guardare, non offrirsi.
#
# La riserva qui sotto resta giusta -- la fotografia e' presa all'accodamento
# e non va spacciata per una lettura fatta adesso -- ma da sola insegnava
# soltanto a DIFFIDARNE. Chi diffida di cio' che ha e non usa cio' che puo'
# chiamare produce esattamente quella risposta: un disclaimer al posto di un
# fatto. La riserva e' una ragione per ANDARE A GUARDARE, non per scusarsi.
_CONTESTO_PRESENTE = (
    "Cio' che sai della casa -- e di cio' che le persone ti hanno detto, "
    "ricordi e sessioni precedenti compresi -- e' la fotografia qui sotto, "
    "presa quando e' arrivato questo messaggio: non contiene tutto. Usala per "
    "rispondere e dichiara apertamente quando cio' che serve non c'e', ma non "
    "presentarla come una lettura fatta adesso.\n"
    "Se la domanda riguarda lo STATO CORRENTE della casa -- com'e' adesso, "
    "cosa e' acceso, come sta una stanza -- e hai gli strumenti, CHIAMALI e "
    "rispondi con cio' che ti dicono. Non premettere che la tua e' una "
    "fotografia per poi offrirti di guardare: guarda."
)

_CONTESTO_ASSENTE = (
    "In questo turno non hai nemmeno la fotografia della casa: questo "
    "messaggio e' arrivato in coda senza il contesto, e non c'e' modo di "
    "recuperarlo ora. Rispondi con cio' che sai dalla conversazione stessa e "
    "dillo apertamente se per rispondere servirebbe conoscere la casa."
)

# Fix della review totale della fetta (m-2): questa istruzione diceva
# «Rispondi SEMPRE in italiano». Era l'UNICA istruzione di lingua che il ponte
# riceveva -- "Rispondi nella lingua dell'utente" viveva in
# `BASE_REGOLE_STRUMENTI`, la meta' che il ponte non emette -- e imponeva al
# ponte una lingua che il percorso sincrono non impone: un utente che scrive
# in inglese riceveva inglese di la' e italiano di qua. Ora quella riga sta in
# `BASE_IDENTITA` (vedi il commento del taglio in claude_runner.py) e arriva
# a ENTRAMBI i percorsi: lasciare qui «SEMPRE in italiano» significherebbe
# contraddirla dentro lo stesso prompt -- il system dice una cosa, l'ultima
# riga dell'utente ne dice un'altra, e vince l'ultima letta. Allineata.
_CHAT_INSTRUCTION = (
    "Rispondi ORA come l'assistente, proseguendo la conversazione sopra. "
    "Rispondi nella lingua dell'utente, con una risposta breve e pertinente. "
    "Nella risposta finale usa testo semplice: niente blocchi di codice o JSON."
)


def build_chat_messages(system_prompt: str, history: list, *,
                        contesto: str = "",
                        strumenti_attivi: bool = False,
                        restrict_to_home: bool = False,
                        response_mode: str = "") -> tuple[str, str]:
    """Chat-via-abbonamento: separa il SYSTEM prompt (BASE + persona HIRIS +
    guida + contesto della casa) dal prompt UTENTE (trascritto conversazione +
    istruzione formato). Il system va passato al CLI via --system-prompt
    cosi' il modello E' HIRIS e non Claude Code.

    fetta E4 Task 8: questo docstring diceva «e puo' usare i tool MCP» --
    falso dalla fetta E2 Task 3, che ha tolto l'MCP interno insieme al server
    che lo serviva.

    fetta "il ponte riceve il nucleo" (parita' A, Task 2): diceva anche che
    «il system prompt composto qui e' l'unica cosa che il modello riceve,
    oltre alla trascrizione» -- vero finche' il job del ponte portava solo
    `history` + `system_prompt`. Ora porta anche `contesto`, la stessa
    stringa che il ramo sincrono passa al runner
    (`handlers_chat.componi_contesto_chat`: nucleo + sessioni precedenti), e
    quella stringa entra in coda al system. Resta vero -- e la guida continua
    a dirlo -- che gli STRUMENTI non ci sono: `contesto` e' una fotografia,
    non un accesso.

    L'ordine dei blocchi e' quello del ramo sincrono (`ClaudeRunner.chat`),
    perche' i due percorsi devono comporre le stesse cose nello stesso ordine
    o divergono in silenzio: BASE -> `system_prompt` (la persona) -> i
    modificatori di comportamento (`restrict_to_home`, `response_mode`) ->
    la guida -> `contesto`. La guida sta DOPO la persona per poterla
    smentire: e' scritta per il percorso sincrono e nomina strumenti che QUI
    non esistono.

    `restrict_to_home` e `response_mode` (Task 3, "il ponte riceve il
    nucleo"): le due impostazioni della chat che sono TESTO di prompt e che,
    prima di questo task, il ponte non riceveva affatto (`_enqueue_chat_job`
    portava solo `history` + `system_prompt`, mentre il ramo sincrono le
    legge gia' da `impostazioni.restrict_to_home`/`.response_mode`,
    `handlers_chat.py`). `RESTRICT_PROMPT`, `COMPACT_PROMPT` e
    `MINIMAL_PROMPT` si IMPORTANO da `..claude_runner` -- sono gia' l'unica
    fonte per il ramo sincrono E per `backends/openai_compat_runner.py`
    (Task 3, Step 1: erano ricopiate li' tre volte prima di questo task);
    una quarta copia qui sarebbe la "funzione doppia" vietata da
    CLAUDE.md:70-72. Applicati fra `system_prompt` e la guida, come
    `claude_runner.py::ClaudeRunner.chat` fa fra i suoi blocchi stabili e il
    breakpoint di cache.

    `strumenti_attivi` sceglie DUE cose insieme, non una (fix round 1,
    Critical 1 della review indipendente):

    1. **quanto di BASE viene emesso.** `BASE_IDENTITA` (chi e' HIRIS, cosa
       conosce) e' vera su entrambi i percorsi ed entra sempre.
       `BASE_REGOLE_STRUMENTI` -- «Usa SEMPRE gli strumenti per dati sulla
       casa», «chiama ricorda subito», «se hai chiamato uno strumento con
       successo l'azione e' reale» -- e' un ORDINE DI CHIAMARE UNO STRUMENTO
       che sul ponte non esiste, e sul ponte non viene emessa affatto. La
       prima stesura di questo task passava BASE intero e lo faceva smentire
       dalla guida che segue: una smentita di testo non e' un meccanismo, e
       il caso peggiore -- «preso nota» senza aver salvato -- e' il bug
       misurato in produzione da cui `ricorda` e' nato. Con
       `strumenti_attivi=True` i due pezzi tornano contigui e il blocco e'
       byte per byte `BASE_SYSTEM_PROMPT`, come nel ramo sincrono;
    2. **quale delle due guide entra.**

    Nella fetta A era sempre False (nessun chiamante di produzione lo
    passava). La fetta "il ponte riceve gli strumenti" (parita' B, Task 3) ha
    raccolto il ramo True cambiando UN ARGOMENTO, senza riscrivere il prompt
    una terza volta: `agent/runner.py::_reason_chat` lo passa, e il valore
    viene dalla sonda `sonda_strumenti` -- lo stesso booleano che decide
    l'argv, due righe piu' sotto. Il default resta False perche' False e' il
    ramo di DEGRADO, e un degrado deve essere cio' che si ottiene quando non
    si sa: un default True prometterebbe strumenti a chi non li ha chiesti."""
    # Con gli strumenti attivi le due meta' tornano adiacenti e il blocco e'
    # esattamente `BASE_SYSTEM_PROMPT`: nessuna terza variante da mantenere.
    base = BASE_IDENTITA + BASE_REGOLE_STRUMENTI if strumenti_attivi else BASE_IDENTITA
    system_parts = [base.strip()]
    if system_prompt:
        system_parts.append(system_prompt.strip())
    # I modificatori di comportamento -- stesso ordine e stesse costanti
    # IMPORTATE del ramo sincrono (claude_runner.py::ClaudeRunner.chat,
    # `if restrict_to_home: ... if response_mode == "compact": ...`).
    if restrict_to_home:
        system_parts.append(RESTRICT_PROMPT)
    if response_mode == "compact":
        system_parts.append(COMPACT_PROMPT)
    elif response_mode == "minimal":
        system_parts.append(MINIMAL_PROMPT)
    guida = _GUIDA_CON_STRUMENTI if strumenti_attivi else _GUIDA_SENZA_STRUMENTI
    contesto = (contesto or "").strip()
    system_parts.append(
        guida + "\n" + (_CONTESTO_PRESENTE if contesto else _CONTESTO_ASSENTE))
    if contesto:
        system_parts.append(contesto)
    system = "\n\n".join(system_parts)

    lines = ["Conversazione finora:"]
    for msg in history or []:
        role = (msg or {}).get("role", "user")
        content = (msg or {}).get("content", "")
        speaker = "Assistente" if role == "assistant" else "Utente"
        lines.append(f"{speaker}: {content}")
    lines.append("")
    lines.append(_CHAT_INSTRUCTION)
    user = "\n".join(lines)
    return system, user
