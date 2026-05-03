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
        if(stored !== null){ return stored; }
      } catch (error) {
        // Fall back to cookies when localStorage is unavailable.
      }
      const cookieValue = readCookie("friedutch_" + key);
      return cookieValue !== null ? cookieValue : null;
    },
    set: function(key, value){
      if(value === null || typeof value === 'undefined'){
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

function clamp(n,min,max){return Math.min(Math.max(n,min),max);}
function themeToIndex(theme){return theme==='light'?0:theme==='dark'?2:1;}
function indexToTheme(index){return index<=0?'light':index>=2?'dark':'system';}

function setTheme(theme){
  const storage=getStorage();
  storage.set('theme',theme);
  applyTheme(theme);
  updateThemeUI(theme);
}

function setSliderThumb(slider, index){
  const track=slider.querySelector('[data-theme-track]');
  const thumb=slider.querySelector('[data-theme-thumb]');
  if(!track||!thumb){return;}
  const pad=parseFloat(window.getComputedStyle(track).getPropertyValue('--landing-slider-pad'))||6;
  const maxLeft=track.clientWidth-thumb.clientWidth-(pad*2);
  const ratio=index/2;
  thumb.style.left=(pad + (maxLeft*ratio))+'px';
  track.setAttribute('aria-valuenow', String(index));
}

function updateThemeUI(theme){
  document.querySelectorAll('[data-theme-toggle]').forEach(function(toggle){
    toggle.textContent=themeButtonText(toggle, theme);
  });
  document.querySelectorAll('[data-theme-slider]').forEach(function(slider){
    setSliderThumb(slider, themeToIndex(theme));
    slider.dataset.themePosition=themeLabelText(theme);
    slider.querySelectorAll('[data-theme-current-label], [data-theme-thumb-label]').forEach(function(label){
      label.textContent=themeLabelText(theme);
    });
    const track=slider.querySelector('[data-theme-track]');
    if(track){ track.setAttribute('aria-valuetext', themeLabelText(theme)); }
  });
}

function toggleTheme(){
  const storage=getStorage();
  const themes=['system','light','dark'];
  const cur=storage.get('theme')||'system';
  const next=themes[(themes.indexOf(cur)+1)%3];
  setTheme(next);
}

(function(){
  const storage=getStorage();
  let t=storage.get('theme')||'system';
  applyTheme(t);
  const mediaQuery=window.matchMedia('(prefers-color-scheme: dark)');
  document.addEventListener('DOMContentLoaded',function(){
    updateThemeUI(t);
    document.querySelectorAll('[data-theme-toggle]').forEach(function(toggle){
      toggle.addEventListener('click',function(){toggleTheme();});
    });
    document.querySelectorAll('[data-theme-slider]').forEach(function(slider){
      const track=slider.querySelector('[data-theme-track]');
      const thumb=slider.querySelector('[data-theme-thumb]');
      if(!track||!thumb){return;}
      let dragging=false;
      let dragOffset=0;
      function themeFromPointer(clientX){
        const rect=track.getBoundingClientRect();
        const x=clamp(clientX-rect.left,0,rect.width);
        const zone=rect.width/3;
        const index=x<zone?0:x<(zone*2)?1:2;
        return indexToTheme(index);
      }
      function moveThumb(clientX){
        const rect=track.getBoundingClientRect();
        const pad=parseFloat(window.getComputedStyle(track).getPropertyValue('--landing-slider-pad'))||6;
        const maxLeft=rect.width-thumb.offsetWidth-(pad*2);
        const rawLeft=clientX-rect.left-dragOffset;
        const left=clamp(rawLeft,pad,pad+maxLeft);
        thumb.style.left=left+'px';
      }
      track.addEventListener('click',function(event){
        if(dragging){return;}
        setTheme(themeFromPointer(event.clientX));
      });
      thumb.addEventListener('pointerdown',function(event){
        dragging=true;
        track.classList.add('is-dragging');
        dragOffset=event.clientX-thumb.getBoundingClientRect().left;
        thumb.setPointerCapture(event.pointerId);
      });
      thumb.addEventListener('pointermove',function(event){
        if(!dragging){return;}
        moveThumb(event.clientX);
      });
      thumb.addEventListener('pointerup',function(event){
        if(!dragging){return;}
        dragging=false;
        track.classList.remove('is-dragging');
        setTheme(themeFromPointer(event.clientX));
      });
      thumb.addEventListener('pointercancel',function(){
        dragging=false;
        track.classList.remove('is-dragging');
        const current=storage.get('theme')||'system';
        updateThemeUI(current);
      });
      track.addEventListener('keydown',function(event){
        const current=storage.get('theme')||'system';
        const idx=themeToIndex(current);
        if(event.key==='ArrowLeft'){event.preventDefault(); setTheme(indexToTheme(clamp(idx-1,0,2)));}
        if(event.key==='ArrowRight'){event.preventDefault(); setTheme(indexToTheme(clamp(idx+1,0,2)));}
      });
    });
    document.querySelectorAll('[data-confirm]').forEach(function(link){
      link.addEventListener('click',function(event){
        if(!window.confirm(link.dataset.confirm)){event.preventDefault();}
      });
    });
    mediaQuery.addEventListener('change',function(){
      const cur=storage.get('theme')||'system';
      if(cur==='system'){applyTheme('system');}
    });
  });
})();
