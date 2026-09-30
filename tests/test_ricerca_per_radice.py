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
    """«tv» non deve trovare «tvoc»; «luce» (4 lettere) resta una parola
    intera: nessun prefisso.

    Mutazione ESEGUITA: STEM_MIN_LENGTH = 4 -- rossa («luce» trova
    «Lucernario»).
    """
    assert not name_matches("tv", "Sensore tvoc")
    assert name_matches("luce", "Luce finestrone")
    assert not name_matches("luce", "Lucernario bagno")
    assert not name_matches("luci", "Lucido")


def test_a_quattro_lettere_singolare_e_plurale_si_trovano():
    """Review finale, M4 (30/09/2026): «luci» non trovava «Luce», e la
    domanda «le luci» e' la piu' comune che ci sia.

    Mutazione ESEGUITA: togliere il ramo `_PAIR_LENGTH` da `_word_pattern` --
    rossa."""
    for query, name in (("luci", "Luce finestrone"), ("luce", "Luci di Natale"),
                        ("casa", "Case sull'albero"), ("case", "Casa al mare"),
                        ("faro", "Fari giardino"), ("fari", "Faro ingresso"),
                        ("rete", "Reti Wi-Fi"), ("anta", "Ante armadio")):
        assert name_matches(query, name), (query, name)


def test_a_quattro_lettere_parole_diverse_non_si_confondono():
    """La vocale cambia solo nella propria coppia: «casa» non e' «caso»,
    «pala» non e' «palo», «tele» non e' «telo».

    Mutazione ESEGUITA: `_NUMBER_PAIRS` con ogni vocale per ogni vocale
    (`"aeiou"`) -- rossa."""
    for query, name in (("casa", "Caso limite"), ("pala", "Palo della luce"),
                        ("tele", "Telo ombreggiante"), ("moto", "Mote di polvere"),
                        ("faro", "Fare la spesa"), ("luce", "Lucy")):
        assert not name_matches(query, name), (query, name)


def test_tutte_le_parole_significative_devono_esserci():
    """Mutazione ESEGUITA: `all` -> `any` sulle parole -- rossa."""
    assert name_matches("automazioni rifiuti", "Gestione Rifiuto Vetro") is False
    assert name_matches("rifiuti vetro", "Gestione Rifiuto VETRO")
    assert name_matches("il vetro", "Gestione Rifiuto VETRO")


def test_accenti_e_maiuscole_non_contano():
    assert name_matches("umidita", "Umidità cantina")
