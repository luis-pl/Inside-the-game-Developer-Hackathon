import { changedIds } from "./domain/workspace-feedback.ts";
import type { ReportChanges } from "./domain/workspace-feedback.ts";

export function documentHtml(
  html: string,
  dark: boolean,
  token: string,
  changes: ReportChanges | null,
) {
  const policy = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'">`;
  const theme = dark
    ? `<style>:root{--ink:#ebebeb;--muted:#aaa;--line:#353535;--paper:#181818;color-scheme:dark}body,header,main,footer,section.insight{background:#181818!important;color:#ebebeb!important}h1,h2,h3,dt,dd,p,summary{color:inherit}figure svg,.pitch{background:#242824!important}figcaption,.method,.palette-note{color:#aaa}a{color:#ccc}button,select{background:#292929;color:#eee;border-color:#555}pre{background:#242424;color:#ddd}.field-lines{stroke:#8b9c90}figure svg text:not(.jersey){fill:#ccc}.status{background:#2b3a2e;color:#d4e0d6}</style>`
    : "";
  const config = JSON.stringify({
    token,
    ids: changedIds(changes),
    parentOrigin: location.origin,
  }).replace(/</g, "\\u003c");
  const tableTheme = `<style>.team-breakdown td:not(:first-child),.team-breakdown th:not(:first-child){white-space:nowrap}${dark ? "thead,th{background:#292929!important;color:#ebebeb!important}" : ""}</style>`;
  // Puente limitado a foco/scroll dentro del documento aislado. Nunca recibe HTML,
  // URLs o credenciales, ni habilita allow-same-origin o acceso a la red.
  const bridge = `<style>.ig-updated{scroll-margin-top:22px}.ig-change-label{display:inline-flex;gap:6px;align-items:center;font:600 11px system-ui;padding:4px 8px;margin:0 0 12px;border:1px solid #888;border-radius:5px;color:inherit}.ig-focus{outline:2px solid #888;outline-offset:5px;transition:outline-color 180ms ease-out}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto!important}.ig-focus{transition:none}}</style><script>(function(){const cfg=${config};const reduce=matchMedia('(prefers-reduced-motion:reduce)');function ready(){for(const id of cfg.ids){const el=document.getElementById(id);if(!el)continue;el.classList.add('ig-updated');const label=document.createElement('span');label.className='ig-change-label';label.textContent='Actualizado';el.prepend(label);}parent.postMessage({type:'inside-game-ready',token:cfg.token},cfg.parentOrigin);}window.addEventListener('message',function(e){if(e.source!==parent||e.data?.token!==cfg.token||e.data.type!=='inside-game-focus')return;const target=e.data.target;let el;if(target==='analysis')el=document.querySelector('.analyst-note');else if(target==='title')el=document.querySelector('header');else if(target==='graphics')el=document.querySelector('section.insight');else el=cfg.ids.map(id=>document.getElementById(id)).find(Boolean)||document.querySelector('.analyst-note');if(!el)return;el.scrollIntoView({block:'start',behavior:reduce.matches?'instant':'smooth'});document.querySelectorAll('.ig-focus').forEach(n=>n.classList.remove('ig-focus'));el.classList.add('ig-focus');el.setAttribute('tabindex','-1');el.focus({preventScroll:true});});if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready,{once:true});else ready();})();</script>`;
  // El HTML exportado ya limita los scripts por hash. Conservamos esa política
  // y autorizamos sólo este puente con un nonce efímero, sin abrir la red.
  const securedHtml = html.replace(
    /<meta\b[^>]*http-equiv=["']Content-Security-Policy["'][^>]*>/gi,
    (meta) => {
      const node = new DOMParser()
        .parseFromString(meta, "text/html")
        .querySelector("meta");
      if (!node) return meta;
      const content = node.getAttribute("content") ?? "";
      node.setAttribute(
        "content",
        content.replace(/(script-src\s+[^;]+)/i, `$1 'nonce-${token}'`),
      );
      return node.outerHTML;
    },
  );
  return securedHtml
    .replace(/<head>/i, "<head>" + policy)
    .replace(
      "</head>",
      theme +
        tableTheme +
        bridge.replace("<script>", `<script nonce="${token}">`) +
        "</head>",
    );
}
