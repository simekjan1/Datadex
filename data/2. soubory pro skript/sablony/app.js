(() => {
  "use strict";
  const root = document.documentElement;
  const dbId = root.dataset.dbId;
  const status = document.getElementById("globalni-stav");
  let db = null;
  let dbPromise;
  const announce = (text, error=false) => { if (!status) return; status.hidden=false; status.textContent=text; status.classList.toggle("chyba",error); };
  const openDb = () => {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise((resolve,reject) => {
      if (!("indexedDB" in window)) return reject(new Error("IndexedDB není dostupná."));
      const req = indexedDB.open("znalostni-preference",1);
      req.onupgradeneeded = () => { if (!req.result.objectStoreNames.contains("prefs")) req.result.createObjectStore("prefs"); };
      req.onsuccess = () => { db=req.result; resolve(db); };
      req.onerror = () => reject(req.error || new Error("IndexedDB nelze otevřít."));
    }).catch(err => { announce("Nastavení prohlížeče se nebude ukládat: "+err.message,true); return null; });
    return dbPromise;
  };
  const key = name => `${dbId}:${name}`;
  async function getPref(name, fallback=null) { const d=await openDb(); if(!d) return fallback; return new Promise(resolve=>{const r=d.transaction("prefs","readonly").objectStore("prefs").get(key(name)); r.onsuccess=()=>resolve(r.result===undefined?fallback:r.result); r.onerror=()=>resolve(fallback);}); }
  async function setPref(name,value) { const d=await openDb(); if(!d) return; return new Promise((resolve,reject)=>{const t=d.transaction("prefs","readwrite"); t.objectStore("prefs").put(value,key(name)); t.oncomplete=resolve; t.onerror=()=>reject(t.error);}); }

  async function themes() {
    const select=document.getElementById("volba-motivu"); if(!select) return;
    const saved=await getPref("theme","auto"); select.value=["auto","light","dark"].includes(saved)?saved:"auto";
    const apply=v=>{ if(v==="auto") root.removeAttribute("data-theme"); else root.dataset.theme=v; };
    apply(select.value); select.addEventListener("change",()=>{apply(select.value); setPref("theme",select.value);});
  }
  async function rememberedDetails() {
    for (const el of document.querySelectorAll("details[data-pref]")) {
      el.open=await getPref("detail:"+el.dataset.pref,false);
      el.addEventListener("toggle",()=>setPref("detail:"+el.dataset.pref,el.open));
    }
    const navPath=document.querySelector('meta[name="current-nav-path"]')?.content;
    if(new URLSearchParams(location.search).has("q")&&navPath){for(const id of navPath.split(",").filter(Boolean)){const el=document.querySelector(`details[data-pref="nav:${CSS.escape(id)}"]`);if(el)el.open=true;}}
  }

  async function exportPrefs() {
    const d=await openDb(); if(!d) return;
    const values={};
    await new Promise((resolve,reject)=>{const r=d.transaction("prefs","readonly").objectStore("prefs").openCursor(); r.onsuccess=()=>{const c=r.result;if(!c)return resolve();if(String(c.key).startsWith(dbId+":")) values[String(c.key).slice(dbId.length+1)]=c.value;c.continue();};r.onerror=()=>reject(r.error);});
    const blob=new Blob([JSON.stringify({format:"znalostni-preference",version:1,databaseId:dbId,preferences:values},null,2)],{type:"application/json"});
    const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`preference-${dbId}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);announce("Preference byly připraveny ke stažení.");
  }
  async function importPrefs(file) {
    if(file.size>5*1024*1024)return announce("Import selhal: soubor je větší než povolených 5 MB.",true);
    let data; try { data=JSON.parse(await file.text()); } catch(e){return announce("Import selhal: soubor není platný JSON.",true);}
    if(!data||data.format!=="znalostni-preference"||data.version!==1||typeof data.databaseId!=="string"||!data.preferences||Array.isArray(data.preferences)||typeof data.preferences!=="object") return announce("Import selhal: nepodporovaný nebo neúplný formát.",true);
    const validValue=(value,depth=0)=>{if(depth>12)return false;if(value===null||typeof value==="string"||typeof value==="boolean"||(typeof value==="number"&&Number.isFinite(value)))return true;if(Array.isArray(value))return value.length<=1000&&value.every(v=>validValue(v,depth+1));if(typeof value==="object")return Object.keys(value).length<=1000&&Object.entries(value).every(([k,v])=>k.length<=200&&validValue(v,depth+1));return false;};
    if(!Object.entries(data.preferences).every(([k,v])=>typeof k==="string"&&k.length>0&&k.length<=300&&validValue(v)))return announce("Import selhal: preference obsahují neplatný klíč, typ nebo příliš hluboká data.",true);
    if(data.databaseId!==dbId && !confirm("Soubor pochází z jiné databáze. Opravdu chcete její preference použít v této databázi?")) return announce("Import byl zrušen.");
    if(!confirm("Import nahradí všechny preference této databáze. Pokračovat?")) return announce("Import byl zrušen.");
    const d=await openDb(); if(!d)return;
    try { await new Promise((resolve,reject)=>{const t=d.transaction("prefs","readwrite"),s=t.objectStore("prefs"),r=s.openCursor();r.onsuccess=()=>{const c=r.result;if(!c){for(const [k,v] of Object.entries(data.preferences))s.put(v,key(k));return;}if(String(c.key).startsWith(dbId+":"))c.delete();c.continue();};t.oncomplete=resolve;t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error);}); announce("Preference byly bezpečně importovány. Pro jejich úplné použití obnovte stránku."); } catch(e){ announce("Import selhal a původní preference zůstaly zachovány: "+e.message,true); }
  }
  const exportBtn=document.getElementById("export-preferenci"), importBtn=document.getElementById("import-preferenci"), fileInput=document.getElementById("soubor-preferenci");
  exportBtn?.addEventListener("click",exportPrefs); importBtn?.addEventListener("click",()=>fileInput?.click()); fileInput?.addEventListener("change",()=>{if(fileInput.files[0])importPrefs(fileInput.files[0]);fileInput.value="";});

  async function documentModes() {
    const article=document.querySelector("article[data-document-id]"); if(!article)return;
    const id=article.dataset.documentId, select=document.getElementById("rezim-dokumentu"), toggles=[...article.querySelectorAll(".kapitola-prepinac")];
    if(select){const mode=await getPref(`doc:${id}:mode`,"full");select.value=mode;article.classList.toggle("režim-kapitoly",mode==="chapters");select.addEventListener("change",()=>{article.classList.toggle("režim-kapitoly",select.value==="chapters");setPref(`doc:${id}:mode`,select.value);});}
    for(const b of toggles){b.hidden=false;const section=b.closest(".kapitola"),sid=section.dataset.sectionId;const opened=await getPref(`doc:${id}:section:${sid}`,false);section.dataset.open=String(opened);b.setAttribute("aria-expanded",String(opened));b.addEventListener("click",()=>{const next=section.dataset.open!=="true";section.dataset.open=String(next);b.setAttribute("aria-expanded",String(next));b.textContent=next?"Sbalit kapitolu":"Rozbalit kapitolu";setPref(`doc:${id}:section:${sid}`,next);});b.textContent=opened?"Sbalit kapitolu":"Rozbalit kapitolu";}
  }

  let speaking={chunks:[],index:0,active:false,paused:false,token:0};
  function speechControls(){const box=document.querySelector(".cteni-ovladani");if(!box)return;const voice=box.querySelector("#hlas"),rate=box.querySelector("#rychlost"),s=document.getElementById("stav-cteni");if(!("speechSynthesis"in window)){box.querySelectorAll("button,select,input").forEach(x=>x.disabled=true);s.textContent="Hlasové čtení není v tomto prohlížeči dostupné.";return;}
    const loadVoices=async()=>{const saved=await getPref("speech:voice","");const voices=speechSynthesis.getVoices();voice.innerHTML='<option value="">Výchozí hlas prohlížeče</option>';voices.forEach(v=>{const o=document.createElement("option");o.value=v.name;o.textContent=`${v.name} (${v.lang})`;voice.append(o);});if(saved&&voices.some(v=>v.name===saved))voice.value=saved;else if(saved){voice.value="";s.textContent="Dříve zvolený hlas není dostupný; používá se výchozí hlas.";}};loadVoices();speechSynthesis.addEventListener?.("voiceschanged",loadVoices);getPref("speech:rate",1).then(v=>{rate.value=String(Math.min(2,Math.max(.5,Number(v)||1)));});
    const chunkNodes=rootNode=>[...rootNode.querySelectorAll("h1,h2,h3,h4,h5,h6,p,li,th,td")].map(n=>n.textContent.trim()).filter(Boolean);
    const stop=()=>{speaking.token++;speechSynthesis.cancel();speaking.active=false;speaking.paused=false;s.textContent="Čtení je zastaveno.";};
    const speakCurrent=()=>{if(!speaking.active||speaking.index>=speaking.chunks.length){speaking.active=false;s.textContent="Čtení bylo dokončeno.";return;}const token=speaking.token,u=new SpeechSynthesisUtterance(speaking.chunks[speaking.index]);u.rate=Number(rate.value);const found=speechSynthesis.getVoices().find(v=>v.name===voice.value);if(found)u.voice=found;u.onend=()=>{if(speaking.token===token&&speaking.active&&!speaking.paused){speaking.index++;speakCurrent();}};u.onerror=e=>{if(speaking.token===token&&e.error!=="canceled"&&e.error!=="interrupted"){speaking.active=false;s.textContent="Hlasové čtení selhalo: "+e.error;}};speechSynthesis.speak(u);};
    const start=node=>{const token=speaking.token+1;speechSynthesis.cancel();speaking={chunks:chunkNodes(node),index:0,active:true,paused:false,token};s.textContent="Probíhá hlasové čtení.";speakCurrent();};
    box.querySelector("#precist-dokument").addEventListener("click",()=>start(document.querySelector(".obsah-dokumentu")));
    document.querySelectorAll(".precist-kapitolu").forEach(b=>b.addEventListener("click",()=>start(document.getElementById(b.dataset.target))));
    box.querySelector("#pozastavit-cteni").addEventListener("click",()=>{if(speaking.active&&!speechSynthesis.paused){speechSynthesis.pause();speaking.paused=true;s.textContent="Čtení je pozastaveno.";}});
    box.querySelector("#obnovit-cteni").addEventListener("click",()=>{if(speaking.active&&speechSynthesis.paused){speaking.paused=false;speechSynthesis.resume();s.textContent="Čtení pokračuje.";}});
    box.querySelector("#zastavit-cteni").addEventListener("click",stop);
    voice.addEventListener("change",()=>{setPref("speech:voice",voice.value);if(speaking.active){speaking.token++;speechSynthesis.cancel();speaking.paused=false;speakCurrent();}});
    rate.addEventListener("change",()=>setPref("speech:rate",Number(rate.value)));
    window.addEventListener("pagehide",()=>speechSynthesis.cancel());
  }

  function lightbox(){const dialog=document.getElementById("lightbox");if(!dialog||typeof dialog.showModal!=="function")return;const img=document.getElementById("lightbox-obrazek"),caption=document.getElementById("lightbox-popis"),count=document.getElementById("lightbox-poradi"),wrap=document.getElementById("lightbox-obrazek-obal");let group=[],index=0,origin=null,scale=1;
    const reset=()=>{scale=1;img.style.transform="scale(1)";wrap.scrollTop=wrap.scrollLeft=0;};const show=i=>{index=(i+group.length)%group.length;const b=group[index];img.src=b.dataset.full;img.alt=b.dataset.alt;caption.textContent=b.dataset.alt;count.textContent=`Obrázek ${index+1} z ${group.length}`;reset();};
    document.querySelectorAll(".nahled").forEach(b=>b.addEventListener("click",()=>{origin=b;group=[...document.querySelectorAll(`.nahled[data-gallery="${CSS.escape(b.dataset.gallery)}"]`)];index=group.indexOf(b);show(index);dialog.showModal();document.body.classList.add("modal-otevren");document.getElementById("lightbox-zavrit").focus();}));
    const close=()=>dialog.close();document.getElementById("lightbox-zavrit").addEventListener("click",close);document.getElementById("lightbox-predchozi").addEventListener("click",()=>show(index-1));document.getElementById("lightbox-dalsi").addEventListener("click",()=>show(index+1));document.getElementById("lightbox-priblizit").addEventListener("click",()=>{scale=Math.min(4,scale+.25);img.style.transform=`scale(${scale})`;});document.getElementById("lightbox-oddalit").addEventListener("click",()=>{scale=Math.max(.5,scale-.25);img.style.transform=`scale(${scale})`;});document.getElementById("lightbox-obnovit").addEventListener("click",reset);
    dialog.addEventListener("close",()=>{document.body.classList.remove("modal-otevren");img.src="";origin?.focus();});dialog.addEventListener("keydown",e=>{if(e.key==="ArrowLeft"){e.preventDefault();show(index-1);}if(e.key==="ArrowRight"){e.preventDefault();show(index+1);}if(e.key==="Tab"){const f=[...dialog.querySelectorAll("button:not([disabled])")];const first=f[0],last=f.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});dialog.addEventListener("wheel",e=>{if(e.ctrlKey)return;e.preventDefault();show(index+(e.deltaY>0?1:-1));},{passive:false});
  }

  function highlights(){const p=new URLSearchParams(location.search),q=p.get("q");if(!q)return;const article=document.querySelector(".obsah-dokumentu");if(!article)return;const terms=q.trim().split(/\s+/).filter(Boolean);if(!terms.length)return;const fold=s=>s.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLocaleLowerCase("cs");const walker=document.createTreeWalker(article,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest("script,style,button,select")?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);for(const node of nodes){const original=node.nodeValue,f=fold(original);let ranges=[];for(const term of terms){let start=0,t=fold(term),idx;while(t&&(idx=f.indexOf(t,start))>=0){ranges.push([idx,idx+t.length]);start=idx+t.length;}}ranges.sort((a,b)=>a[0]-b[0]);if(!ranges.length)continue;const frag=document.createDocumentFragment();let pos=0;for(const [a,b]of ranges){if(a<pos)continue;frag.append(original.slice(pos,a));const m=document.createElement("mark");m.textContent=original.slice(a,b);frag.append(m);pos=b;}frag.append(original.slice(pos));node.replaceWith(frag);}const marks=[...article.querySelectorAll("mark")];if(!marks.length)return;const panel=document.getElementById("nalezy");panel.hidden=false;let i=0;const go=n=>{marks[i]?.classList.remove("aktivni");i=(n+marks.length)%marks.length;const m=marks[i];m.classList.add("aktivni");m.tabIndex=-1;const section=m.closest(".kapitola");if(section){section.dataset.open="true";const b=section.querySelector(".kapitola-prepinac");b?.setAttribute("aria-expanded","true");}m.focus({preventScroll:true});m.scrollIntoView({block:"center"});panel.querySelector("output").textContent=`Výskyt ${i+1} z ${marks.length}`;};panel.querySelector(".predchozi-nalez").addEventListener("click",()=>go(i-1));panel.querySelector(".dalsi-nalez").addEventListener("click",()=>go(i+1));go(0);}

  document.querySelectorAll(".na-zacatek").forEach(b=>b.addEventListener("click",()=>{document.getElementById("app-zacatek").scrollIntoView();document.querySelector(".preskocit")?.focus();}));
  themes(); rememberedDetails(); documentModes().then(highlights); speechControls(); lightbox(); openDb();
})();
