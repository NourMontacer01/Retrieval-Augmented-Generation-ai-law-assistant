// Version en ligne : la recherche tourne dans le navigateur, sans serveur.
//
// Meme logique que conformite/recherche.py : glossaire, texte nomme -> filtre, 30 candidats
// par similarite cosinus, considerants ponderes a 0,9, references explicites en tete,
// au plus 2 morceaux par article. Le modele est le meme (multilingual-e5-base, en ONNX) :
// les vecteurs de la question sont donc comparables a ceux calcules a l'indexation.
//
// Les appels de app.js a /api/... sont servis ici : l'interface est identique en local.

(() => {
  const TRANSFORMERS = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.2";
  const MODELE = "Xenova/multilingual-e5-base";
  const DIMENSION = 768;
  const MESSAGE_SYNTHESE =
    "Version en ligne : la recherche et le surlignage tournent dans votre navigateur. " +
    "La synthèse rédigée par un modèle de langue est disponible dans la version locale du projet.";

  // ---------- chargement ----------

  // float16 -> float32 (pas de Float16Array dans tous les navigateurs)
  function depuisFloat16(tampon) {
    const brut = new Uint16Array(tampon);
    const sortie = new Float32Array(brut.length);
    for (let i = 0; i < brut.length; i++) {
      const h = brut[i];
      const signe = h & 0x8000 ? -1 : 1;
      const exposant = (h >> 10) & 0x1f;
      const mantisse = h & 0x3ff;
      sortie[i] = exposant === 0
        ? signe * 2 ** -14 * (mantisse / 1024)
        : exposant === 31
          ? (mantisse ? NaN : signe * Infinity)
          : signe * 2 ** (exposant - 15) * (1 + mantisse / 1024);
    }
    return sortie;
  }

  async function telecharger(chemin, binaire) {
    const reponse = await fetchNatif(chemin);
    if (!reponse.ok) throw new Error(`${chemin} : ${reponse.status}`);
    return binaire ? depuisFloat16(await reponse.arrayBuffer()) : reponse.json();
  }

  const fetchNatif = window.fetch.bind(window);
  const etat = { morceaux: null, vecteurs: null, phrases: {}, reglages: null, extracteur: null };

  function afficherEtat(texte) {
    let ligne = document.getElementById("etat-moteur");
    if (!ligne) {
      ligne = document.createElement("p");
      ligne.id = "etat-moteur";
      ligne.className = "discret";
      document.getElementById("formulaire")?.after(ligne);
    }
    ligne.textContent = texte;
    const statut = document.getElementById("statut");
    if (statut && !statut.hidden && texte.startsWith("Chargement")) statut.textContent = texte;
  }

  async function chargerDonnees() {
    const [morceaux, vecteurs, positions, vecteursPhrases, reglages] = await Promise.all([
      telecharger("donnees/morceaux.json"),
      telecharger("donnees/vecteurs.bin", true),
      telecharger("donnees/phrases.json"),
      telecharger("donnees/phrases.bin", true),
      telecharger("donnees/reglages.json"),
    ]);
    // Les vecteurs des phrases sont ranges dans l'ordre de phrases.json
    let ligne = 0;
    for (const [id, pos] of Object.entries(positions)) {
      etat.phrases[id] = { positions: pos, debut: ligne };
      ligne += pos.length;
    }
    etat.vecteursPhrases = vecteursPhrases;
    etat.morceaux = morceaux;
    etat.vecteurs = vecteurs;
    etat.reglages = reglages;
    etat.rangDe = new Map(morceaux.map((m, i) => [m.id, i]));
  }

  async function chargerModele() {
    const { pipeline } = await import(TRANSFORMERS);
    const fichiers = {};
    etat.extracteur = await pipeline("feature-extraction", MODELE, {
      dtype: "q8",
      progress_callback: (p) => {
        if (p.status !== "progress" || !p.total) return;
        fichiers[p.file] = [p.loaded, p.total];
        const [lu, total] = Object.values(fichiers).reduce(([a, b], [c, d]) => [a + c, b + d], [0, 0]);
        afficherEtat(`Chargement du modèle de langue (première visite, ${Math.round(total / 1e6)} Mo) : ${Math.round(100 * lu / total)} %`);
      },
    });
  }

  afficherEtat("Chargement du modèle de langue…");
  const pret = Promise.all([chargerDonnees(), chargerModele()]).then(() => {
    afficherEtat("Modèle chargé : la recherche se fait dans votre navigateur, sans serveur.");
  });
  pret.catch((e) => afficherEtat(`Le chargement a échoué : ${e.message}. Recharger la page.`));

  // ---------- analyse de la question (glossaire.py) ----------

  const sansAccents = (t) => t.normalize("NFD").replace(/\p{Mn}/gu, "");
  const echapperRegex = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  function enrichir(question) {
    const q = sansAccents(question.toLowerCase());
    const ajouts = [];
    for (const [terme, traduction] of Object.entries(etat.reglages.glossaire)) {
      if (new RegExp(`\\b${echapperRegex(terme)}e?s?\\b`).test(q) && !ajouts.includes(traduction)) {
        ajouts.push(traduction);
      }
    }
    return ajouts.length ? `${question} (${ajouts.join("; ")})` : question;
  }

  function textesNommes(question) {
    const q = sansAccents(question.toLowerCase());
    const trouves = new Set();
    for (const [nom, source] of Object.entries(etat.reglages.noms_des_textes)) {
      if (new RegExp(`\\b${echapperRegex(nom)}\\b`).test(q)) trouves.add(source);
    }
    return trouves;
  }

  function referencesExplicites(question) {
    const q = sansAccents(question.toLowerCase());
    const refs = [];
    for (const m of q.matchAll(/\barticle\s+(\d+)(?:\s*(bis|ter))?\b/g)) {
      refs.push(["article", `${m[1]} ${m[2] || ""}`.trim()]);
    }
    for (const m of q.matchAll(/\bannexe\s+([ivxlc]+)\b/g)) refs.push(["annexe", m[1].toUpperCase()]);
    return refs;
  }

  // ---------- recherche (recherche.py) ----------

  const cacheVecteurs = new Map();

  async function vectoriser(texte) {
    if (cacheVecteurs.has(texte)) return cacheVecteurs.get(texte);
    const sortie = await etat.extracteur(`query: ${texte}`, { pooling: "mean", normalize: true });
    const vecteur = Float32Array.from(sortie.data);
    cacheVecteurs.set(texte, vecteur);
    return vecteur;
  }

  function produitScalaire(tableau, ligne, vecteur) {
    let s = 0;
    const debut = ligne * DIMENSION;
    for (let j = 0; j < DIMENSION; j++) s += tableau[debut + j] * vecteur[j];
    return s;
  }

  const correspond = (m, filtres) =>
    Object.entries(filtres).every(([champ, valeur]) => !valeur || m[champ] === valeur);

  async function rechercher(question, k, filtresDemandes) {
    const { candidats, max_par_unite: maxParUnite, poids_considerant: poidsConsiderant } = etat.reglages;
    const requete = enrichir(question);
    const vecteur = await vectoriser(requete);

    let filtres = { ...filtresDemandes };
    if (!filtres.source_id) {
      const nommes = textesNommes(question);
      if (nommes.size === 1) filtres.source_id = [...nommes][0];
    }

    // 1. Candidats par le sens : similarite cosinus avec tous les morceaux autorises
    const scores = [];
    etat.morceaux.forEach((m, i) => {
      if (correspond(m, filtres)) scores.push([i, produitScalaire(etat.vecteurs, i, vecteur)]);
    });
    scores.sort((a, b) => b[1] - a[1]);
    const cosinus = new Map(scores.map(([i, s]) => [i, s]));

    // 2. Rang -> score de fusion, 3. considerants ponderes
    const fusion = scores.slice(0, candidats).map(([i], rang) => {
      const poids = etat.morceaux[i].type_unite === "considerant" ? poidsConsiderant : 1;
      return [i, poids / (60 + rang)];
    });
    fusion.sort((a, b) => b[1] - a[1]);
    let classement = fusion.map(([i]) => i);

    // 4. References explicites en tete
    const cites = [];
    for (const [type, numero] of referencesExplicites(question)) {
      const trouves = [];
      etat.morceaux.forEach((m, i) => {
        if (correspond(m, { ...filtres, type_unite: type, numero })) trouves.push(i);
      });
      trouves.sort((a, b) => (etat.morceaux[a].ordre || 0) - (etat.morceaux[b].ordre || 0));
      cites.push(...trouves);
    }
    classement = [...cites, ...classement.filter((i) => !cites.includes(i))];

    // 5. Diversite
    const retenus = [];
    const parUnite = new Map();
    for (const i of classement) {
      const m = etat.morceaux[i];
      const unite = `${m.source_id}|${m.type_unite}|${m.numero}`;
      if ((parUnite.get(unite) || 0) >= maxParUnite) continue;
      parUnite.set(unite, (parUnite.get(unite) || 0) + 1);
      retenus.push(i);
      if (retenus.length === k) break;
    }

    return {
      requete,
      passages: retenus.map((i) => {
        const m = etat.morceaux[i];
        const score = cosinus.has(i) ? cosinus.get(i) : produitScalaire(etat.vecteurs, i, vecteur);
        return {
          id: m.id, texte: m.texte, reference: m.reference, nature: m.nature, autorite: m.autorite,
          source_id: m.source_id, type_unite: m.type_unite, numero: m.numero, url: m.url,
          score: Math.round(score * 1e4) / 1e4,
        };
      }),
    };
  }

  // ---------- surlignage (phrases.py) ----------

  async function surligner(requete, passages) {
    const vecteur = await vectoriser(requete);
    const resultat = {};
    for (const p of passages) {
      const phrases = etat.phrases[p.id];
      if (!phrases) { resultat[p.id] = null; continue; }
      let meilleur = 0, scoreMax = -Infinity;
      phrases.positions.forEach((_, j) => {
        const s = produitScalaire(etat.vecteursPhrases, phrases.debut + j, vecteur);
        if (s > scoreMax) { scoreMax = s; meilleur = j; }
      });
      const [debut, fin] = phrases.positions[meilleur];
      resultat[p.id] = { debut, fin };
    }
    return resultat;
  }

  // ---------- article entier (app.py, /api/unite) ----------

  function unite(source, type, numero) {
    const morceaux = etat.morceaux
      .filter((m) => m.source_id === source && m.type_unite === type && m.numero === numero)
      .sort((a, b) => (a.ordre || 0) - (b.ordre || 0));
    if (!morceaux.length) return null;
    const m = morceaux[0];
    return {
      source_titre: m.source_titre, type_unite: type, numero, titre_unite: m.titre_unite,
      chapitre: m.chapitre, section: m.section, nature: m.nature, version: m.version, url: m.url,
      texte: morceaux.map((x) => x.texte).join("\n"),
    };
  }

  // ---------- les routes de l'API, servies sur place ----------

  const json = (donnees, statut = 200) =>
    new Response(JSON.stringify(donnees), { status: statut, headers: { "Content-Type": "application/json" } });

  const dejaPosees = new Map();

  async function servir(chemin, options) {
    await pret;
    if (chemin.startsWith("/api/unite/")) {
      const [source, type, numero] = chemin.slice("/api/unite/".length).split("/").map(decodeURIComponent);
      const u = unite(source, type, numero);
      return u ? json(u) : json({ detail: "unite introuvable" }, 404);
    }

    const demande = JSON.parse(options?.body || "{}");
    const filtres = { source_id: demande.source_id || null, type_unite: demande.type_unite || null };
    const cle = JSON.stringify([demande.question.trim().toLowerCase(), filtres]);

    if (chemin === "/api/recherche") {
      const debut = performance.now();
      const depuisCache = dejaPosees.has(cle);
      if (!depuisCache) dejaPosees.set(cle, await rechercher(demande.question, demande.k || 5, filtres));
      return json({
        passages: dejaPosees.get(cle).passages,
        redaction: false,
        message: MESSAGE_SYNTHESE,
        duree_ms: Math.round(performance.now() - debut),
        cache: depuisCache,
      });
    }
    if (chemin === "/api/surlignage") {
      if (!dejaPosees.has(cle)) dejaPosees.set(cle, await rechercher(demande.question, demande.k || 5, filtres));
      const { requete, passages } = dejaPosees.get(cle);
      return json(await surligner(requete, passages));
    }
    return json({ detail: "pas de redaction dans la version en ligne" }, 404);
  }

  window.fetch = (ressource, options) => {
    const chemin = typeof ressource === "string" ? ressource : ressource.url;
    return chemin.startsWith("/api/") ? servir(chemin, options) : fetchNatif(ressource, options);
  };
})();
