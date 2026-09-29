"""Il filtro `nome` confronta anche per radice (spec §2.2, causa 4).

Misurato il 29/09/2026: «rifiuti» e «indifferenziata» davano zero, «rifiuto»
dava tutte e cinque le automazioni.
"""
from hiris.app.memory.resolver import name_matches


def test_il_plurale_trova_il_singolare():
    """Mutazione ESEGUITA: solo parola intera -- rossa."""
    assert name_matches("rifiuti", "Gestione Rifiuto Carta")
    assert name_matches("indifferenziata", "Gestione Rifiuto Indifferenziato (SECCO) ")


def test_le_parole_corte_restano_intere():
    """«tv» non deve trovare «tvoc»; «luce» (4 lettere) resta intera.

    Mutazione ESEGUITA: STEM_MIN_LENGTH = 4 -- rossa (luce trova Luci).
    """
    assert not name_matches("tv", "Sensore tvoc")
    assert name_matches("luce", "Luce finestrone")
    assert not name_matches("luce", "Luci di Natale")


def test_tutte_le_parole_significative_devono_esserci():
    """Mutazione ESEGUITA: `all` -> `any` sulle parole -- rossa."""
    assert name_matches("automazioni rifiuti", "Gestione Rifiuto Vetro") is False
    assert name_matches("rifiuti vetro", "Gestione Rifiuto VETRO")
    assert name_matches("il vetro", "Gestione Rifiuto VETRO")


def test_accenti_e_maiuscole_non_contano():
    assert name_matches("umidita", "Umidità cantina")
