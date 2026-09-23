"""Porta i caratteri tipografici DENTRO l'add-on (reperto D-7, 23/09/2026).

Fino a oggi le due pagine chiedevano i caratteri a `fonts.googleapis.com` a
ogni apertura. Tre conseguenze, e nessuna e' teorica:

- **rivela al fornitore indirizzo e programma del proprietario**: ogni volta
  che apri HIRIS, un terzo impara che quella casa e' sveglia e a che ora;
- **l'add-on non e' autosufficiente senza rete**: una casa con la rete giu' --
  esattamente quella in cui HIRIS serve di piu' -- apre le pagine coi
  caratteri di ripiego;
- **la politica dei contenuti resta aperta verso l'esterno**: finche' il
  foglio di stile puo' venire da fuori, `style-src` deve ammetterlo.

**Questo script si esegue a mano, non al build.** Scaricare al build
significherebbe che due costruzioni della stessa versione di HIRIS possono
contenere due caratteri diversi -- la stessa ragione per cui la CLI del ponte
e' pinnata a una versione esatta (`Dockerfile`). I file scaricati **entrano
nel repository** e si aggiornano quando qualcuno lo decide.

Uso:  python scripts/vendora_caratteri.py

Solo i sottoinsiemi **latino e latino esteso**: cirillico, greco e vietnamita
erano il grosso del peso e questo prodotto parla italiano e inglese. Se un
giorno servira' un'altra lingua, si aggiunge qui.

Licenze: Geist e Geist Mono (Vercel) e JetBrains Mono (JetBrains) sono tutti e
tre sotto SIL Open Font License 1.1, che permette la ridistribuzione. Il testo
della licenza viaggia con loro in `hiris/app/static/fonts/OFL.txt`.
"""
from __future__ import annotations

import pathlib
import re
import sys
import urllib.request

RADICE = pathlib.Path(__file__).resolve().parents[1]
DESTINAZIONE = RADICE / "hiris" / "app" / "static" / "fonts"

#: L'agente dice a Google di servire woff2: con un agente sconosciuto risponde
#: ttf, che pesa il triplo.
AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

#: La stessa richiesta che stava in `<link>` nelle due pagine, in forma
#: VARIABILE (`300..700` invece di `300;400;500;600;700`): un file per faccia
#: invece di uno per peso, stesso risultato a schermo.
SORGENTE = ("https://fonts.googleapis.com/css2"
            "?family=Geist:wght@300..700"
            "&family=Geist+Mono:ital,wght@0,400..600;1,400"
            "&family=JetBrains+Mono:wght@400..600"
            "&display=swap")

SOTTOINSIEMI = ("latin", "latin-ext")

BLOCCO = re.compile(r"/\*\s*([a-z-]+)\s*\*/\s*(@font-face\s*\{[^}]*\})",
                    re.IGNORECASE)
URL = re.compile(r"url\((https://fonts\.gstatic\.com/[^)]+)\)")


def _scarica(indirizzo: str) -> bytes:
    richiesta = urllib.request.Request(indirizzo, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(richiesta, timeout=60) as risposta:
        return risposta.read()


def _nome(blocco: str, sottoinsieme: str) -> str:
    famiglia = re.search(r"font-family:\s*'([^']+)'", blocco).group(1)
    stile = re.search(r"font-style:\s*(\w+)", blocco).group(1)
    peso = re.search(r"font-weight:\s*([\d ]+)", blocco).group(1).strip()
    return (f"{famiglia}-{stile}-{peso}-{sottoinsieme}"
            .lower().replace(" ", "_") + ".woff2")


def main() -> int:
    DESTINAZIONE.mkdir(parents=True, exist_ok=True)
    css = _scarica(SORGENTE).decode("utf-8")
    pezzi = []
    scaricati = 0
    for sottoinsieme, blocco in BLOCCO.findall(css):
        if sottoinsieme not in SOTTOINSIEMI:
            continue
        indirizzo = URL.search(blocco).group(1)
        nome = _nome(blocco, sottoinsieme)
        (DESTINAZIONE / nome).write_bytes(_scarica(indirizzo))
        scaricati += 1
        pezzi.append(f"/* {sottoinsieme} */\n"
                     + URL.sub(f"url(fonts/{nome})", blocco))
        print(f"  {nome}  ({(DESTINAZIONE / nome).stat().st_size // 1024} KB)")
    if not pezzi:
        print("nessun blocco riconosciuto: il formato della risposta e' cambiato")
        return 1
    intestazione = (
        "/* I caratteri di HIRIS, DENTRO l'add-on (reperto D-7, 23/09/2026).\n"
        "\n"
        "   **Questo file e' GENERATO**: si rifa' con\n"
        "   `python scripts/vendora_caratteri.py`, che dice anche da dove\n"
        "   vengono i file e perche' sono qui invece che a Google.\n"
        "\n"
        "   Solo latino e latino esteso: il resto era il grosso del peso, e\n"
        "   questo prodotto parla italiano e inglese.\n"
        "\n"
        "   Geist e Geist Mono (Vercel), JetBrains Mono (JetBrains): SIL Open\n"
        "   Font License 1.1, testo in `fonts/OFL-*.txt`. */\n\n")
    (DESTINAZIONE.parent / "hiris-fonts.css").write_text(
        intestazione + "\n\n".join(pezzi) + "\n", encoding="utf-8")
    print(f"\n{scaricati} file, e hiris-fonts.css rifatto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
