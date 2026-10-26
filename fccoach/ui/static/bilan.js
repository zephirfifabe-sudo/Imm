// Rendu commun d'un bilan (mi-temps / fin de match / clip). `fileUrl(rel)` donne l'URL d'un fichier.
function esc(t) { const d = document.createElement("div"); d.textContent = t ?? ""; return d.innerHTML; }
const CTX = { attaque: "Attaque", defense: "Défense", relance: "Relance", perte: "Perte de balle", adversaire: "Adversaire" };
const STAT_LABEL = {
  passes_me: "Passes (moi)", passes_opp: "Passes (adv)", pertes: "Ballons perdus", recuperations: "Ballons récupérés",
  tirs_me: "Tirs (moi)", tirs_opp: "Tirs (adv)", corners_me: "Corners (moi)", corners_opp: "Corners (adv)",
  conduites_me: "Conduites (moi)", conduites_opp: "Conduites (adv)", pressings_subis: "Pressings subis",
  changements_joueur_me: "Changements de joueur (moi)", changements_joueur_opp: "Changements de joueur (adv)",
  buts_me: "Buts (moi)", buts_opp: "Buts (adv)", opp_reaction_delay_mean_s: "Délai de réaction adverse moyen (s)",
};
function renderBilan(b, fileUrl, onClip) {
  if (!b) return `<div class="muted">Bilan pas encore disponible.</div>`;
  const st = b.stats || {};
  const poss = st.possession_pct ? `${st.possession_pct.me} % / ${st.possession_pct.opp} %` : "–";
  const stats = [`<div class="row"><span>Possession (moi / adv)</span><span>${poss}</span></div>`]
    .concat(Object.entries(STAT_LABEL).filter(([k]) => st[k] != null).map(([k, l]) => `<div class="row"><span>${l}</span><span>${st[k]}</span></div>`)).join("");
  const f = b.formations || {};
  const form = (x) => x && x.name ? `${x.name} (${Math.round(x.confidence * 100)} %)${x.confidence < 0.7 ? " — incertaine" : ""}` : "–";
  const opp = b.opponent || {};
  const habits = (opp.habits || []).map(h => `<div class="row"><span>${esc(h.label)}</span><span>${h.count}× · ${h.status}${h.known_before ? " · déjà vu" : ""}</span></div>`).join("")
    || `<div class="muted">Aucune habitude repérée.</div>`;
  const rules = (b.rules || []).map(r => `
    <div class="rule">
      <div class="t">${esc(r.conseil)}${r.bouton ? ` <span class="muted">(bouton suggéré : ${esc(r.bouton)})</span>` : ""}</div>
      <div class="muted" style="font-size:13px">Fiche ${r.source} « ${esc(r.fiche)} » · ${CTX[r.contexte] || r.contexte} · ${r.count}×</div>
      <div class="muted" style="font-size:13px">Situation : ${esc(r.situation)}</div>
      <div>${r.moments.map(m => m.clip
        ? `<span class="chip"><a href="#" data-clip="${esc(fileUrl(m.clip))}">▶ ${m.clock || (m.t + " s")}</a></span>`
        : `<span class="chip">${m.clock || (m.t + " s")}</span>`).join("")}</div>
    </div>`).join("") || `<div class="muted">Aucune règle déclenchée : rien à signaler (ou terrain non calibré).</div>`;
  const heat = Object.entries(b.heatmaps || {}).filter(([k]) => !k.includes("_h")).map(([k, rel]) =>
    `<img class="full" style="margin-bottom:8px" src="${fileUrl(rel)}" alt="Heatmap ${esc(k)}">`).join("");
  const score = b.score && b.score.me != null ? `${b.score.me} - ${b.score.opp}` : (b.score && b.score.raw ? b.score.raw.join(" - ") + " (domicile - ext.)" : "–");
  return `
    <div class="panel"><h2>Ce que j'aurais dû faire</h2>${rules}</div>
    <div class="panel"><h2>Match</h2>
      <div class="row"><span>Score (moi - adv)</span><span>${score}</span></div>
      <div class="row"><span>Ma formation</span><span>${form(f.me)}</span></div>
      <div class="row"><span>Formation adverse</span><span>${form(f.opp)}</span></div>
      <div class="row"><span>Hauteur de ligne adverse</span><span>${opp.line_height ?? "–"}</span></div>
      ${stats}</div>
    <div class="panel"><h2>Adversaire${opp.pseudo ? " — " + esc(opp.pseudo) : ""}</h2>${habits}</div>
    ${heat ? `<div class="panel"><h2>Heatmaps</h2>${heat}</div>` : ""}`;
}
function bindClips(root, onClip) {
  for (const a of root.querySelectorAll("a[data-clip]")) a.addEventListener("click", (e) => { e.preventDefault(); onClip(a.dataset.clip); });
}
