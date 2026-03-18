function getSystemTheme(){return window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
function applyTheme(t){document.documentElement.setAttribute('data-theme',t==='system'?getSystemTheme():t);}
function themeIcon(t){return t==='dark'?'☀️':t==='light'?'🌙':'🔄';}
function toggleTheme(btn){
  const themes=['dark','light','system'];
  const cur=localStorage.getItem('theme')||'dark';
  const next=themes[(themes.indexOf(cur)+1)%3];
  localStorage.setItem('theme',next);
  applyTheme(next);
  btn.textContent=themeIcon(next);
}
(function(){
  const t=localStorage.getItem('theme')||'dark';
  applyTheme(t);
  document.addEventListener('DOMContentLoaded',function(){
    const btn=document.getElementById('theme-btn')||document.querySelector('[data-theme-toggle]');
    if(btn)btn.textContent=themeIcon(t);
    document.querySelectorAll('[data-theme-toggle]').forEach(function(toggle){
      toggle.addEventListener('click',function(){toggleTheme(toggle);});
    });
    document.querySelectorAll('[data-confirm]').forEach(function(link){
      link.addEventListener('click',function(event){
        if(!window.confirm(link.dataset.confirm)){event.preventDefault();}
      });
    });
    if(t==='system'){window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>applyTheme('system'));}
  });
})();
