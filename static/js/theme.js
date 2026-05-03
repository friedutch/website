function getStorage(){
  if(window.friedutchStorage){return window.friedutchStorage;}
  function readCookie(name){
    const prefix = name + "=";
    const parts = document.cookie ? document.cookie.split(";") : [];
    for(let i = 0; i < parts.length; i += 1){
      const item = parts[i].trim();
      if(item.indexOf(prefix) === 0){ return decodeURIComponent(item.slice(prefix.length)); }
    }
    return null;
  }
  function writeCookie(name, value){
    document.cookie = name + "=" + encodeURIComponent(value) + "; path=/; max-age=31536000; SameSite=Lax";
  }
  function clearCookie(name){
    document.cookie = name + "=; path=/; max-age=0; SameSite=Lax";
  }
  window.friedutchStorage = {
    get: function(key){
      try {
        const stored = window.localStorage.getItem(key);
        if(stored === 'dark' || stored === 'light'){ return stored; }
      } catch (error) {
        // Fall back to cookies when localStorage is unavailable.
      }
      const cookieValue = readCookie("friedutch_" + key);
      return cookieValue === 'dark' || cookieValue === 'light' ? cookieValue : null;
    },
    set: function(key, value){
      if(value !== 'dark' && value !== 'light'){
        try {
          window.localStorage.removeItem(key);
        } catch (error) {
          // Fall back to cookies when localStorage is unavailable.
        }
        clearCookie("friedutch_" + key);
        return;
      }
      try {
        window.localStorage.setItem(key, value);
      } catch (error) {
        // Fall back to cookies when localStorage is unavailable.
      }
      writeCookie("friedutch_" + key, value);
    }
  };
  return window.friedutchStorage;
}
function getSystemTheme(){return window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
function applyTheme(t){document.documentElement.setAttribute('data-theme',t==='system'?getSystemTheme():t);}
function themeIcon(t){return t==='dark'?'Dark':t==='light'?'Light':'System';}
function themeLabelText(t){return t==='system'?'system':t;}
function themeButtonText(btn, theme){
  const label = btn?.dataset?.themeLabel;
  const textOnly = btn?.dataset?.themeTextOnly === 'true';
  const icon = themeIcon(theme);
  if(label && textOnly){ return label + ': ' + themeLabelText(theme); }
  return label ? icon + ' ' + label : icon;
}
function toggleTheme(btn){
  const storage=getStorage();
  const themes=['light','dark','system'];
  const cur=storage.get('theme')||'light';
  const next=themes[(themes.indexOf(cur)+1)%3];
  storage.set('theme',next);
  applyTheme(next);
  btn.textContent=themeButtonText(btn, next);
}
(function(){
  const storage=getStorage();
  const t=storage.get('theme')||'light';
  applyTheme(t);
  document.addEventListener('DOMContentLoaded',function(){
    const btn=document.getElementById('theme-btn')||document.querySelector('[data-theme-toggle]');
    if(btn)btn.textContent=themeButtonText(btn, t);
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
