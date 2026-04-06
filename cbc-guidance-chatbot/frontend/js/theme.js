// Theme initialization - runs before page load to prevent flash
(function() {
  try {
    const stored = localStorage.getItem('uiTheme');
    const preferred = stored || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    if (preferred === 'dark') {
      document.documentElement.classList.add('theme-dark');
    }
  } catch(e) {}
})();
