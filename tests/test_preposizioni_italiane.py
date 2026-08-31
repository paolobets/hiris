"""Il cancello sulle preposizioni: nessuna giuntura italiana in un nome nuovo.

**Perche' esiste.** La misura ordine-e-preposizioni del 31/08 ha trovato 25
nomi difettosi che nessun rilancio di `scripts/rinomina.py` avrebbe mai
segnalato: sono parole GIA' inglesi tenute insieme da una preposizione
italiana (`_prompt_di_system`, `area_del_device`, `da_anchor`, `a_ts`) o
messe in ordine italiano (`bands_all`, `reason_downgrade`). Lo strumento non
li vede perche' non c'e' niente da tradurre.

Delle due meta' della classe **una sola e' meccanizzabile**, e questo file e'
quella meta': una preposizione, un articolo o una congiunzione italiana
dentro un identificatore e' un fatto di forma, e un test la puo' vietare per
sempre -- comprese le 11.266 righe dei sottosistemi non ancora convertiti.
L'altra meta' -- l'ordine invertito -- non lo e': richiede di sapere quale
pezzo e' la TESTA del nome, e nessuna macchina lo sa. Il suo unico controllo
e' la lettura, ed e' scritto in `docs/GLOSSARIO.md` («L'ordine delle parole
non e' meccanizzabile: nessuna macchina lo difende»).

## Perche' un'istantanea di tutto il repo, e non un elenco di percorsi convertiti

La forma ovvia sarebbe stata: «il cancello guarda i sottosistemi gia'
convertiti», con l'elenco dei percorsi scritto qui. **E' la forma sbagliata,
e la ragione e' gia' scritta nello strumento**: un elenco che va aggiornato a
mano «sarebbe silenziosamente incompleta per costruzione»
(`scripts/rinomina.py::_righe_di_percorso_e_parola_chiave`, sui percorsi di
import). Il giorno in cui `agent/` venisse convertito e nessuno si ricordasse
di aggiungerlo, il cancello smetterebbe di proteggerlo **senza dire niente**
-- ed e' esattamente il difetto che questa fetta esiste per curare, applicato
al cancello stesso.

La forma che regge e' l'opposta: **il cancello guarda TUTTO il Python del
progetto fin dal primo giorno**, e porta l'istantanea dei casi noti -- ogni
identificatore che oggi contiene una giuntura italiana, convertito o no.
Non c'e' nessun perimetro da ricordarsi di allargare, perche' non c'e'
nessun perimetro.

Il confronto e' **un'uguaglianza esatta nelle due direzioni**, la stessa
disciplina di `_SORVEGLIATI` in `test_rinomina_applica.py`:

- un nome NUOVO con una giuntura italiana non e' nell'istantanea -> rosso,
  ovunque nasca, anche in un sottosistema che nessuno ha ancora aperto;
- un nome dell'istantanea che SPARISCE (perche' il suo sottosistema e' stato
  convertito) rompe l'uguaglianza -> rosso, e chi converte toglie la riga.
  L'istantanea e' quindi **un debito che cala**, non un permesso che resta.

La differenza che conta: un elenco di PERCORSI dimenticato tace; un'istantanea
di CASI dimenticata grida.

## Le tre regole, e perche' non sono una sola

**1. Le forme piane** (`_PIANE`): preposizioni proprie, articolate e
IMPROPRIE, articoli, congiunzioni e la **negazione**. Si segnalano ovunque
compaiano come pezzo.

Che ci siano anche articoli, congiunzioni e `non`, e non solo preposizioni,
non e' zelo: e' il conto di **due omissioni pagate**. La prima lista ometteva
`a` nuda e le elisioni, e furono trovate LEGGENDO -- `a_ts`, `a_iso`. La
seconda -- questa -- ometteva `non`, e con lei cinque nomi in un ambito
dichiarato chiuso (`casa/anagrafe.py`: `_ID_AREA_NON_LOADED`,
`_ID_DEVICE_NON_LOADED`, `_ID_FLOOR_NON_LOADED`, `device_non_loaded`,
`area_non_loaded`), piu' `senza` (28 nomi), `che` (7), `come` (4), `oltre`
(2), `durante` (1). Anche loro trovate leggendo, non dalla lista.

**La lezione non e' «serviva una lista migliore»**: e' che una lista scritta
a mano e' silenziosamente incompleta per costruzione -- la stessa frase che
lo strumento dice di se' -- e che qui l'unico rimedio possibile e' tenerla
sulla CLASSE GRAMMATICALE CHIUSA (tutte le preposizioni, tutti gli articoli,
le congiunzioni, la negazione) invece che sui casi incontrati. Le forme con
zero occorrenze oggi (`tranne`, `mediante`, `nonostante`, ...) sono dentro
apposta: costano nulla e chiudono la lista invece di aspettare la terza volta.

**Cio' che resta fuori, e non e' una dimenticanza**: `quando`, `dove`,
`perche`, `secondo`, `lungo`, `circa`, `fino`. Introducono una frase o portano
un senso proprio, e negli identificatori del progetto compaiono come PAROLE,
non come giunture -- `quando_ts` e' una colonna del database, `secondo_giro`
e' un ordinale. Segnalarle vorrebbe dire chiamare difetto un nome che dice
quello che deve dire.

**2. Le elisioni** (`_ELISIONI`: `dell`, `nell`, `all`, `sull`, `coll`,
`dall`, `l`) valgono **solo se il pezzo successivo comincia per vocale**.
Non e' un'attenuazione: e' cosa vuol dire elidere. `dell'utente` esiste,
`dell'bands` non esiste. Senza questa condizione `all` -- che in inglese e'
una parola comunissima -- avrebbe segnalato `all_bands`, `all_states`,
`get_all`, `show_all`, `close_all_stores`, cioe' cinque nomi inglesi
corretti, di cui uno (`all_bands`) e' la CORREZIONE che la misura stessa
prescrive. Con la condizione ne segnala zero, e continua a segnalare
`dall_area`, `nell_argv`, `_ARCHIVIO_DELL_UTENTE`, `l_altro_ieri`.

**3. `a` vale solo se NON e' l'ultimo pezzo** -- e questa regola ha due
FALSI NEGATIVI dichiarati, perche' la frase che la giustificava era piu'
larga del vero.

Diceva: «`a` in coda e' SEMPRE un'etichetta di enumerazione». **E' falso, ed
e' stato misurato**: su otto `a` in coda, sei lo sono (`call_a`, `text_a`,
`tools_a`, ...) e **due sono la preposizione vera** -- `aggiungi_etichetta_a`
(`proxy/ha_client.py:632`, chiamata da `azione/costruzione/officina.py:591`:
«aggiungi etichetta A qualcosa») e `_caricato_a` (`azione/registro.py:113`).
La regola RESTA, perche' vietare `a` in coda arrossirebbe su sei nomi
corretti per prenderne due; ma la ragione giusta e' un rapporto misurato
(6 a 2), non una legge senza eccezioni. I due sono difetti che questo cancello
**non vede**, e li trova solo la lettura -- come l'ordine invertito.

`a` che precede qualcosa e' invece la preposizione (`a_ts`, `a_iso`,
`_chiamate_a_salva`, `CLIMA_A_21`): una preposizione unisce cio' che la SEGUE.

## Le QUATTRO forme escluse, ognuna con il suo conto

Il metro e' sempre lo stesso, e va applicato a tutte o non e' un metro:
**quanti difetti veri cattura questa forma, contro quanti nomi inglesi
corretti farebbe arrossire.**

- **`per` -- FUORI.** Difetti veri: 0. Nomi corretti colpiti: 12+
  (`AREAS_PER_ROUND`, `MAX_POINTS_PER_ANSWER`, `ROUNDS_PER_EXCHANGE_KEY`,
  `STORE_KEY_PER_TYPE`, `_RESOURCE_PER_TOOL`, `_count_per_domain`,
  `_per_domain`, `_per_type`, `_per_provider`, `answers_per_command`,
  `areas_per_floor`, `area_per_entity`).
- **`in` -- FUORI.** Difetti veri: 0. Nomi corretti colpiti: 7+
  (`_in_timezone`, `_models_in_use`, `_MAX_DEVICE_NAMES_IN_LINE`, `in_domain`,
  `in_baseline`, `entities_in_balance`, `breaks_in_ha_version`).
- **`i` -- FUORI.** Difetti veri: 0. Nomi corretti colpiti: 12, e **dieci sono
  letteralmente `X.index(...)`** (`i_alias`, `i_base`, `i_cerca`, `i_compact`,
  `i_contesto`, `i_guida`, `i_letta_vuota`, `i_persona`, `i_restrict`,
  `i_ricorda`, `i_scarti`), piu' `_solo_i_nostri`/`interroga_i_registri`/
  `leggi_i_file`, dove l'articolo c'e' ma il nome e' gia' italiano per intero e
  altre giunture lo prendono comunque.
- **`o` -- FUORI.** Difetti veri: 0. Nomi corretti colpiti: 3, e sono una
  FAMIGLIA APERTA -- `O_CREAT`/`O_TRUNC`/`O_WRONLY` sono costanti di `os`, e le
  altre dieci (`O_RDONLY`, `O_APPEND`, `O_EXCL`, ...) arrossirebbero il giorno
  in cui qualcuno le usasse.

**`i` e `o` sono usciti il 31/08, dopo la review**, e non perche' fossero
fastidiosi: perche' misurati col metro gia' applicato a `in` e `per` davano lo
stesso verdetto, e **un criterio applicato a tre parole e non alla quarta non
e' un criterio**. Il costo concreto che `i` avrebbe avuto: un futuro
`i_start`/`i_end` -- inglese perfettamente corretto -- avrebbe fatto arrossire
il cancello.

**`e` invece RESTA, e la differenza e' misurata, non stilistica**: `e` ha
catturato un difetto vero (`state_e_cost`, uno dei 25 della misura) e non
colpisce nessun nome inglese; `i` e `o` non ne catturano nessuno. Stessa forma
-- una lettera sola -- conti opposti.

`in_use` e `solo_in_sospeso` portano lo stesso pezzo e uno solo dei due e' un
difetto: la forma da sola non lo dice. **Un cancello che arrossisce su un
nome inglese corretto non viene corretto, viene indebolito** -- e allora non
protegge piu' nemmeno cio' che protegge oggi. Il costo di queste quattro
esclusioni e' dichiarato: una giuntura `in`/`per`/`i`/`o` in un nome
altrimenti inglese la trova solo la lettura, come per l'ordine invertito.

## Cosa questo cancello NON copre, e perche'

- **I nomi delle funzioni `test_*`**: sono frasi italiane in tutti e 172 i
  file, per decisione, e il rapporto del Task 9 lo aveva gia' registrato come
  domanda aperta. Segnalarli sarebbe oltre 1.300 righe di rumore su un fatto
  gia' deciso. Il criterio e' meccanico (il nome comincia per `test_`, anche
  dopo i trattini bassi), non un elenco di eccezioni.
- **Le maiuscole interne**: si spezza sui soli trattini bassi, mai su
  camelCase. `AsyncOpenAI` finisce in `Async`+`Open`+`AI` con lo stesso
  criterio di `spezza()`, e quell'`AI` e' la preposizione articolata `ai`: un
  falso positivo puro. In Python i composti si scrivono col trattino basso;
  una classe in maiuscole e' un'unita' lessicale sola. Il costo: `_CacheConNomi`
  e `ArchivioConCorsaSuPrendi` (finte di test, italiane) non si vedono.
- **`hiris/app/static/`**: e' JavaScript, e questo cancello legge i token NAME
  di `tokenize`. Riconoscere un identificatore JS senza un parser vorrebbe
  dire una regex sul testo, che non distingue un nome da una stringa -- la
  classe di misura sbagliata che la specifica della fetta mette in cima alle
  proprie ragioni. Residuo dichiarato, non dimenticato.
"""
import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Preposizioni semplici e articolate, articoli e congiunzioni che NON sono
# anche parole inglesi. `in` e `per` sono esclusi di proposito: vedi il
# docstring del modulo, con la misura degli usi inglesi veri.
_PIANE = frozenset([
    # preposizioni proprie
    "di", "da", "con", "su", "tra", "fra",
    # preposizioni articolate
    "del", "dello", "della", "dei", "degli", "delle",
    "al", "allo", "alla", "ai", "agli", "alle",
    "dal", "dallo", "dalla", "dai", "dagli", "dalle",
    "nel", "nello", "nella", "nei", "negli", "nelle",
    "col", "collo", "colla", "coi", "cogli", "colle",
    "sul", "sullo", "sulla", "sui", "sugli", "sulle",
    "pel", "pei",
    # preposizioni improprie e locuzioni
    "sopra", "sotto", "dopo", "prima", "senza", "oltre", "durante", "dentro",
    "fuori", "verso", "contro", "tranne", "salvo", "presso", "mediante",
    "tramite", "entro", "dietro", "davanti", "attraverso", "nonostante", "malgrado",
    # articoli
    "il", "lo", "la", "gli", "le", "un", "uno", "una",
    # congiunzioni e negazione
    "e", "ed", "che", "come", "non",
])

