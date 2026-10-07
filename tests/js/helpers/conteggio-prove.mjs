/* Il conteggio delle prove JS e' un fatto che si confronta (CLAUDE.md, regola
 * di Paolo del 05/10/2026). Questo e' un reporter di `node --test`, montato da
 * `npm test` accanto a quello che si legge: conta le prove raccolte file per
 * file, le confronta con quelle del giro prima su questo clone, e quando un
 * file ne porta meno lo dice per nome e fa uscire la corsa con 1.
 *
 * Il giro prima vive in `node_modules/.cache/` (fuori da git): e' la memoria
 * di questo clone, non un fatto del progetto da ricopiare a mano. Un clone
 * nuovo (la CI) non ha giro prima, e il confronto parte dal giro dopo.
 *
 * Scrive su stderr, non su stdout accanto al reporter che si legge: con
 * `--test-force-exit` il padre aspetta che ogni destinazione sia staccata
 * prima di uscire, ma due reporter sulla STESSA destinazione si sciolgono al
 * primo distacco, e questo resoconto si perdeva. Misurato il 07/10/2026
 * (Node 22.22.0): sulla stessa stdout di `spec` non e' uscito ne' sulla
 * suite intera ne' su due file soli; su stderr, tre corse su tre.
 *
 * Un conto che scende NON si salva (revisore, N75-1, 07/10/2026): se si
 * salvasse, un rilancio automatico confronterebbe con il conto gia' sceso e
 * direbbe di si', e il confronto sarebbe spento da chi rilancia. Se le prove
 * le hai tolte tu, lo dici: `HIRIS_PROVE_JS_OK=1 npm test` accetta il conto
 * nuovo, lo salva e non ferma la corsa. Il valore accettato e' esattamente
 * `1`, come `HIRIS_COMPONENTI_OK` del cancello del rilascio. */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
export const MEMORIA = join(ROOT, 'node_modules', '.cache', 'hiris-prove-js.json');

/** Le prove raccolte di questo giro, per file: solo quelle di primo livello. */
export function contaPerFile(eventi) {
  const perFile = {};
  for (const { type, data } of eventi) {
    if (type !== 'test:pass' && type !== 'test:fail') continue;
    if (data.nesting !== 0) continue;
    const file = data.file ? relative(ROOT, data.file).split('\\').join('/') : '(senza file)';
    perFile[file] = (perFile[file] ?? 0) + 1;
  }
  return perFile;
}

/** Cosa e' sceso rispetto al giro prima: un file sparito conta come zero. */
export function scese(prima, adesso) {
  const righe = [];
  for (const [file, quante] of Object.entries(prima ?? {})) {
    const ora = adesso[file] ?? 0;
    if (ora < quante) righe.push({ file, prima: quante, adesso: ora });
  }
  return righe.sort((a, b) => a.file.localeCompare(b.file));
}

const somma = (perFile) => Object.values(perFile ?? {}).reduce((a, b) => a + b, 0);

/** Il testo che il reporter scrive, se la corsa va fermata e se il conto si
 * salva. `accetta` e' il si' di chi ha tolto le prove apposta. */
export function resoconto(prima, adesso, { accetta = false } = {}) {
  const totale = somma(adesso);
  if (prima == null) {
    return {
      ferma: false,
      salva: true,
      testo: `prove JS raccolte: ${totale} (nessun giro prima su questo clone)\n`,
    };
  }
  const giu = scese(prima, adesso);
  const intestazione = `prove JS raccolte: ${totale} (il giro prima: ${somma(prima)})\n`;
  if (giu.length === 0) return { ferma: false, salva: true, testo: intestazione };
  const dettagli = giu.map((r) => `  ${r.file}: ${r.adesso} invece di ${r.prima}\n`).join('');
  if (accetta) {
    return {
      ferma: false,
      salva: true,
      testo: intestazione + `Conto sceso, accettato con HIRIS_PROVE_JS_OK=1:\n${dettagli}`,
    };
  }
  return {
    ferma: true,
    salva: false,
    testo:
      intestazione +
      `ATTENZIONE: questi file hanno raccolto meno prove del giro prima, senza dirlo:\n${dettagli}` +
      'Il conto nuovo non e\' salvato. Se le hai tolte tu: HIRIS_PROVE_JS_OK=1 npm test\n',
  };
}

function leggiMemoria(memoria) {
  try {
    return JSON.parse(readFileSync(memoria, 'utf8')).per_file;
  } catch {
    return null;
  }
}

/** Confronta con il giro prima scritto in `memoria`, e salva il conto nuovo
 * solo se il resoconto lo consente. */
export function registra(adesso, { memoria = MEMORIA, accetta = false } = {}) {
  const esito = resoconto(leggiMemoria(memoria), adesso, { accetta });
  if (esito.salva) {
    mkdirSync(dirname(memoria), { recursive: true });
    writeFileSync(memoria, JSON.stringify({ per_file: adesso }, null, 1));
  }
  return esito;
}

export default async function* conteggioProve(sorgente) {
  const eventi = [];
  for await (const evento of sorgente) {
    if (evento.type === 'test:pass' || evento.type === 'test:fail') eventi.push(evento);
  }
  const { ferma, testo } = registra(contaPerFile(eventi), {
    accetta: process.env.HIRIS_PROVE_JS_OK === '1',
  });
  if (ferma) process.exitCode = 1;
  yield testo;
}
