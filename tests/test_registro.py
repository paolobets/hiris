"""Il registro dei doppioni e' la lista di lavoro: si legge, non si ricopia.

Una voce si chiude solo quando la copia e' cancellata (R20). Queste prove
tengono il registro LEGGIBILE da un programma: se il lettore si rompe, ogni
cancello che gli chiede le voci aperte resterebbe verde guardando il vuoto.

Mutazione ESEGUITA: duplicata la riga `A-01` nel capitolo A -- rossa
(`id ripetuti: ['A-01']`).
Mutazione ESEGUITA: in `read_entries` riconosciuti solo i capitoli A-G --
rossa (capitoli mancanti: M, S, T, X).
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import registro

REGISTER = Path(__file__).resolve().parents[1] / "docs" / "design" / (
    "2026-10-01-registro-dei-doppioni.md")
#: I capitoli del registro. Scritti UNA volta: e' il fatto (le undici lettere
#: della legenda del documento), non la copia di un elenco che vive altrove.
CHAPTERS = "ABCDEFGMSTX"
ID_SHAPE = re.compile(rf"^[{CHAPTERS}]-\d{{2,}}$")


def test_ogni_voce_ha_un_id_ben_formato_e_unico():
    ids = [entry.id for entry in registro.read_entries(REGISTER)]
    malformed = [i for i in ids if not ID_SHAPE.match(i)]
    assert not malformed, malformed
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    assert not repeated, f"id ripetuti: {repeated}"


def test_la_lettura_non_si_e_svuotata():
    # Il pavimento e' largo apposta: non conta le voci, dice solo che il
    # lettore sta ancora leggendo tutti gli undici capitoli.
    per_chapter = registro.count(registro.read_entries(REGISTER))
    missing = sorted(set(CHAPTERS) - set(per_chapter))
    assert not missing, f"capitoli mancanti: {missing}"
    thin = {chapter: tally for chapter, tally in per_chapter.items()
            if tally["aperte"] + tally["chiuse"] < 10}
    assert not thin, thin


def _an_open_entry(path) -> str:
    """Una voce ancora aperta, CHIESTA al registro. Scritta a mano («M-13»)
    era giusta finche' quella voce non e' stata chiusa davvero, il 02/10/2026:
    quel giorno due prove sono diventate rosse per aver fatto il loro lavoro."""
    still_open = [entry.id for entry in registro.read_entries(path)
                  if not entry.closed and entry.chapter == "M"]
    assert still_open, "nessuna voce aperta nel capitolo M: la prova non guarda niente"
    return still_open[0]


def test_una_voce_chiusa_non_e_anche_aperta(tmp_path):
    copy = tmp_path / "registro.md"
    copy.write_text(REGISTER.read_text(encoding="utf-8"), encoding="utf-8")
    chosen = _an_open_entry(copy)
    registro.close(copy, chosen, version="3.73.0", commit="abc1234",
                   note="costante cancellata")
    found = [entry for entry in registro.read_entries(copy) if entry.id == chosen]
    assert len(found) == 1
    assert found[0].closed
    assert found[0].chapter == "M"


def test_chiudere_due_volte_o_una_voce_che_non_c_e_si_rifiuta(tmp_path):
    copy = tmp_path / "registro.md"
    copy.write_text(REGISTER.read_text(encoding="utf-8"), encoding="utf-8")
    chosen = _an_open_entry(copy)
    registro.close(copy, chosen, version="3.73.0", commit="abc1234", note="x")
    with pytest.raises(SystemExit, match=chosen):
        registro.close(copy, chosen, version="3.73.0", commit="abc1234", note="x")
    with pytest.raises(SystemExit, match="Z-99"):
        registro.close(copy, "Z-99", version="3.73.0", commit="abc1234", note="x")


def test_i_verdetti_si_contano_solo_sulle_voci_aperte_dei_doppioni(tmp_path):
    """Mutazione ESEGUITA: tolto `entry.closed or` dal filtro di `verdicts` --
    rossa (la voce chiusa `A-02` entra nel conto con le sue colonne di
    chiusura: `'3.73.0': 1` fra gli stati, `'abc1234': 1` fra gli `unirla`)."""
    document = tmp_path / "registro.md"
    document.write_text(
        "## A. Leggere\n\n| Id | Voce | Stato | Unirla |\n|---|---|---|---|\n"
        "| A-01 | prima | E | PS |\n"
        "| A-03 | terza | NV (x) · E (y) — CONTRADDIZIONE | CC |\n\n"
        "## M. Morto\n\n| Id | Reperto | Righe |\n|---|---|---|\n"
        "| M-01 | un file | `a.py` |\n\n"
        "## Chiuse\n\n| Id | Voce | Chiusa con | Commit | Cosa |\n|---|---|---|---|---|\n"
        "| A-02 | seconda | 3.73.0 | abc1234 | copia tolta |\n", encoding="utf-8")
    tally = registro.verdicts(registro.read_entries(document))
    assert tally == {"stato": {"E": 1, registro.TWO_VERDICTS: 1},
                     "unirla": {"PS": 1, "CC": 1}}


def test_il_documento_non_porta_conti_scritti_a_mano():
    text = REGISTER.read_text(encoding="utf-8")
    assert "**Totale A–G e T**" not in text, (
        "la tabella dei conti e' tornata: i conti si chiedono a "
        "`python scripts/registro.py conta`")


def test_nessuna_voce_resta_fuori_dal_suo_capitolo():
    # Le aggiunte in coda (la vecchia sezione 6) erano voci vere scritte fuori
    # dai capitoli: un lettore che legge i capitoli non le avrebbe viste.
    text = REGISTER.read_text(encoding="utf-8")
    seen = {entry.id for entry in registro.read_entries(REGISTER)}
    written = set(re.findall(rf"^\| ([{CHAPTERS}]-\d{{2,}}) \|", text,
                             flags=re.MULTILINE))
    assert written == seen, sorted(written ^ seen)


def test_una_voce_si_chiude_dentro_la_sezione_chiuse_anche_se_non_e_l_ultima(tmp_path):
    """Mutazione ESEGUITA: accodata la riga a fine file -- rossa (la voce
    chiusa finisce sotto «Appendice» e non viene piu' letta)."""
    document = tmp_path / "registro.md"
    document.write_text(
        "## A. Leggere\n\n| Id | Voce | Stato | Unirla |\n|---|---|---|---|\n"
        "| A-01 | prima | E | PS |\n\n"
        "## Chiuse\n\n| Id | Voce | Chiusa con | Commit | Cosa |\n|---|---|---|---|---|\n\n"
        "## Appendice\n\ntesto\n", encoding="utf-8")
    registro.close(document, "A-01", version="3.73.0", commit="abc1234", note="tolta")
    (entry,) = registro.read_entries(document)
    assert entry.closed and entry.id == "A-01"


def test_una_voce_nel_capitolo_sbagliato_ferma_la_lettura(tmp_path):
    document = tmp_path / "registro.md"
    document.write_text(
        "## A. Leggere\n\n| Id | Voce | Stato | Unirla |\n|---|---|---|---|\n"
        "| B-01 | fuori posto | E | PS |\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="B-01"):
        registro.read_entries(document)


def test_un_id_a_tre_cifre_si_legge(tmp_path):
    document = tmp_path / "registro.md"
    document.write_text(
        "## D. Turni\n\n| Id | Voce | Stato | Unirla |\n|---|---|---|---|\n"
        "| D-100 | centesima | E | PS |\n", encoding="utf-8")
    assert [entry.id for entry in registro.read_entries(document)] == ["D-100"]



#: Un registro piccolo con le tre forme del «fatto ma non rilasciato»: una
#: voce aperta segnata, una aperta non segnata, una chiusa prima della versione.
_WITH_RELEASABLE = (
    "## A. Leggere\n\n| Id | Voce | Stato | Unirla | Fonti |\n|---|---|---|---|---|\n"
    "| A-01 | prima | E | PS | reg · **chiudibile al rilascio** `abc1234`, `def5678`: "
    "copia tolta |\n"
    "| A-03 | terza | D | CC | reg |\n\n"
    "## Chiuse\n\n| Id | Voce | Chiusa con | Commit | Cosa |\n|---|---|---|---|---|\n"
    "| A-02 | seconda | 3.73.0 | 1111111 | tolta |\n"
    "| A-04 | quarta | Tappa 6, Task 7 | 2222222 | tolta prima del rilascio |\n")


def test_una_voce_segnata_si_riconosce_e_porta_i_suoi_commit(tmp_path):
    """Mutazione ESEGUITA: in `releasable` letto solo il primo commit --
    rossa (la voce porta un commit solo invece dei due)."""
    document = tmp_path / "registro.md"
    document.write_text(_WITH_RELEASABLE, encoding="utf-8")
    entries = {entry.id: entry for entry in registro.read_entries(document)}
    assert registro.releasable(entries["A-01"]) == registro.Releasable(
        commits=["abc1234", "def5678"], note="copia tolta")
    assert registro.releasable(entries["A-03"]) is None
    assert [entry.id for entry in registro.closed_early(list(entries.values()))] == ["A-04"]


def test_un_segno_storto_ferma_la_verifica(tmp_path):
    """Un segno che il lettore non capisce non e' una voce chiudibile in meno:
    e' una voce che al rilascio resterebbe aperta in silenzio.
    Mutazione ESEGUITA: `malformed` restituisce sempre [] -- rossa."""
    document = tmp_path / "registro.md"
    document.write_text(_WITH_RELEASABLE.replace("`abc1234`, `def5678`: ", ""),
                        encoding="utf-8")
    assert registro.malformed(registro.read_entries(document)) == ["A-01"]


def test_al_rilascio_le_segnate_si_chiudono_e_le_anticipate_prendono_la_versione(tmp_path):
    """Mutazione ESEGUITA: tolta da `release` la riscrittura delle chiuse in
    anticipo -- rossa (A-04 resta «Tappa 6, Task 7»)."""
    document = tmp_path / "registro.md"
    document.write_text(_WITH_RELEASABLE, encoding="utf-8")
    closed = registro.release(document, version="3.78.0")
    assert closed == ["A-01", "A-04"]
    entries = {entry.id: entry for entry in registro.read_entries(document)}
    assert entries["A-01"].closed
    assert entries["A-01"].cells[2:] == ("3.78.0", "abc1234, def5678", "copia tolta")
    assert entries["A-04"].cells[2] == "3.78.0"
    assert entries["A-02"].cells[2] == "3.73.0"
    assert not entries["A-03"].closed
    assert registro.release(document, version="3.78.0") == []


def test_il_rilascio_vuole_una_versione_vera(tmp_path):
    document = tmp_path / "registro.md"
    document.write_text(_WITH_RELEASABLE, encoding="utf-8")
    with pytest.raises(SystemExit, match="Tappa 7"):
        registro.release(document, version="Tappa 7")


def test_il_registro_vero_non_ha_segni_storti():
    assert registro.malformed(registro.read_entries(REGISTER)) == []


#: Un registro e un BACKLOG piccoli per le trasferite (D1 della Chiusura,
#: 13/10/2026): una voce aperta, la sezione delle trasferite, due voci del
#: BACKLOG, una aperta e una chiusa.
_WITH_TRANSFERRED = (
    "## C. La resa\n\n| Id | Voce | Stato | Unirla | Fonti |\n|---|---|---|---|---|\n"
    "| C-24 | fogli di stile | D | DP | reg |\n"
    "| C-26 | altra | E | PS | reg |\n\n"
    "## Trasferite\n\n| Id | Voce | Voce del BACKLOG | Perché |\n|---|---|---|---|\n\n"
    "## Chiuse\n\n| Id | Voce | Chiusa con | Commit | Cosa |\n|---|---|---|---|---|\n"
    "| C-01 | prima | 3.73.0 | 1111111 | tolta |\n")
_BACKLOG_TEXT = (
    "# BACKLOG\n\n## In attesa\n\n"
    "### I fogli di stile: due sistemi — aperta il 05/10/2026\n\ntesto\n\n"
    "### ~~Una cosa fatta~~ — CHIUSA il 02/10/2026\n\ntesto\n\n"
    "### I soggetti raggruppati — **USCITA con la v3.54.0**, resta `volte`\n")


def _transfer_copies(tmp_path):
    document = tmp_path / "registro.md"
    document.write_text(_WITH_TRANSFERRED, encoding="utf-8")
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(_BACKLOG_TEXT, encoding="utf-8")
    return document, backlog


def test_una_voce_trasferita_non_e_ne_aperta_ne_chiusa(tmp_path):
    """Mutazione ESEGUITA: in `read_entries` la sezione «Trasferite» non
    riconosciuta (`transferred` sempre falso) -- rossa (la riga non si legge
    piu': `C-24` sparisce dal registro)."""
    document, backlog = _transfer_copies(tmp_path)
    registro.transfer(document, "C-24", backlog="I fogli di stile: due sistemi",
                      note="fuori dallo sprint", backlog_path=backlog)
    entries = {entry.id: entry for entry in registro.read_entries(document)}
    assert entries["C-24"].transferred and not entries["C-24"].closed
    assert not registro.is_open(entries["C-24"])
    assert entries["C-24"].cells[2:] == ("I fogli di stile: due sistemi", "fuori dallo sprint")
    assert registro.count(list(entries.values())) == {
        "C": {"aperte": 1, "chiuse": 1, "trasferite": 1}}
    assert registro.untethered(list(entries.values()), backlog) == []


def test_si_trasferisce_solo_a_una_voce_aperta_del_backlog(tmp_path):
    """Mutazione ESEGUITA: in `backlog_titles` tolto il salto delle voci
    barrate o chiuse -- rossa (la voce «~~Una cosa fatta~~» lega una trasferita)."""
    document, backlog = _transfer_copies(tmp_path)
    assert registro.backlog_titles(backlog) == {"I fogli di stile: due sistemi"}
    for title in ("Una voce che non c'e'", "~~Una cosa fatta~~", "I soggetti raggruppati"):
        with pytest.raises(SystemExit, match="non e' una voce aperta del BACKLOG"):
            registro.transfer(document, "C-24", backlog=title, note="x",
                              backlog_path=backlog)
    assert registro.is_open({e.id: e for e in registro.read_entries(document)}["C-24"])


def test_una_trasferita_senza_legame_ferma_la_verifica(tmp_path):
    """Il legame si ricontrolla a ogni verifica: la voce del BACKLOG puo'
    chiudersi, o cambiare titolo, dopo il trasferimento.
    Mutazione ESEGUITA: `untethered` restituisce sempre [] -- rossa."""
    document, backlog = _transfer_copies(tmp_path)
    registro.transfer(document, "C-24", backlog="I fogli di stile: due sistemi",
                      note="x", backlog_path=backlog)
    backlog.write_text(_BACKLOG_TEXT.replace(
        "### I fogli di stile: due sistemi — aperta",
        "### ~~I fogli di stile: due sistemi~~ — CHIUSA"), encoding="utf-8")
    assert registro.untethered(registro.read_entries(document), backlog) == ["C-24"]


def test_la_verifica_vera_si_ferma_su_ogni_difetto(tmp_path, monkeypatch, capsys):
    """Il cancello e' `main` con «verifica»: si fa girare quello, su copie, e
    si pretende l'uscita 1 per ogni ramo (giro 143, N143-1: la prova chiamava
    `untethered` da sola, e il ramo di `main` si poteva togliere a suite verde).
    Mutazioni ESEGUITE, ognuna rossa sul suo caso: in `problems` tolto il
    ramo di `untethered`; tolto il ramo di `malformed`; tolto quello di
    `unfinished`; in `main` l'uscita 1 tolta."""
    document, backlog = _transfer_copies(tmp_path)
    registro.transfer(document, "C-24", backlog="I fogli di stile: due sistemi",
                      note="x", backlog_path=backlog)
    monkeypatch.setattr(registro, "REGISTER", document)
    monkeypatch.setattr(registro, "BACKLOG", backlog)
    monkeypatch.setattr(sys, "argv", ["registro.py", "verifica"])
    registro.main()
    assert "nessuna chiusa a meta'" in capsys.readouterr().out
    healthy = document.read_text(encoding="utf-8")
    broken = {
        "trasferite": (backlog, _BACKLOG_TEXT.replace("— aperta il 05/10/2026", "— CHIUSA")),
        "chiudibile": (document, healthy.replace(
            "| C-26 | altra | E | PS | reg |",
            "| C-26 | altra | E | PS | reg · **chiudibile al rilascio** senza commit |")),
        "senza versione": (document, healthy.replace("| 3.73.0 | 1111111 |", "|  | 1111111 |")),
    }
    for what, (path, text) in broken.items():
        original = path.read_text(encoding="utf-8")
        path.write_text(text, encoding="utf-8")
        with pytest.raises(SystemExit) as stopped:
            registro.main()
        assert stopped.value.code == 1, what
        assert what in capsys.readouterr().err, what
        path.write_text(original, encoding="utf-8")


def test_una_trasferita_non_porta_segno_ne_verdetto(tmp_path):
    """Una trasferita non si chiude al rilascio e non conta fra i doppioni
    aperti, anche se la sua riga porta ancora segno e verdetti (giro 143).
    Mutazioni ESEGUITE: in `releasable` `entry.closed` al posto di `is_open`
    -- rossa; in `verdicts` lo stesso -- rossa."""
    document, _backlog = _transfer_copies(tmp_path)
    document.write_text(_WITH_TRANSFERRED.replace(
        "| C-24 | fogli di stile | D | DP | reg |",
        "| C-24 | fogli di stile | D | DP | reg · **chiudibile al rilascio** `abc1234`: x |"),
        encoding="utf-8")
    rows = document.read_text(encoding="utf-8").splitlines()
    moved = next(row for row in rows if row.startswith("| C-24 |"))
    rows.remove(moved)
    rows.insert(rows.index("|---|---|---|---|") + 1, moved)
    document.write_text("\n".join(rows) + "\n", encoding="utf-8")
    entries = {entry.id: entry for entry in registro.read_entries(document)}
    assert entries["C-24"].transferred
    assert registro.releasable(entries["C-24"]) is None
    assert registro.verdicts(list(entries.values())) == {
        "stato": {"E": 1}, "unirla": {"PS": 1}}


def test_trasferire_o_chiudere_una_trasferita_si_rifiuta(tmp_path):
    """Chiudere una trasferita direbbe «copia cancellata» di una copia che
    resta nel codice.
    Mutazione ESEGUITA: tolto da `_the_open_entry` il rifiuto delle
    trasferite -- rossa (`close` la sposta fra le chiuse senza dire niente)."""
    document, backlog = _transfer_copies(tmp_path)
    registro.transfer(document, "C-24", backlog="I fogli di stile: due sistemi",
                      note="x", backlog_path=backlog)
    with pytest.raises(SystemExit, match="gia' trasferita"):
        registro.transfer(document, "C-24", backlog="I fogli di stile: due sistemi",
                          note="x", backlog_path=backlog)
    with pytest.raises(SystemExit, match="gia' trasferita"):
        registro.close(document, "C-24", version="3.79.0", commit="abc1234", note="x")


def test_le_trasferite_del_registro_vero_hanno_il_loro_legame():
    assert registro.untethered(registro.read_entries(REGISTER)) == []
    # Il lettore del BACKLOG non si e' svuotato: senza titoli ogni legame
    # sembrerebbe rotto, o -- con una mutazione che lo zittisce -- nessuno.
    assert len(registro.backlog_titles()) > 20