# Elisioni: valgono SOLO davanti a vocale, perche' e' cio' che l'elisione e'.
_ELISIONI = frozenset(["dell", "all", "nell", "sull", "coll", "dall", "l"])
_VOCALI = frozenset("aeiou")


def giunture(nome: str) -> list[str]:
    """I pezzi di `nome` che sono una giuntura italiana. Lista vuota = pulito."""
    pezzi = [p for p in nome.lower().split("_") if p]
    if len(pezzi) < 2:
        return []
    fuori = []
    for i, p in enumerate(pezzi):
        successivo = pezzi[i + 1] if i + 1 < len(pezzi) else ""
        elisa = p in _ELISIONI and successivo[:1] in _VOCALI
        preposizione_a = p == "a" and bool(successivo)
        if p in _PIANE or elisa or preposizione_a:
            fuori.append(p)
    return fuori


def _scansione() -> dict[str, str]:
    """`{nome: "file:riga" del primo sito}` su tutto il Python del progetto."""
    trovati: dict[str, str] = {}
    for base in ("hiris", "tests", "scripts"):
        for f in sorted((ROOT / base).rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            try:
                sorgente = f.read_text(encoding="utf-8")
                token = list(tokenize.generate_tokens(io.StringIO(sorgente).readline))
            except (OSError, UnicodeDecodeError, tokenize.TokenError,
                    IndentationError, SyntaxError):
                continue
            for t in token:
                if t.type != tokenize.NAME:
                    continue
                if t.string.lstrip("_").startswith("test_"):
                    continue
                if giunture(t.string):
                    trovati.setdefault(
                        t.string, f"{f.relative_to(ROOT).as_posix()}:{t.start[0]}")
    return trovati


# L'ISTANTANEA DEL DEBITO -- ogni identificatore che oggi porta una giuntura
# italiana, misurato il 31/08/2026 subito dopo la correzione dei 25 nomi.
# **Cala, non cresce.** Un nome che sparisce da qui perche' il suo
# sottosistema e' stato convertito fa fallire il test finche' non si toglie
# anche da questo elenco: e' il modo in cui la conversione si misura invece
# di dichiararsi.
#
# Dentro ci sono tre specie, e vale saperlo prima di leggerlo:
# 1. il debito italiano coerente dei sottosistemi non convertiti (`agent/`,
#    `proxy/`, `backends/`, `reasoning/`, i moduli di radice, gran parte di
#    `tests/`) -- `nomi_di_ripiego`, `_avvisi_del_ponte`, `catena_di_oggi`;
# 2. i MISTI che la misura ha tenuto fuori apposta (`_accoda_al_bridge`,
#    `_normalize_con_mappa`, `cost_da_listino`; il quarto,
#    `CEILING_IN_SOSPESO`, non compare qui perche' porta `in`, forma esclusa);
# 3. i QUATTRO falsi positivi noti -- **annotati uno per uno ACCANTO alla
#    loro voce**, in cima all'elenco, e non qui: una decisione che vive
#    lontano da cio' che decide non la legge nessuno. Erano sei: `O_CREAT`/
#    `O_TRUNC`/`O_WRONLY` sono usciti insieme alla forma `o` (vedi la sezione
#    sulle quattro forme escluse), misurata e non piu' tollerata. I quattro
#    che restano costerebbero, per uscire, `a`, `col` e `non`: tre forme che
#    catturano difetti veri.
_NOTE_ITALIANE = frozenset({
    # -- I QUATTRO FALSI POSITIVI, annotati dove si leggono --------------------
    # NON sono debito da far calare: sono nomi corretti che la regola non sa
    # distinguere. Chi li trova qui non deve «correggerli».
    "a_trunc",              # `chat_store.py`: quella `a` e' il messaggio
                            # dell'assistente, accanto a `u_trunc` che e' quello
                            # dell'utente
    "col_offset", "end_col_offset",   # attributi di `tokenize`: quel `col` sta
                            # per «column», non e' `con` + articolo
    "_non_negative_integer",  # `non-negative` E' inglese: il prefisso `non-`
                            # esiste in inglese davanti a un aggettivo. E' l'unico
                            # `non` inglese misurato oggi su 24 -- vedi il
                            # docstring per il conto che ha deciso di tenerlo
    # -- il resto: debito italiano vero, e cala --------------------------------
    "ACCENDI_LE_ABAT_JOUR", "ALIAS_DEL_PIANO", "ANNUNCIA_IL_CLIMA_A_21",
    "ANNUNCIA_IL_SALOTTO_SPENTO", "ANNUNCIA_LE_ABAT_JOUR_ACCESE",
    "AZIONE_METTI_IL_PIANO_IN_TESTA", "AZIONE_TOGLI_IL_PIANO", "CAMERA_A_17_5", "CLIMA_A_19",
    "CLIMA_A_21", "CREDENZIALI_DEL_PROPRIETARIO", "HA_RIPORTA_IL_SALOTTO_SPENTO",
    "HA_RIPORTA_LA_CAMERA_A_19_5", "METTI_A_21", "METTI_LA_CAMERA_A_19_5", "SCADENZA_NEI_TEST",
    "SENTINELLE_DEL_PONTE", "SPEGNI_IL_SALOTTO", "TUTTA_LA_CUCINA", "VARIABILE_TOKEN_DEL_PIANO",
    "_ARCHIVIO_DELL_UTENTE", "_BLOCCHI_A_TUTTA_LARGHEZZA", "_CASA_CON_ETICHETTA",
    "_CHIAVI_NOMINATE_DAL_PROMPT", "_CLASSI_SENZA_REGOLA_PER_SCELTA",
    "_DIREZIONE_DA_TRANSLATION_KEY", "_DOMINI_DI_RECAPITO", "_DOMINI_NON_PIATTAFORMA",
    "_FALSITA_IN_ENTRAMBE_LE_VOCI", "_FUNZIONI_CHE_LEGGONO_LA_CREDENZIALE",
    "_GUIDA_CON_STRUMENTI", "_GUIDA_SENZA_STRUMENTI", "_LETTURE_VIVE_DELLA_CREDENZIALE",
    "_MARK_DOPO_VAULT", "_NOMI_DEL_CATALOGO", "_NON_SLUG", "_SENZA_RECAPITO",
    "_accoda_al_bridge", "_accoda_e_prendi", "_alias_di_oggi", "_annuncia_fra_poco",
    "_app_col_ponte", "_app_come_in_produzione", "_archivio_con_una_casa",
    "_avvia_la_semina_della_catena", "_avvisi_del_ponte", "_blocco_catena_dallo_startup",
    "_blocco_giorni_dallo_startup", "_blocco_risponde_dallo_startup",
    "_blocco_semina_catena_dallo_startup", "_blocco_semina_dallo_startup", "_cambiati_da",
    "_casa_con_aree", "_casa_con_sensore", "_casa_con_un_dispositivo", "_casa_sala_da_pranzo",
    "_casa_senza_nomi", "_catena_di_oggi", "_che_solleva", "_chiamate_a_salva",
    "_chiavi_lette_da_run_sh", "_chiavi_prodotte_dalla_porta", "_classi_disegnate_dalla_pagina",
    "_codice_di", "_codice_senza_commenti", "_con_registro", "_con_strumenti_e_processo",
    "_cosa_non_esiste", "_da_consegnare", "_da_quando", "_da_rileggere", "_da_salvare",
    "_da_salvare_p", "_dentro_un_loop", "_e_carattere_di_parola", "_e_chiamata_a_primitiva_rest",
    "_e_chiamata_a_rete", "_e_risorsa_della_card", "_e_self_ha", "_eco_della_cli",
    "_fogli_della_pagina_config", "_fra_poco", "_fuso_da_archivio_casa",
    "_get_entities_on_come_lo_strumento", "_giorni_da_ambiente", "_governa_lavoratore_del_ponte",
    "_guasto_con_404", "_i_due_testi_di_chi_puo_agire", "_init_col_server_collegato",
    "_istante_da_ha", "_le_due_guide", "_letture_dallo_startup", "_membri_di",
    "_mock_che_solleva", "_mock_risposta_con_stato", "_modello_di", "_nomi_di_campo",
    "_normalize_con_mappa", "_ordered_backends_con_nome", "_porta_di_prova",
    "_posizionali_dopo_self", "_presente_nel_js", "_prompt_del_ponte", "_replace_che_esplode",
    "_righe_di_percorso_e_parola_chiave", "_ripiego_sala_da_pranzo",
    "_risposta_openai_senza_tool", "_rompe_dalla_lettura", "_scarti_e_alias", "_seme_da",
    "_semina_casa_con_comportamento", "_semina_gli_archivi", "_senza_commenti",
    "_senza_commenti_html", "_senza_commenti_js", "_senza_conclusione", "_senza_docstring",
    "_sonda_con", "_sostituzioni_di_identificatori", "_specchio_del_termostato", "_su_disco",
    "_testi_che_legge_l_utente", "_tools_list_come_la_rotta", "_tutte_le_descrizioni", "a_iso",
    "a_ts", "aggiornata_il", "ago_senza_slash", "alias_di_oggi", "annuncio_di_un_altra",
    "app_con", "app_senza", "ascoltatori_durante_la_chiamata", "avvolte_da_rete", "body_con",
    "body_senza", "casa_con_orfana", "casa_senza", "catena_di_oggi",
    "chiamata_dello_schedulatore", "chiamato_con", "chiavi_che_parlano_del_ponte",
    "claude_con_elenco", "client_con", "client_senza", "cliente_su", "col_token",
    "col_token_del_piano", "come_stringa", "commenti_di", "con_free", "con_gratuiti",
    "con_registro_caduto", "corpo_ricevuto_dal_modello", "cost_da_listino", "da_anchor",
    "da_http", "da_iso", "da_quando", "da_quante", "da_risolvere", "da_run_sh", "da_salvare",
    "da_sempre", "da_strumento", "da_ts", "dai_guasti", "dal_dispositivo", "dal_js", "dall_area",
    "dall_entita", "dall_init", "dalla_sonda", "detto_da", "dopo_nuovo", "dopo_riavvio",
    "e_alias", "e_contenitore", "e_def", "e_intestazione", "entita_del_dispositivo",
    "estrai_dal_bersaglio", "famiglia_da_codice", "forme_del_token", "fra_parentesi",
    "giro_di_confronto_albero", "grave_piu_un_taciuto", "guarda_condizioni_di_sistema",
    "i_non_letta", "ids_da_leggere", "il_file_non_porta_i_giorni", "il_piano_puo_rispondere",
    "in_fuori", "kwargs_con", "kwargs_senza", "l_altro_ieri", "legami_a_self_ha",
    "mezzanotte_e_mezza_a_roma", "mezzanotte_e_mezza_roma", "modello_del_turno", "modello_di",
    "motivo_token_non_valido", "nei_preset", "nei_test", "nel_prompt", "nell_argv",
    "nomi_di_ripiego", "non_c_e", "non_chiesto", "non_disponibili", "non_esiste", "non_letti",
    "non_letto", "non_validi", "non_viste", "notte_30_oltre_confine", "parole_di_scadenza",
    "piano_ha_il_token", "poco_dopo", "ponte_con_configurazione_predefinita", "porta_con_canale",
    "prima_dei_guasti", "prima_riga", "prima_rivendicazione", "prima_voce", "resp_con",
    "resp_senza", "riaggrega_gli_ultimi_due_giorni", "riepilogo_non_chiesto",
    "riepilogo_non_letto", "riga_di", "righe_non_vuote", "rompe_dalla_lettura",
    "rotta_senza_archivi", "runner_con", "runner_senza", "semina_modello_del_piano",
    "senza_accenti", "senza_area", "senza_causa", "senza_id", "senza_modello",
    "senza_registro_caduto", "senza_stato_vivo", "senza_token", "specchio_al_ritorno",
    "strumenti_che_scrivono", "su_disco", "tipi_non_verificabili", "toks_dopo", "toks_prima",
    "ultimo_init_del_ponte", "uno_grave", "uno_oltre_il_tetto", "usa_e_getta",
})


def test_nessuna_giuntura_italiana_nuova_in_un_identificatore():
    """Il cancello. Uguaglianza esatta nelle due direzioni.

    Provato per mutazione: rimesso `area_del_device` al posto di `device_area`
    in `memoria/interpretazione.py` (occorrenze contate prima e dopo la
    scrittura, per non credere a una regex che non combacia), questo test va
    rosso col nome nell'elenco «mai visti prima»; ripristinato, torna verde.
    """
    trovati = _scansione()
    nuovi = sorted(set(trovati) - _NOTE_ITALIANE)
    spariti = sorted(_NOTE_ITALIANE - set(trovati))
    assert not nuovi, (
        "identificatori con una giuntura italiana mai visti prima: "
        + ", ".join(f"{n} ({trovati[n]}, giunture: {'/'.join(giunture(n))})"
                    for n in nuovi)
        + " -- una preposizione, un articolo o una congiunzione italiana in un "
          "nome nuovo e' il difetto che questo cancello vieta. Se il nome e' "
          "interamente italiano e vive in un sottosistema non ancora "
          "convertito, aggiungilo a `_NOTE_ITALIANE` con la sua ragione; "
          "altrimenti rinominalo.")
    assert not spariti, (
        "nomi nell'istantanea che il codice non ha piu': " + ", ".join(spariti)
        + " -- sono stati corretti (bene): toglili da `_NOTE_ITALIANE`. "
          "L'istantanea e' un debito che cala, e un'eccezione dimenticata "
          "sarebbe silenziosa quanto il difetto che copriva.")


def test_la_regola_vede_i_nomi_che_la_misura_ha_trovato():
    """I casi veri della misura, quelli che nessun dry-run avrebbe mostrato."""
    for nome in ("_prompt_di_system", "_note_del_downgrade", "area_del_device",
                 "behavior_loaded_il", "_DAL_NAME", "state_e_cost", "da_anchor",
                 "da_iso", "a_iso", "da_ts", "a_ts", "_tools_di_chat_claude"):
        assert giunture(nome), f"{nome} doveva essere segnalato"


def test_la_regola_non_tocca_i_nomi_inglesi_corretti():
    """Le correzioni della misura, e gli inglesi che `all`/`a` mettevano a
    rischio: se questo test arrossisse, il cancello starebbe vietando proprio
    cio' che la misura prescrive."""
    for nome in ("_system_prompt", "_downgrade_note", "device_area",
                 "behavior_loaded_at", "_PROVIDER_BY_SUFFIX", "cost_state_and_value",
                 "from_anchor", "from_iso", "to_iso", "from_ts", "to_ts",
                 "all_bands", "all_states", "get_all", "show_all", "close_all_stores",
                 "call_a", "text_a", "tools_a", "_claude_chat_tools", "downgrade_reason",
                 "READABLE_STATE", "EXECUTIONS_RETENTION_S", "ha_target", "pool_lines"):
        assert not giunture(nome), f"{nome} NON doveva essere segnalato"


def test_l_elisione_vale_solo_davanti_a_vocale():
    """La regola che rende `all` utilizzabile invece che ingestibile."""
    assert giunture("all_inizio") == ["all"]
    assert giunture("dell_utente") == ["dell"]
    assert giunture("nell_argv") == ["nell"]
    assert giunture("all_bands") == []
    assert giunture("close_all_stores") == []


def test_a_in_coda_e_un_etichetta_non_una_preposizione():
    assert giunture("a_ts") == ["a"]
    assert giunture("_chiamate_a_salva") == ["a"]
    assert giunture("text_a") == []


def test_un_nome_di_un_pezzo_solo_non_e_mai_una_giuntura():
    """`da`, `a`, `e` come identificatori interi sono parametri veri
    (`ObservationsStore.record(da=..., a=...)`, che sono anche colonne del
    database): il difetto e' la GIUNTURA fra due pezzi, non la parola."""
    for nome in ("da", "a", "e", "i", "del"):
        assert giunture(nome) == []
