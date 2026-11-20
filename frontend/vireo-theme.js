(()=>{
 const root=document.documentElement,button=document.querySelector('#theme-toggle'),icon=document.querySelector('#theme-icon');
 function setTheme(value){const theme=value==='light'?'light':'dark';root.dataset.theme=theme;try{localStorage.setItem('vireo_theme_v1',theme)}catch{}const light=theme==='light';icon.textContent=light?'☾':'☀';button.title=button.ariaLabel=light?'Chuyển sang giao diện tối':'Chuyển sang giao diện sáng';button.setAttribute('aria-pressed',String(light));}
 setTheme(root.dataset.theme);button.addEventListener('click',()=>setTheme(root.dataset.theme==='light'?'dark':'light'));
 const stage=document.querySelector('#auth-screen');
 // Start immediately on entry; pause only while the login screen is hidden.
 function sync(){stage.classList.toggle('motion-paused',stage.hidden);}
 new MutationObserver(sync).observe(stage,{attributes:true,attributeFilter:['hidden']});sync();
})();
