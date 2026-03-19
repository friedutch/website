(function(){
  function readCookie(name){
    var prefix = name + "=";
    var parts = document.cookie ? document.cookie.split(";") : [];
    for(var i = 0; i < parts.length; i += 1){
      var item = parts[i].trim();
      if(item.indexOf(prefix) === 0){ return decodeURIComponent(item.slice(prefix.length)); }
    }
    return null;
  }
  function writeCookie(name, value){
    document.cookie = name + "=" + encodeURIComponent(value) + "; path=/; max-age=31536000; SameSite=Lax";
  }
  function getStoredValue(key){
    try {
      var stored = window.localStorage.getItem(key);
      if(stored !== null){ return stored; }
    } catch (error) {
      // Fall back to cookies when localStorage is unavailable.
    }
    return readCookie("friedutch_" + key);
  }
  function setStoredValue(key, value){
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      // Fall back to cookies when localStorage is unavailable.
    }
    writeCookie("friedutch_" + key, value);
  }
  window.friedutchStorage = window.friedutchStorage || {
    get: getStoredValue,
    set: setStoredValue
  };
  var t = window.friedutchStorage.get("theme") || "dark";
  var eff = t === "system" ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : t;
  document.documentElement.setAttribute("data-theme", eff);
})();
