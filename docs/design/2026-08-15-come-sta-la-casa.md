# Come sta la casa — lo stato entra nel nucleo

**Data:** 2026-08-15 · **Ramo:** `2.0` · **Versione di partenza:** 3.3.0 (`15ae32e`)
**Nasce da:** una risposta vera di HIRIS sull'impianto del proprietario.

---

## 0. Il fatto, e le misure che hanno deciso il disegno

Alla domanda *«lo stato della casa in generale, luci accese, temperature»* HIRIS ha risposto:

> «basato su una lettura appena fatta di Cantina, Lavanderia, Bagnetto, Cucina, Esterno, Sala da
> pranzo, Soggiorno, Bagno e Camera da letto (**ho esaurito il limite di chiamate per questo turno**
> prima di controllare Cameretta Viola, Disimpegno, Studio e "Senza area")»

Il limite è `api/handlers_mcp.MAX_GIRI_STRUMENTI = 10`: il freno che sostituisce un `--max-turns`
che la CLI dell'abbonamento non ha. HIRIS ha fatto **la cosa giusta** — ha dichiarato cosa non
aveva guardato invece di far passare per completo un resoconto parziale.

**Ma la risposta era incompleta in modo che conta.** Le sole due luci stabilmente accese della casa
— `light.sala_da_pranzo_sala_da_pranzo` e `light.telecamera_cancellino_...` — stanno entrambe in
**«Senza area»**, una delle quattro che il tetto ha lasciato fuori. Alla domanda «quali luci sono
accese» il proprietario ha ricevuto «nessuna», con la lacuna dichiarata ma la risposta sbagliata.

### Le quattro misure

Prese sull'impianto vero, non stimate.

**(1) Il nucleo ha la struttura e non lo stato.** `costruisci_nucleo` compone piani, 16 aree e
conteggi per dominio — 5.584 caratteri, ~1.400 token, in **ogni** turno di chat (sincrono e ponte).
Nessuno stato. HIRIS sa com'è fatta la casa e non come sta.

**(2) `guarda` ha lo stato, una cosa alla volta.** È il solo strumento che porta gli stati, e il
suo contratto dice «UNA cosa sola» tre volte.

**(3) Tutta la casa via `guarda` costa 141.283 caratteri, ~35.320 token.** Sedici chiamate, e due
«aree» fanno il 64%: **Senza area** (386 entità, 49.252 car.) e **Telecamere** (276, 40.943).
Rendere `guarda` plurale avrebbe **sostituito un tetto con un altro**: da dieci chiamate a
trentacinquemila token, a ogni domanda sulla casa.

**(4) Lo stesso stato, come RIEPILOGO, costa 609 caratteri: ~152 token.** Duecentotrenta volte
meno. E la riga che ne esce — `Senza area: 2 light acc.` — è esattamente ciò che mancava alla
risposta del punto 0.

**Il buco non è una fonte che manca: è che il riepilogo non esiste.** I dati sono già tutti in
`entity_cache`, che `costruisci_nucleo` ha già in mano e usa solo per contare.

---

## 1. Il principio

**Il nucleo dice com'è fatta la casa. Da questa fetta dice anche come sta.**

Non un oggetto nuovo, non uno strumento nuovo, non una seconda porta da tenere allineata: **una
riga in più per area**, dentro la struttura che esiste già, composta dalla funzione che è già
condivisa fra la rotta di verifica e i due percorsi di chat.

E vale per il Brain quando tornerà: un Brain che vuole sapere come sta la casa legge il nucleo,
che è già la cosa che tutti leggono. Nessun secondo meccanismo.

---

## 2. La riga di stato

Per ogni area, accanto alla riga dei conteggi che c'è già, una riga con **solo ciò che ha qualcosa
da dire**:

```
Terra:
  - Sala da pranzo: 3 sensori binari, 7 button, 1 termostato, 7 luci, 10 sensori, 11 interruttori
    adesso: 7 interruttori accesi · 26,7 °C (heat) · 5 non disponibili
```

### 2.1 Tre regole, e ognuna nasce da una misura

