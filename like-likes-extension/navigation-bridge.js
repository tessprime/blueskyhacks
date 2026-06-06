// Runs in the page's main world so we can patch the real history API.
// Dispatches 'ltl:navigate' on window whenever the URL changes via the History API.
for (const method of ['pushState', 'replaceState']) {
  const orig = history[method].bind(history);
  history[method] = (...args) => {
    orig(...args);
    window.dispatchEvent(new CustomEvent('ltl:navigate'));
  };
}
