"""Ogni bit delle tabelle delle capacita', pinnato contro la fonte -- non
contro se stesso.

La review indipendente ha trovato che tre mutazioni sulle tabelle restavano
VERDI: `climate` con 128/256 (spegnimento/accensione) scambiati, `update`
con `RELEASE_NOTES` spostato da 16 a 64, `media_player` senza `STOP`. La
causa: le prove esistenti pinnavano quasi solo il BIT 1 di ogni tabella (un
`decoded_capabilities(dominio, 1) == [nome]`), e un dominio con nove o
ventuno voci ne aveva una sola protetta.

Questo file elenca OGNI (bit, nome) di OGNI tabella, COPIATO A MANO dalla
fonte -- non importato dal vocabolario dei tipi -- cosi' una mutazione della
tabella implementativa non puo' portarsi dietro anche il test che dovrebbe
scoprirla (la stessa ragione per cui un test non deve derivare il proprio
oracolo dalla stessa finta che sta verificando).

Le tabelle vivevano in `topology._FEATURE_NAMES` fino al 07/09/2026; ora sono
il campo `capability_names` delle righe del vocabolario dei tipi, con la loro
provenienza dichiarata (`importato`) e la versione da cui vengono. Questo file
non e' cambiato in cio' che pinna: e' cambiato il posto da cui legge il primo
elenco, e resta il secondo.

Fonte: sorgente vero di Home Assistant, tag `2024.7.0` e `2026.9.1`, mai
`dev` -- vedi il commento sopra `_FEATURE_TABLES` in `type_vocabulary.py` per
la citazione file-per-file.
"""
import pytest

from hiris.app.home_space.topology import decoded_capabilities
from hiris.app.home_space.type_vocabulary import capability_tables

