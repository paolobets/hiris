/* Caricato con `--import` da `npm test`, nel processo padre e in ogni figlio
 * (il padre passa i propri `execArgv` ai figli che lancia, uno per file).
 *
 * Perche' esiste. `--test-force-exit` (lo difende
 * tests/test_sponde_js.py: un cronometro orfano altrimenti tiene appesa la
 * corsa) fa chiamare a ogni figlio `process.exit()` appena l'ultima prova del
 * file finisce. Il figlio consegna gli esiti al padre scrivendoli sulla
 * propria uscita, che e' una pipe; e sulle pipe POSIX le scritture di Node
 * sono ASINCRONE (documentazione di Node 22, `process`, «A note on process
 * I/O»). Se il padre legge piu' lento di quanto il figlio scriva, la pipe si
 * riempie, il resto resta in coda, e `process.exit()` lo butta: gli esiti di
 * coda di quel file non arrivano mai, il figlio esce 0, e il conteggio
 * scende SENZA nessuna prova rossa.
 *
 * Misurato il 07/10/2026 (Node 22.22.0, Linux): fermando a intermittenza il
 * processo padre, tre corse hanno raccolto 553, 551 e 552 prove su 638, tutte
 * con 0 rosse e codice 0; due corse uguali senza `--test-force-exit` ne hanno
 * raccolte 638 su 638. E' la causa della voce del BACKLOG «Il conteggio
 * instabile di `npm test`» (577, 599, 601 invece di 592 e 614 il 05/10).
 *
 * La correzione: l'uscita diventa bloccante, cosi' ogni scrittura e' sulla
 * pipe prima che la successiva parta, e `process.exit()` non trova niente in
 * coda. Su un file l'uscita e' gia' sincrona e non ha `setBlocking`: non si
 * tocca. */
for (const flusso of [process.stdout, process.stderr]) {
  if (typeof flusso._handle?.setBlocking === 'function') flusso._handle.setBlocking(true);
}
