"""`_trim_history`: la cronologia che va al modello comincia da un turno utente.

L'API di Claude rifiuta una conversazione che si apre con un turno
`assistant`. Dalla fetta «il seguito delle chat divise» (Task 3) l'esito di
una promessa entra nel filo come messaggio di HIRIS, e una conversazione puo'
cominciare con UNO O PIU' messaggi `assistant` di fila (due promesse concluse
prima che la persona riscriva).
"""
from hiris.app.api.handlers_chat import _trim_history


def test_un_assistant_in_testa_si_toglie():
    """Il comportamento di prima, pinnato sul codice di partenza."""
    storia = [{"role": "assistant", "content": "a"},
              {"role": "user", "content": "u"},
              {"role": "assistant", "content": "b"},
              {"role": "user", "content": "v"}]
    assert _trim_history(storia) == storia[1:]


def test_piu_assistant_in_testa_si_tolgono_tutti():
    storia = [{"role": "assistant", "content": "esito 1"},
              {"role": "assistant", "content": "esito 2"},
              {"role": "user", "content": "grazie"}]
    assert _trim_history(storia) == [{"role": "user", "content": "grazie"}]


def test_una_storia_che_comincia_da_utente_resta_com_e():
    storia = [{"role": "user", "content": "u"},
              {"role": "assistant", "content": "a"},
              {"role": "assistant", "content": "esito"}]
    assert _trim_history(storia) == storia