# (dominio, bit, nome) -- una riga per OGNI voce di OGNI tabella verificata
# su questa fetta. L'ordine ricalca quello di `_FEATURE_TABLES`, ma i valori
# sono scritti qui di nuovo: e' un secondo elenco che deve continuare a
# essere d'accordo col primo, non una copia che lo scavalca.
_PINNED_BITS = [
    # update -- UpdateEntityFeature, components/update/const.py
    ("update", 1, "installazione"),
    ("update", 2, "versione_specifica"),
    ("update", 4, "avanzamento_installazione"),
    ("update", 8, "backup"),
    ("update", 16, "note_di_rilascio"),
    # light -- LightEntityFeature, components/light/const.py
    ("light", 4, "effetti"),
    ("light", 8, "flash"),
    ("light", 32, "transizione"),
    # notify -- NotifyEntityFeature, components/notify/__init__.py
    ("notify", 1, "titolo"),
    # camera -- CameraEntityFeature, components/camera/__init__.py
    ("camera", 1, "accensione"),
    ("camera", 2, "streaming"),
    # climate -- ClimateEntityFeature, components/climate/const.py (64 escluso)
    ("climate", 1, "temperatura_target"),
    ("climate", 2, "intervallo_temperatura"),
    ("climate", 4, "umidita_target"),
    ("climate", 8, "modo_ventola"),
    ("climate", 16, "preset"),
    ("climate", 32, "oscillazione"),
    ("climate", 128, "spegnimento"),
    ("climate", 256, "accensione"),
    ("climate", 512, "oscillazione_orizzontale"),
    # media_player -- MediaPlayerEntityFeature, components/media_player/const.py
    ("media_player", 1, "pausa"),
    ("media_player", 2, "avanzamento"),
    ("media_player", 4, "volume"),
    ("media_player", 8, "muto"),
    ("media_player", 16, "traccia_precedente"),
    ("media_player", 32, "traccia_successiva"),
    ("media_player", 128, "accensione"),
    ("media_player", 256, "spegnimento"),
    ("media_player", 512, "riproduzione_media"),
    ("media_player", 1024, "volume_a_passi"),
    ("media_player", 2048, "selezione_sorgente"),
    ("media_player", 4096, "stop"),
    ("media_player", 8192, "svuota_playlist"),
    ("media_player", 16384, "play"),
    ("media_player", 32768, "shuffle"),
    ("media_player", 65536, "modo_audio"),
    ("media_player", 131072, "sfoglia_media"),
    ("media_player", 262144, "ripeti"),
    ("media_player", 524288, "raggruppamento"),
    ("media_player", 1048576, "annuncio"),
    ("media_player", 2097152, "accoda"),
    ("media_player", 4194304, "ricerca_media"),
    # valve -- ValveEntityFeature, components/valve/__init__.py
    ("valve", 1, "apertura"),
    ("valve", 2, "chiusura"),
    ("valve", 4, "posizione"),
    ("valve", 8, "stop"),
    # cover -- CoverEntityFeature, components/cover/const.py (0/181 qui)
    ("cover", 1, "apertura"),
    ("cover", 2, "chiusura"),
    ("cover", 4, "posizione"),
    ("cover", 8, "stop"),
    ("cover", 16, "apertura_lamelle"),
    ("cover", 32, "chiusura_lamelle"),
    ("cover", 64, "stop_lamelle"),
    ("cover", 128, "posizione_lamelle"),
    ("cover", 256, "velocita"),
    # fan -- FanEntityFeature, components/fan/__init__.py (0/181 qui)
    ("fan", 1, "velocita"),
    ("fan", 2, "oscillazione"),
    ("fan", 4, "direzione"),
    ("fan", 8, "preset"),
    ("fan", 16, "spegnimento"),
    ("fan", 32, "accensione"),
    # water_heater -- WaterHeaterEntityFeature, .../__init__.py (0/181 qui)
    ("water_heater", 1, "temperatura_target"),
    ("water_heater", 2, "modo_operativo"),
    ("water_heater", 4, "modo_assenza"),
    ("water_heater", 8, "accensione_spegnimento"),
    # vacuum -- VacuumEntityFeature, components/vacuum/const.py (64 escluso, 0/181 qui)
    ("vacuum", 1, "accensione"),
    ("vacuum", 2, "spegnimento"),
    ("vacuum", 4, "pausa"),
    ("vacuum", 8, "stop"),
    ("vacuum", 16, "rientro_alla_base"),
    ("vacuum", 32, "velocita_aspirazione"),
    ("vacuum", 128, "stato_dettagliato"),
    ("vacuum", 256, "comando_diretto"),
    ("vacuum", 512, "localizzazione"),
    ("vacuum", 1024, "pulizia_puntuale"),
    ("vacuum", 2048, "mappa"),
    ("vacuum", 4096, "riporta_stato"),
    ("vacuum", 8192, "avvio"),
    ("vacuum", 16384, "pulizia_area"),
    # weather -- WeatherEntityFeature, components/weather/const.py
    ("weather", 1, "previsioni_giornaliere"),
    ("weather", 2, "previsioni_orarie"),
    ("weather", 4, "previsioni_due_volte_al_giorno"),
    # siren -- SirenEntityFeature, components/siren/const.py
    ("siren", 1, "accensione"),
    ("siren", 2, "spegnimento"),
    ("siren", 4, "toni"),
    ("siren", 8, "volume"),
    ("siren", 16, "durata"),
    # todo -- TodoListEntityFeature, components/todo/const.py
    ("todo", 1, "crea_elemento"),
    ("todo", 2, "elimina_elemento"),
    ("todo", 4, "aggiorna_elemento"),
    ("todo", 8, "sposta_elemento"),
    ("todo", 16, "scadenza_data"),
    ("todo", 32, "scadenza_data_ora"),
    ("todo", 64, "descrizione_elemento"),
    # alarm_control_panel -- AlarmControlPanelEntityFeature, .../const.py
    ("alarm_control_panel", 1, "armato_in_casa"),
    ("alarm_control_panel", 2, "armato_fuori_casa"),
    ("alarm_control_panel", 4, "armato_notte"),
    ("alarm_control_panel", 8, "allarme"),
    ("alarm_control_panel", 16, "armato_bypass"),
    ("alarm_control_panel", 32, "armato_vacanza"),
    # calendar -- CalendarEntityFeature, components/calendar/const.py
    ("calendar", 1, "crea_evento"),
    ("calendar", 2, "elimina_evento"),
    ("calendar", 4, "aggiorna_evento"),
    # remote -- RemoteEntityFeature, components/remote/__init__.py
    ("remote", 1, "apprendimento_comando"),
    ("remote", 2, "elimina_comando"),
    ("remote", 4, "attivita"),
    # conversation -- ConversationEntityFeature, nato prima di 2026.9.1
    ("conversation", 1, "controllo"),
    # I quattro nominati dal censore (08/09/2026): il registro dei servizi di
    # questa casa dichiarava bit per domini che non avevano nessuna tabella.
    # lock -- LockEntityFeature, components/lock/__init__.py (identica ai due tag)
    ("lock", 1, "apertura"),
    # humidifier -- HumidifierEntityFeature, .../const.py (identica ai due tag)
    ("humidifier", 1, "modi"),
    # lawn_mower -- LawnMowerEntityFeature, .../const.py (identica ai due tag)
    ("lawn_mower", 1, "avvio_taglio"),
    ("lawn_mower", 2, "pausa"),
    ("lawn_mower", 4, "rientro_alla_base"),
    # assist_satellite -- AssistSatelliteEntityFeature, .../const.py: il
    # componente NON esiste a 2024.7.0 (404 su entrambi i file), nasce prima
    # di 2026.9.1 -- lo stesso caso di `conversation`.
    ("assist_satellite", 1, "annuncio"),
    ("assist_satellite", 2, "avvio_conversazione"),
]


