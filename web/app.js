// Logique de la page : envoyer la question, afficher la synthese et les passages,
// ouvrir l'article complet dans le lecteur.

const $ = (id) => document.getElementById(id);

const NATURES = {
  contraignant: "Obligation légale",
  recommandation: "Recommandation",
  ethique: "Cadre éthique",
};

const TYPES = { article: "Art.", annexe: "Annexe", considerant: "Consid." };

const SOURCES = { rgpd: "RGPD", "ai-act": "AI Act", eprivacy: "ePrivacy", "data-act": "Data Act" };

// Le texte vient de la base et du modele : on l'echappe toujours avant de l'inserer
function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function enParagraphes(texte) {
  return texte
    .split(/\n+/)
    .filter((l) => l.trim())
    .map((l) => `<p>${echapper(l)}</p>`)
    .join("");
}

// Texte en paragraphes, avec la zone [debut, fin) surlignee au feutre.
// Si la zone traverse un retour a la ligne, le surlignage est ferme puis rouvert
// de part et d'autre, pour garder un HTML valide.
function avecSurlignage(texte, debut, fin) {
  if (debut == null) return enParagraphes(texte);
  const morceaux = [
    [texte.slice(0, debut), false],
    [texte.slice(debut, fin), true],
    [texte.slice(fin), false],
  ];
  const html = morceaux.map(([t, surligne]) => {
    const e = echapper(t).replace(/\n+/g, surligne ? "</mark></p><p><mark>" : "</p><p>");
    return surligne ? `<mark>${e}</mark>` : e;
  }).join("");
  return `<p>${html}</p>`.replace(/<mark>\s*<\/mark>/g, "").replace(/<p>\s*<\/p>/g, "");
}

// Extrait d'environ 700 caracteres centre sur la phrase surlignee
function extraitSurligne(p) {
  const s = p.surlignage;
  const texte = p.texte;
  if (texte.length <= 700) return avecSurlignage(texte, s?.debut, s?.fin);
  const debut = s ? Math.max(0, s.debut - 200) : 0;
  const fin = Math.min(texte.length, Math.max(debut + 700, s ? s.fin + 100 : 0));
  const avant = debut > 0 ? "… " : "";
  const apres = fin < texte.length ? " …" : "";
  const morceau = avant + texte.slice(debut, fin) + apres;
  return s
    ? avecSurlignage(morceau, s.debut - debut + avant.length, s.fin - debut + avant.length)
    : enParagraphes(morceau);
}

// Les renvois [1], [2] de la synthese deviennent des liens vers les passages
function avecRenvois(html, nbSources) {
  return html.replace(/\[(\d{1,2})\]/g, (tout, n) =>
    Number(n) >= 1 && Number(n) <= nbSources
      ? `<a class="appel" href="#source-${n}">${n}</a>`
      : tout
  );
}

function valeurCochee(nom) {
  return document.querySelector(`input[name="${nom}"]:checked`).value;
}

function statut(message) {
  $("statut").hidden = !message;
  $("statut").textContent = message || "";
}

async function consulter(evenement) {
  evenement.preventDefault();
  const question = $("question").value.trim();
  if (question.length < 3) return;

  $("bouton").disabled = true;
  $("resultats").hidden = true;
  statut("Recherche dans les textes…");

  const corps = JSON.stringify({
    question,
    source_id: valeurCochee("source"),
    type_unite: valeurCochee("unite"),
  });
  const consultation = ++numeroConsultation;

  try {
    // 1. Les passages : calcul local, ils s'affichent tout de suite
    const reponse = await fetch("/api/recherche", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: corps,
    });
    if (!reponse.ok) throw new Error(`erreur ${reponse.status}`);
    const donnees = await reponse.json();
    if (!afficher(donnees)) return;
    statut("");

    // 2. En parallele : le surlignage (calcul local) et la synthese (redigee a distance,
    //    affichee au fil de l'eau). Aucun des deux ne bloque l'autre.
    await Promise.all([
      surligner(corps, donnees.passages, consultation),
      donnees.redaction ? rediger(corps, donnees.passages.length, consultation) : null,
    ]);
  } catch (erreur) {
    statut(`La consultation a échoué (${erreur.message}). Le serveur est-il lancé ?`);
  } finally {
    $("bouton").disabled = false;
  }
}

// Si une nouvelle question part pendant qu'une synthese s'ecrit, l'ancienne s'arrete
let numeroConsultation = 0;

async function surligner(corps, passages, consultation) {
  if (passages.every((p) => p.surlignage)) return;     // deja surlignes (question en cache)
  const reponse = await fetch("/api/surlignage", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: corps,
  });
  if (!reponse.ok || consultation !== numeroConsultation) return;
  const positions = await reponse.json();
  passages.forEach((p, i) => {
    p.surlignage = positions[p.id];
    const extrait = document.querySelector(`#source-${i + 1} .extrait`);
    if (extrait && p.surlignage) extrait.innerHTML = extraitSurligne(p);
  });
}

