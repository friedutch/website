(function(){
  var t=localStorage.getItem('theme')||'dark';
  var eff=t==='system'?(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):t;
  document.documentElement.setAttribute('data-theme',eff);
})();
