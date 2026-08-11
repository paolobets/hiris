/* HIRIS · Chat page · shared state (SP-4 Fase B Task 8: rebuild pagina chat;
   fetta E5 Task 3: via l'elenco dei bot -- una conversazione sola)
   Single mutable namespace the other chat/*.js modules read/write, so the
   page keeps working like the old inline <script> (one shared "turnCount"
   etc.) without resorting to bare top-level `var` across files. Cached DOM
   refs here instead of re-querying in every module -- this file loads right
   after the body markup, exactly where the old inline <script> used to sit,
   so the elements already exist. */
(function() {
  var HIRIS_AVATAR = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="28" height="28" style="display:block;border-radius:50%">'
    + '<defs><radialGradient id="hbg" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#2a0a4e"/><stop offset="100%" stop-color="#0a0015"/></radialGradient></defs>'
    + '<circle cx="50" cy="50" r="50" fill="url(#hbg)"/>'
    + '<g transform="translate(50,50)">'
    + '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#c084fc"/>'
    + '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#818cf8" transform="rotate(60)"/>'
    + '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#60a5fa" transform="rotate(120)"/>'
    + '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#22d3ee" transform="rotate(180)"/>'
    + '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#2dd4bf" transform="rotate(240)"/>'
    + '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#e879f9" transform="rotate(300)"/>'
    + '</g>'
    + '<circle cx="50" cy="50" r="4.5" fill="white"/>'
    + '</svg>';

  window.HirisChatState = {
    HIRIS_AVATAR: HIRIS_AVATAR,
    els: {
      messages: document.getElementById('messages'),
      input: document.getElementById('input'),
      sendBtn: document.getElementById('send-btn'),
      welcome: document.getElementById('welcome'),
      connDot: document.getElementById('conn-dot'),
    },
    /* Mutable — read/written directly by the other chat/*.js modules
       (window.HirisChatState.turnCount = ...), same shared-state shape
       the single inline <script> used to have as bare `var`s. */
    hasMessages: false,
    /* Tetto e contatore di turni per l'UNICA conversazione (Task 3): prima
       erano mappe indicizzate per agentId, con un id solo dentro. `maxChatTurns`
       viene da `GET /api/impostazioni-chat` (chat/agents.js::loadSettings). */
    maxChatTurns: 0,
    turnCount: 0,
    isLoading: false,
  };
})();
