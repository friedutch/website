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
    const btn=document.getElementById('theme-btn')||document.querySelector('.theme-toggle');
    if(btn)btn.textContent=themeIcon(t);
    if(t==='system'){window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>applyTheme('system'));}
  });
})();