**(a) Un'area senza niente da dire non produce nessuna riga.** Su questo impianto due aree su
sedici non ne avrebbero (Bagnetto, e altre a seconda dell'ora). È la stessa regola già scelta per
la fetta «salute di HA»: zero righe su casa quieta. Un riepilogo che dice sempre qualcosa è un
riepilogo che si smette di leggere — lo stesso difetto che la pagina Modelli è appena servita a
togliere.

**(b) «Acceso» NON è `state == "on"`.** Misurato: 132 entità sono `on`, ma **99 sono `switch`, 18
sono `automation` e solo 3 sono luci**. Un'automazione `on` è **abilitata**, non accesa; un
`button` è `unknown` finché non lo premi. Entrano solo i domini in cui «acceso» significa qualcosa
in casa:

> `light`, `switch`, `fan`, `cover`, `media_player`, `valve`

e si contano **per dominio**, con il nome del dominio: «2 luci accese, 54 interruttori accesi», mai
«56 cose accese».

**(c) Il clima porta i GRADI, non solo la modalità.** `state` di un `climate` è la modalità
(`heat`); la temperatura è un attributo. **Non serve estendere niente**:
`proxy/entity_cache._DOMAIN_ATTRS["climate"]` conserva già `current_temperature`, `temperature`,
`hvac_mode`, `hvac_action` e `preset_mode` — e la prova che arrivano fino al modello è nella
risposta del §0, dove HIRIS scrive «Bagno 28,1 °C».

### 2.2 Cosa entra nella riga, in ordine

1. **acceso**, per dominio e solo per i sei domini di (b);
2. **clima**, `current_temperature` + modalità fra parentesi;
3. **non disponibili**, come conteggio.

`unknown` **non entra**: sono 75, e 57 di quelle misurate nella fetta «salute di HA» erano `button`
— cioè cose che sono `unknown` per costruzione. Contarle sarebbe il generatore di allarmi che
quella fetta aveva già deciso di non costruire.

---

## 3. Dove si scrive, e cosa NON si tocca

**Si tocca `casa/nucleo.componi()`** (`:546`), dove i conteggi per area si compongono già e dove
`stato` arriva **già come parametro** insieme a `stato_affidabile` (`:549`) — cioè il posto ha
tutto quello che serve e oggi lo usa solo per contare. `api/handlers_casa.costruisci_nucleo` le
passa già lo specchio vivo (`entity_cache`), e resta invariata: la condivisione fra
`/api/nucleo` e i due percorsi di chat è esattamente ciò che questa fetta non deve rompere.

**Non si tocca:**

- **`guarda`** — resta singolare e dettagliato, che è il suo mestiere. Il dettaglio di una stanza è
  una domanda diversa da «come sta la casa», e continua a costare una chiamata.
- **`MAX_GIRI_STRUMENTI`** — resta 10. Non si alza un freno: si toglie il motivo per cui mordeva.
  La domanda comune non chiama più strumenti; dieci giri restano abbondanti per il resto.
- **`_DOMAIN_ATTRS`** — conserva già tutto il necessario.
- **`cerca`, `/api/casa`, `/api/entities`** — nessuno di questi cambia forma.

**Nessun dato viene duplicato:** la riga non ripete i conteggi (che stanno nella riga sopra) né gli
identificatori (che stanno in `guarda`). Dice una cosa che oggi non dice nessuno.

---

## 4. Quando lo stato non si può leggere

`costruisci_nucleo` distingue già `stato_affidabile` — vero solo quando l'archivio c'è **e**
l'inventario vivo è pronto. Quando è falso, **la riga non si scrive affatto e il nucleo lo dice
una volta**, a livello di casa e non per area:

> `adesso: non ho potuto leggere lo stato della casa.`

Un riepilogo di stato composto su un inventario non pronto direbbe «niente acceso» su una casa
accesa — cioè la forma peggiore di silenzio: quella che sembra una risposta.

---

## 5. Le prove

Ogni prova deve poter **produrre** il difetto che dice di impedire, e si convalida per mutazione.

1. **Un'area con una luce accesa la nomina, col dominio.** *Mutazione:* contare tutti i domini
   insieme → «1 cosa accesa» invece di «1 luce accesa».
2. **Un'automazione `on` NON compare fra gli accesi.** È il caso da 18 unità sull'impianto vero.
   *Mutazione:* togliere il filtro dei domini — la prova cade, e cadrebbe anche in produzione con
   un +18 sul conteggio.
3. **Un `button` `unknown` non compare da nessuna parte.**
4. **Un'area senza niente da dire non produce righe.** *Mutazione:* emettere sempre la riga.
5. **Il clima porta i gradi e la modalità.** *Mutazione:* usare `state` da solo → esce `heat`
   senza numero.
6. **Con `stato_affidabile` falso non si scrive nessuna riga di stato**, e si dichiara una volta
   sola. *Mutazione:* comporre lo stesso → una casa accesa viene descritta come spenta.
7. **Il nucleo resta piccolo:** sull'anagrafe vera dell'impianto il blocco di stato sta **sotto i
   1.000 caratteri**. *Mutazione:* mettere gli identificatori invece dei conteggi → si sfonda.
8. **La riga dei conteggi non cambia**, byte per byte, su una casa il cui stato non si legge: la
   struttura e lo stato sono due frasi, e la seconda non deve poter alterare la prima.

**Cancelli:** suite py e js verdi in foreground, censimento a 0 opzioni non lette.

---

## 6. Cosa NON entra

1. **`guarda` plurale.** Misurato: 35.320 token per la casa intera. Sostituirebbe un tetto con un
   altro. Se un giorno servisse il dettaglio di *poche* aree in un colpo, sarà una fetta sua e
   nascerà da una domanda vera, non da questa.
2. **Alzare `MAX_GIRI_STRUMENTI`.** Curerebbe il sintomo e lascerebbe la casa intera a costare
   dieci giri.
3. **Le entità `unknown` nel riepilogo.** Vedi §2.2.
4. **Una riga di stato per piano o per casa** («12 luci accese in tutto»). È un secondo livello di
   aggregazione che nessuna domanda ha chiesto, e il modello sa sommare.
5. **La salute di Home Assistant** (riparazioni, integrazioni cadute). È la fetta già brainstormata
   e resta sua: qui si dice cosa fa la casa, non se HA sta bene.

---

## 7. Il metro della fetta

Sull'impianto vero, dopo il rilascio: la stessa domanda del §0 — *«lo stato della casa in generale,
luci accese, temperature»* — deve ottenere una risposta **completa**, che nomini le **due luci
accese in «Senza area»**, e **senza che HIRIS dichiari di aver esaurito il limite di chiamate**.

È lo stesso metro della domanda che ha fatto nascere la fetta, ed è il solo che conti.