@pytest.mark.parametrize("domain,bit,name", _PINNED_BITS,
                         ids=[f"{d}:{b}:{n}" for d, b, n in _PINNED_BITS])
def test_every_bit_decodes_to_the_name_verified_at_the_source(domain, bit, name):
    """Mutazione (per ogni riga): scambiare due valori nella tabella
    implementativa (per esempio `climate` 128<->256) -- il test della riga
    scambiata torna rosso su `assert decoded_capabilities(domain, bit) ==
    [name]`, perche' l'atteso qui e' scritto a mano e non deriva dalla
    tabella che sta verificando."""
    assert decoded_capabilities(domain, bit) == [name]


def test_pinned_bits_cover_every_entry_of_every_table_exactly():
    """Non solo "ogni voce pinnata e' corretta" -- anche "ogni voce della
    tabella e' pinnata": una voce aggiunta a una tabella senza una riga
    gemella qui sopra passerebbe questo file senza protezione, la stessa
    falsa sicurezza che ha lasciato passare le tre mutazioni della review.

    Mutazione: aggiungere un bit a una tabella (per esempio `light: {...,
    64: "nuovo"}`) senza aggiungerlo a `_PINNED_BITS` -- il test torna
    rosso sulla differenza fra i due insiemi."""
    pinned = {(d, b) for d, b, _ in _PINNED_BITS}
    implemented = {(d, b) for d, table in capability_tables().items() for b in table}
    assert pinned == implemented, (
        f"pinnati ma non implementati: {pinned - implemented} -- "
        f"implementati ma non pinnati: {implemented - pinned}")


def test_pinned_bits_agree_with_the_implementation_domain_by_domain():
    """Stessa garanzia della prova sopra, ma leggibile domino per dominio se
    fallisce: un `assert` sull'insieme intero dice CHE differiscono, non
    QUALE dominio.

    Mutazione: scambiare due valori nella tabella implementativa (per
    esempio `climate` 128<->256, la stessa gia' riprodotta dalla review
    indipendente) -- il test torna rosso su `assert pinned_by_domain ==
    capability_tables()`, con il dominio sbagliato visibile nel diff di
    pytest."""
    pinned_by_domain: dict[str, dict[int, str]] = {}
    for domain, bit, name in _PINNED_BITS:
        pinned_by_domain.setdefault(domain, {})[bit] = name
    assert pinned_by_domain == dict(capability_tables())
