/* HIRIS · Designer · bootstrap
   Last script loaded. Wires up the page after all modules have defined their globals. */

applyTheme();
populateTemplateSelector();
loadModels();
loadAgents();
loadUsage();
setInterval(loadUsage, 30000);
loadProposals('pending');
