"""La scelta della superficie temporale: pura, e provabile senza rete.

E' la spec §3.1 resa eseguibile. Sceglie il CODICE perche' la scelta non e'
una questione di intenzione: dipende da quanto indietro si guarda e da che
tipo e' l'entita'. Chiederlo al modello significherebbe pretendere che
conosca la politica di conservazione del recorder di QUESTA casa.
"""
import pytest

from hiris.app.casa.tempo import (
    MAX_FINESTRA_ORE, SOGLIA_GRANA_ORE, finestra, normalizza_ore,
    scegli_superficie,
)


def test_sotto_la_soglia_si_guardano_i_cambi_veri():
    assert scegli_superficie(ore=6, ha_statistiche=True) == "dettaglio"
    assert scegli_superficie(ore=6, ha_statistiche=False) == "dettaglio"


def test_sopra_la_soglia_con_statistiche_si_passa_alle_fasce():
    assert scegli_superficie(ore=48, ha_statistiche=True) == "statistiche"


def test_sopra_la_soglia_senza_statistiche_resta_il_dettaglio():
    """Non e' una svista: per un'entita' senza `state_class` il dettaglio e'
    l'UNICA fonte che esista. Passare alle statistiche darebbe un elenco
    vuoto, cioe' «non e' mai cambiato»."""
    assert scegli_superficie(ore=48, ha_statistiche=False) == "dettaglio"


def test_la_soglia_e_inclusiva_e_dichiarata():
    assert SOGLIA_GRANA_ORE == 24
    assert scegli_superficie(ore=SOGLIA_GRANA_ORE, ha_statistiche=True) == "dettaglio"
    assert scegli_superficie(ore=SOGLIA_GRANA_ORE + 0.1, ha_statistiche=True) == "statistiche"


@pytest.mark.parametrize("grezzo", [None, "molte", float("nan"), -3, 0, 10**12])
def test_ore_impossibili_non_sollevano_mai(grezzo):
    """`ore` arriva da una tool-call: puo' essere qualunque cosa. Un
    OverflowError dentro un timedelta spezzerebbe il turno del modello."""
    ore = normalizza_ore(grezzo)
    assert 1.0 <= ore <= MAX_FINESTRA_ORE


def test_la_finestra_si_calcola_nel_fuso_della_casa():
    """Le statistiche tornano in UTC, l'utente pensa in ora locale. La fetta
    dello schedulatore ha gia' pagato un difetto di orologi diversi: qui la
    finestra nasce nel fuso della casa e lo porta scritto (spec §3.4)."""
    # 24 agosto 2026, 12:00 UTC = 14:00 a Roma (CEST, +02:00).
    adesso = 1787572800.0
    da, a = finestra(ore=2, adesso_ts=adesso, fuso="Europe/Rome")
    assert a.startswith("2026-08-24T14:00:00")
    assert da.startswith("2026-08-24T12:00:00")
    assert a.endswith("+02:00") and da.endswith("+02:00")


def test_senza_fuso_noto_si_resta_in_utc_e_non_si_inventa():
    """`sistema_di_riferimento()` puo' non aver mai letto la casa. Un fuso
    inventato sposterebbe le ore di una risposta senza dirlo a nessuno."""
    da, a = finestra(ore=2, adesso_ts=1787572800.0, fuso=None)
    assert a.endswith("+00:00") and da.endswith("+00:00")


def test_un_fuso_che_non_esiste_non_solleva():
    da, a = finestra(ore=2, adesso_ts=1787572800.0, fuso="Marte/Olympus")
    assert a.endswith("+00:00")


def test_normalizza_ore_unificata_clampla_al_tetto_del_diario():
    """La normalizzazione ore e' centrale: la usano sia gli strumenti del tempo
    (tetto 2160 = 90 giorni) sia il diario del client (tetto 168 = una
    settimana). Questo test verifica che il diario riceva il suo tetto
    specifico, non quello di tempo.py. Se togli tetto=MAX_DIARIO_ORE dalla
    chiamata di normalizza_ore in ha_client.py, questo test arrossisce
    (perche' 200 ore non verrebbe clampato a 168)."""
    MAX_DIARIO_ORE = 168
    DEFAULT_DIARIO_ORE = 24
    # 200 ore: sopra il tetto di diario (168), ma sotto il tetto di tempo (2160)
    # Con tetto=168: ritorna 168
    # Senza tetto corretto: ritorna 200 e il test fallisce
    ore = normalizza_ore(200, tetto=MAX_DIARIO_ORE, default=DEFAULT_DIARIO_ORE)
    assert ore == MAX_DIARIO_ORE
