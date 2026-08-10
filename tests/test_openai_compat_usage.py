# tests/test_openai_compat_usage.py
#
# fetta E4 Task 6 ("un bot solo"): tutti e tre i test che vivevano qui sono
# usciti, cancellati e non spostati -- nessuno dei tre aveva piu' un soggetto
# vivo:
#   - test_estimate_tokens_is_conservative_and_bounded provava
#     `_estimate_tokens`, uscita insieme al suo unico chiamante
#     (`_track_usage`'s per-chatbot estimate branch, sotto).
#   - test_track_usage_estimates_when_usage_absent / test_track_usage_records_
#     nothing_extra_when_no_text_and_no_chars provavano la stima per-chatbot
#     di `_track_usage` quando la risposta non porta `usage` -- quella stima
#     esisteva SOLO per far "mordere" un budget per-esecuzione letto da
#     `get_chatbot_usage` (il commento del test citava
#     "server.py agent_run_usage -> get_chatbot_usage"): entrambi i lettori
#     sono gia' morti da prima di questo task (rotte usage uscite al Task 3,
#     ChatbotEngine al Task 4) -- verificato zero occorrenze di
#     `agent_run_usage` in produzione. Senza quel lettore la stima non aveva
#     piu' nessuno scopo osservabile.
#
# Verificato che cadessero per costruzione prima di cancellarli:
#   ImportError: cannot import name '_estimate_tokens' from
#   'hiris.app.backends.openai_compat_runner'
# (il modulo aveva gia' perso `_estimate_tokens` quando questo file veniva
# importato -- la seconda coppia di test avrebbe fallito a sua volta con
# TypeError su `_track_usage(..., "ag1", ...)`, la firma non accetta piu'
# `chatbot_id` posizionale).
#
# `_track_usage`'s comportamento sui contatori GLOBALI (total_input_tokens/
# total_output_tokens/total_cost_usd, quando `usage` E' presente) resta un
# soggetto vivo -- ma nessuno dei tre test qui lo provava (tutti e tre
# esercitavano SOLO il ramo "usage assente", ora un semplice log): nessuna
# copertura persa sui contatori globali, perche' non ce n'era in questo file.
# tests/test_claude_runner.py::test_save_usage_concurrent_writes_keep_valid_json
# resta il pin vivo sulla persistenza di usage.json (soggetto condiviso dai
# due runner, stesso schema).