async function rediger(corps, nbSources, consultation) {
  $("fournisseur").textContent = "rédaction en cours…";
  const reponse = await fetch("/api/synthese", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: corps,
  });
  if (!reponse.ok || !reponse.body) {
    $("texte-synthese").innerHTML = "<p><em>La synthèse n'a pas pu être rédigée ; les passages restent consultables.</em></p>";
    $("fournisseur").textContent = "";
    return;
  }

  const lecteur = reponse.body.getReader();
  const decodeur = new TextDecoder();
  let texte = "";
  for (;;) {
    const { done, value } = await lecteur.read();
    if (done || consultation !== numeroConsultation) break;
    texte += decodeur.decode(value, { stream: true });
    $("texte-synthese").innerHTML = avecRenvois(enParagraphes(texte), nbSources);
  }
  if (consultation === numeroConsultation) {
    $("fournisseur").textContent = "rédigée à partir des seuls passages ci-dessous";
  }
}

function afficher(donnees) {
  const passages = donnees.passages || [];

  if (!passages.length) {
    statut("Aucun passage ne correspond à ces critères.");
    return false;
  }

  const duree = donnees.cache ? "déjà consultée" : `${donnees.duree_ms} ms`;
  $("duree").textContent = `${passages.length} passages · ${duree}`;

  if (donnees.redaction) {
    $("texte-synthese").innerHTML = "";
  } else {
    $("texte-synthese").innerHTML =
      "<p><em>Aucune clé d'API n'est configurée : pas de synthèse, seulement les passages les plus proches de la question.</em></p>";
    $("fournisseur").textContent = "";
  }

  passagesAffiches = passages;
  $("liste-sources").innerHTML = passages.map((p, i) => {
    return `
      <li class="source" id="source-${i + 1}">
        <div class="marge">
          <span class="rang">[${i + 1}]</span>
          <span class="type">${echapper(TYPES[p.type_unite] || p.type_unite)}</span>
          <span class="numero">${echapper(p.numero)}</span>
        </div>
        <div>
          <div class="source-tete">
            <span class="source-ref">${echapper(SOURCES[p.source_id] || p.source_id)}</span>
            <span class="nature nature-${echapper(p.nature)}">${echapper(NATURES[p.nature] || p.nature)}</span>
          </div>
          <p class="discret">${echapper(p.reference)}</p>
          <div class="extrait">${extraitSurligne(p)}</div>
          <p class="source-pied">
            proximité ${p.score.toFixed(2)} &middot;
            <button type="button" data-rang="${i}" data-source="${echapper(p.source_id)}" data-type="${echapper(p.type_unite)}" data-numero="${echapper(p.numero)}">lire en entier</button>
          </p>
        </div>
      </li>`;
  }).join("");

  $("resultats").hidden = false;
  $("resultats").scrollIntoView({ behavior: "smooth", block: "start" });
  return true;
}

let passagesAffiches = [];

async function ouvrirUnite(source, type, numero, passage) {
  const reponse = await fetch(`/api/unite/${encodeURIComponent(source)}/${encodeURIComponent(type)}/${encodeURIComponent(numero)}`);
  if (!reponse.ok) return;
  const u = await reponse.json();

  const libelle = { article: "Article", annexe: "Annexe", considerant: "Considérant" }[u.type_unite];
  $("lecteur-source").textContent = u.source_titre;
  $("lecteur-chapitre").textContent = [u.chapitre, u.section].filter(Boolean).join(" — ");
  $("lecteur-titre").textContent = `${libelle} ${u.numero}`;
  $("lecteur-sous-titre").textContent = u.titre_unite || "";
  // Le passage retenu est un morceau de l'article : on retrouve sa place dans le texte
  // entier pour y reporter le surlignage
  const base = passage?.surlignage ? u.texte.indexOf(passage.texte) : -1;
  $("lecteur-texte").innerHTML = base >= 0
    ? avecSurlignage(u.texte, base + passage.surlignage.debut, base + passage.surlignage.fin)
    : enParagraphes(u.texte);
  $("lecteur-version").textContent = `${NATURES[u.nature] || u.nature} · ${u.version}`;
  $("lecteur-lien").href = u.url;

  $("lecteur").classList.add("ouvert");
  $("lecteur").setAttribute("aria-hidden", "false");
  $("lecteur").querySelector(".lecteur-page").scrollTop = 0;
  $("lecteur-texte").querySelector("mark")?.scrollIntoView({ block: "center" });
}

function fermerLecteur() {
  $("lecteur").classList.remove("ouvert");
  $("lecteur").setAttribute("aria-hidden", "true");
}

// ---- Branchements ----

$("date-du-jour").textContent = new Date().toLocaleDateString("fr-FR", {
  day: "numeric", month: "long", year: "numeric",
});

$("formulaire").addEventListener("submit", consulter);

// Entree envoie, Maj+Entree passe a la ligne
$("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("formulaire").requestSubmit();
  }
});

document.querySelectorAll(".exemples a").forEach((lien) =>
  lien.addEventListener("click", (e) => {
    e.preventDefault();
    $("question").value = lien.dataset.q;
    $("formulaire").requestSubmit();
  })
);

$("liste-sources").addEventListener("click", (e) => {
  const bouton = e.target.closest("button[data-source]");
  if (bouton) {
    ouvrirUnite(bouton.dataset.source, bouton.dataset.type, bouton.dataset.numero,
      passagesAffiches[Number(bouton.dataset.rang)]);
  }
});

// Une question passee dans l'adresse (?q=...) est posee directement : lien partageable
const questionAdresse = new URLSearchParams(location.search).get("q");
if (questionAdresse) {
  $("question").value = questionAdresse;
  $("formulaire").requestSubmit();
}

$("fermer").addEventListener("click", fermerLecteur);
$("lecteur").addEventListener("click", (e) => { if (e.target === $("lecteur")) fermerLecteur(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") fermerLecteur(); });
