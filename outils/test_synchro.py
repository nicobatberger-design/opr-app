"""Parcours de test de la synchro OPR Chantier : un « téléphone » (format iPhone) et un « PC » dans le vrai Edge,
sur le vrai serveur Supabase. Espace de test effacé à la fin."""
import tempfile, base64, functools, http.server, json, os, socketserver, sys, threading, time
from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = None
OUT = os.path.join(tempfile.gettempdir(), "opr-chantier-captures")
os.makedirs(OUT, exist_ok=True)

class Silencieux(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def serveur():
    h = functools.partial(Silencieux, directory=REPO)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    s = socketserver.ThreadingTCPServer(("127.0.0.1", 0), h); s.daemon_threads = True
    global URL; URL = f"http://127.0.0.1:{s.server_address[1]}/index.html"
    threading.Thread(target=s.serve_forever, daemon=True).start(); return s

ok, ko, erreurs_console = [], [], []
def verif(cond, msg):
    (ok if cond else ko).append(msg); print(("OK     " if cond else "ÉCHEC  ") + msg, flush=True)

def jpeg(page, couleur, texte, w=900, h=600):
    b = page.evaluate("""([c,t,w,h])=>{const cv=document.createElement('canvas');cv.width=w;cv.height=h;const x=cv.getContext('2d');
      x.fillStyle=c;x.fillRect(0,0,w,h);for(let i=0;i<400;i++){x.fillStyle=`hsl(${i*7%360},70%,50%)`;x.fillRect((i*37)%w,(i*53)%h,24,24);}
      x.fillStyle='#fff';x.font='bold 70px sans-serif';x.fillText(t,40,140);return cv.toDataURL('image/jpeg',0.92).split(',')[1];}""", [couleur, texte, w, h])
    return {"name": "photo.jpg", "mimeType": "image/jpeg", "buffer": base64.b64decode(b)}

def dialogues(page, nom):
    def h(d):
        if d.type == "prompt": d.accept(d.default_value)
        else: d.accept()
    page.on("dialog", h)
    page.on("console", lambda m: m.type == "error" and erreurs_console.append(f"{nom}: {m.text}"))
    page.on("pageerror", lambda e: erreurs_console.append(f"{nom} (exception): {e}"))

def synchro(page):
    page.evaluate("()=>synchroniser()")
    return page.evaluate("()=>({err:syncEtat.erreur, att:enAttente(), ligne:document.querySelector('#syncLineT').textContent})")

def etat(page, nom):
    """Points du chantier « nom » tels que stockés sur l'appareil."""
    return page.evaluate("""async (nom)=>{ if(ch) await flush(); const s=idx.chantiers.find(x=>x.nom===nom); if(!s) return null;
      const c=cleanChantier(await IDB.get('ch:'+s.id));
      return {id:c.id, adresse:c.adresse, plans:c.plans.length, visites:c.suivi.visites.length,
        points:c.suivi.points.map(p=>({id:p.id,num:p.num,desc:p.desc,photos:p.photos.length,ph0:p.photos[0]?p.photos[0].length:0})).sort((a,b)=>a.num-b.num)}; }""", nom)

def nouveau_point(page, texte, photo=None):
    page.click("#fab"); page.wait_for_selector("#shItem.on")
    page.fill("#iDesc", texte)
    if photo:
        page.set_input_files("#iFileGal", photo); page.wait_for_selector("#iPhotos .photo img")
    page.click("#iSave"); page.wait_for_selector("#shItem.on", state="detached", timeout=3000) if False else page.wait_for_timeout(400)

def modifier_point(page, num, texte):
    pid = page.evaluate("(n)=>ch.suivi.points.find(p=>p.num===n).id", num)
    page.click(f"#liste .carte[data-id='{pid}']"); page.wait_for_selector("#shItem.on")
    page.fill("#iDesc", texte); page.click("#iSave"); page.wait_for_timeout(400)

def supprimer_point(page, num):
    pid = page.evaluate("(n)=>ch.suivi.points.find(p=>p.num===n).id", num)
    page.click(f"#liste .carte[data-id='{pid}']"); page.wait_for_selector("#shItem.on")
    page.click("#iDelete"); page.wait_for_timeout(400)

def ouvrir(page, nom):
    if page.evaluate("()=>!!ch"): page.click("#btnBack"); page.wait_for_timeout(300)
    page.click(f"#chList .ccard:has-text('{nom}')"); page.wait_for_selector("#vCh:not([hidden])")

def accueil(page):
    if page.evaluate("()=>!!ch"): page.click("#btnBack"); page.wait_for_timeout(300)

import hashlib, re
MOCK = "--mock" in sys.argv
hors_ligne = set()
class Simu:
    """Copie en mémoire des fonctions opr_* de serveur/synchro.sql (mêmes règles)."""
    def __init__(s): s.esp, s.seq = {}, 0
    def e(s, cle):
        if not isinstance(cle, str) or not re.fullmatch(r"[0-9a-f]{64}", cle): return None
        h = hashlib.sha256(cle.encode()).hexdigest(); return s.esp.get(h)
    def appel(s, fn, a):
        cle = a.get("p_cle")
        if fn == "opr_ouvrir":
            if not isinstance(cle, str) or not re.fullmatch(r"[0-9a-f]{64}", cle): return {"ok": False, "erreur": "cle"}
            h = hashlib.sha256(cle.encode()).hexdigest()
            if h in s.esp: return {"ok": True}
            if not a.get("p_creer"): return {"ok": False, "erreur": "inconnu"}
            if len(s.esp) >= 3: return {"ok": False, "erreur": "limite"}
            s.esp[h] = {"docs": {}, "images": {}, "plans": set(), "expirees": set()}; return {"ok": True, "cree": True}
        e = s.e(cle)
        if e is None: return {"ok": False, "erreur": "inconnu"}
        if fn == "opr_tirer":
            d = sorted(({"id": k, **v} for k, v in e["docs"].items() if v["rev"] > (a.get("p_depuis") or 0)), key=lambda x: x["rev"])
            return {"ok": True, "docs": d}
        if fn == "opr_pousser":
            sup = bool(a.get("p_supprime")); i = a["p_id"]
            if not sup and (a.get("p_data") is None or len(a["p_data"]) > 6000000): return {"ok": False, "erreur": "taille"}
            if i in e["docs"] and e["docs"][i]["rev"] != (a.get("p_base") or 0): return {"ok": False, "conflit": True, "rev": e["docs"][i]["rev"]}
            s.seq += 1; e["docs"][i] = {"rev": s.seq, "data": None if sup else a["p_data"], "supprime": sup}; return {"ok": True, "rev": s.seq}
        if fn == "opr_images_manquantes": return {"ok": True, "manquantes": [h for h in a["p_h"] if h not in e["images"] and h not in e["expirees"]]}
        if fn == "opr_image_poser":
            if not a.get("p_data"): return {"ok": False, "erreur": "taille"}
            if a.get("p_plan"): e["plans"].add(a["p_h"])
            e["images"].setdefault(a["p_h"], base64.b64encode(base64.b64decode(a["p_data"])).decode()); return {"ok": True}
        if fn == "opr_images_lire": return {"ok": True, "images": {h: e["images"][h] for h in a["p_h"][:10] if h in e["images"]}}
        if fn == "opr_etat": return {"ok": True, "chantiers": sum(1 for v in e["docs"].values() if not v["supprime"]),
                                     "photos": sum(1 for h in e["images"] if h not in e["plans"]), "plans": len(e["plans"]),
                                     "octets": sum(len(x) for x in e["images"].values()), "quota": 400*1048576, "base": 80*1048576}
        if fn == "opr_effacer":
            del s.esp[hashlib.sha256(cle.encode()).hexdigest()]; return {"ok": True}
simu = Simu()
def brancher_simu(ctx, nom):
    def h(route, req):
        if nom in hors_ligne: return route.abort("internetdisconnected")
        fn = req.url.rsplit("/", 1)[1]
        route.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"},
                      body=json.dumps(simu.appel(fn, json.loads(req.post_data or "{}"))))
    ctx.route("**/rest/v1/rpc/*", h)
def couper(ctx, nom, coupe):
    if MOCK: (hors_ligne.add if coupe else hors_ligne.discard)(nom)
    else: ctx.set_offline(coupe)

import atexit, urllib.request
CLE = {"v": None}
def effacer_espace_test():
    """Filet : quoi qu'il arrive, l'espace de test ne reste pas sur le vrai serveur."""
    if MOCK or not CLE["v"]: return
    req = urllib.request.Request("https://mcosgvcdclcxxytzplcs.supabase.co/rest/v1/rpc/opr_effacer", method="POST",
        data=json.dumps({"p_cle": CLE["v"]}).encode(), headers={"apikey": "sb_publishable_X5fumnTJVfZCCU_kbyTo6w_q_Wz0fPS", "Content-Type": "application/json"})
    try: print("   (filet de nettoyage :", urllib.request.urlopen(req, timeout=20).read().decode(), ")")
    except Exception as e: print("   (filet de nettoyage impossible :", e, ")")
atexit.register(effacer_espace_test)

NOM = "Chantier test synchro"
srv = serveur()
with sync_playwright() as p:
    nav = p.chromium.launch(channel="msedge", headless=True)
    tel_ctx = nav.new_context(**p.devices["iPhone 13"], service_workers="block" if MOCK else "allow")
    pc_ctx = nav.new_context(viewport={"width": 1366, "height": 860}, service_workers="block" if MOCK else "allow")
    if MOCK: brancher_simu(tel_ctx, "tel"); brancher_simu(pc_ctx, "pc"); print("   (serveur SIMULÉ)")
    tel, pc = tel_ctx.new_page(), pc_ctx.new_page()
    dialogues(tel, "tel"); dialogues(pc, "pc")
    for pg in (tel, pc):
        pg.goto(URL); pg.wait_for_selector("#syncLine")
    verif("Synchroniser avec ton autre appareil" in tel.text_content("#syncLineT"), "accueil : invitation à synchroniser visible")

    # --- Téléphone : un chantier, 2 points dont 1 avec photo, un plan ---
    tel.click("#hNew"); tel.fill("#cNom", NOM); tel.fill("#cAdresse", "12 rue des Essais"); tel.click("#cSave")
    tel.wait_for_selector("#vCh:not([hidden])")
    nouveau_point(tel, "Fissure en plafond", jpeg(tel, "#B33", "PHOTO 1"))
    nouveau_point(tel, "Prise à reprendre")
    tel.set_input_files("#planFile", jpeg(tel, "#336", "PLAN RDC", 1600, 1100)); tel.wait_for_selector("#planStage:not([hidden])")
    tel.click("#tabListe")
    canon = tel.evaluate("()=>{const p=ch.suivi.points[0].photos[0].split(',')[1]; return b64(unb64(p))===p;}")
    verif(canon, "base64 des photos canonique (empreintes stables)")
    accueil(tel)

    # --- Téléphone : activer ---
    tel.click("#syncLine"); tel.wait_for_selector("#shSync.on"); tel.wait_for_timeout(450); tel.screenshot(path=os.path.join(OUT, "tel-1-synchro-inactive.png"))
    t0 = time.time(); tel.click("#syCreer"); tel.wait_for_selector(".sy-code")
    CLE["v"] = tel.evaluate("()=>syncCles.acces")
    tel.wait_for_function("()=>sync && sync.dernier>0 && !syncP", timeout=120000)
    print(f"   (envoi initial mesuré : {time.time()-t0:.1f} s)")
    code = tel.text_content(".sy-code").strip()
    verif(len(code) == 19 and code.count("-") == 3, f"code affiché au format XXXX-XXXX-XXXX-XXXX ({code[:4]}-…)")
    tel.wait_for_timeout(500); tel.screenshot(path=os.path.join(OUT, "tel-2-code.png"))
    r = synchro(tel); verif(r["err"] == "" and r["att"] == 0, f"téléphone : tout envoyé ({r['ligne']})")

    # --- Le serveur ne voit que du chiffré ---
    brut = tel.evaluate("async()=>JSON.stringify(await rpc('opr_tirer',{p_cle:syncCles.acces,p_depuis:0}))")
    verif(NOM not in brut and "Fissure" not in brut and "Essais" not in brut and len(brut) > 200, "serveur : aucun texte en clair (chantier chiffré)")
    cle_test = tel.evaluate("()=>syncCles.acces")
    et = tel.evaluate("async()=>rpc('opr_etat',{p_cle:syncCles.acces})")
    verif(et.get("photos") == 1 and et.get("plans") == 1 and et.get("octets", 0) > 0 and et.get("quota") == 400*1048576,
          f"serveur : 1 photo + 1 plan comptés, place suivie, quota 400 Mo ({et.get('photos')}/{et.get('plans')}/{round(et.get('octets',0)/1024)} Ko)")

    # --- PC : relier avec le code tapé en minuscules et espaces ---
    tel.click("#syClose")
    pc.click("#syncLine"); pc.wait_for_selector("#shSync.on")
    pc.fill("#syCode", code.lower().replace("-", " "))
    t0 = time.time(); pc.click("#syRejoindre")
    pc.wait_for_function("()=>sync && sync.dernier>0 && !syncP", timeout=120000)
    print(f"   (réception initiale mesurée : {time.time()-t0:.1f} s)")
    pc.wait_for_timeout(400); pc.screenshot(path=os.path.join(OUT, "pc-1-relie.png"))
    pc.click("#syClose"); pc.wait_for_timeout(300); pc.screenshot(path=os.path.join(OUT, "pc-2-accueil.png"))
    e_tel, e_pc = etat(tel, NOM), etat(pc, NOM)
    verif(e_pc is not None, "PC : le chantier du téléphone est arrivé")
    verif(e_pc and e_pc["points"] == e_tel["points"] and e_pc["plans"] == 1 and e_pc["adresse"] == "12 rue des Essais",
          "PC : mêmes points, même photo, plan et adresse")
    meme_photo = pc.evaluate("async(n)=>{const s=idx.chantiers.find(x=>x.nom===n);const c=await IDB.get('ch:'+s.id);return c.suivi.points.find(p=>p.num===1).photos[0];}", NOM) == \
                 tel.evaluate("async(n)=>{const s=idx.chantiers.find(x=>x.nom===n);const c=await IDB.get('ch:'+s.id);return c.suivi.points.find(p=>p.num===1).photos[0];}", NOM)
    verif(meme_photo, "PC : photo identique octet pour octet")

    # --- PC modifie, le téléphone reçoit ---
    ouvrir(pc, NOM)
    modifier_point(pc, 1, "Fissure en plafond — vue au bureau")
    nouveau_point(pc, "Point ajouté au PC", jpeg(pc, "#383", "PHOTO PC"))
    r = synchro(pc); verif(r["err"] == "" and r["att"] == 0, "PC : modifications envoyées")
    synchro(tel); e = etat(tel, NOM)
    verif([x["desc"] for x in e["points"]] == ["Fissure en plafond — vue au bureau", "Prise à reprendre", "Point ajouté au PC"] and e["points"][2]["photos"] == 1,
          "téléphone : reçoit la modif du PC + le nouveau point avec sa photo")

    # --- Les deux hors ligne, chacun modifie, puis fusion ---
    couper(tel_ctx, "tel", True); couper(pc_ctx, "pc", True)
    ouvrir(tel, NOM)
    modifier_point(tel, 2, "Prise à reprendre (vu sur le téléphone hors ligne)")
    nouveau_point(tel, "Nouveau point du téléphone")
    tel.evaluate("()=>{ ch.adresse='14 rue des Essais'; persist(); }")
    modifier_point(pc, 1, "Fissure (corrigé au PC hors ligne)")
    supprimer_point(pc, 3)
    nouveau_point(pc, "Nouveau point du PC")
    accueil(tel)
    r = synchro(tel); verif(r["err"] == "Pas de réseau" and "Pas de réseau" in r["ligne"], f"hors ligne : affiché sans erreur bloquante ({r['ligne']})")
    tel.screenshot(path=os.path.join(OUT, "tel-3-hors-ligne.png"))
    couper(tel_ctx, "tel", False); couper(pc_ctx, "pc", False)
    synchro(tel); synchro(pc); synchro(tel)
    e_tel, e_pc = etat(tel, NOM), etat(pc, NOM)
    descs = sorted(x["desc"] for x in e_tel["points"])
    verif(e_tel["points"] == e_pc["points"] and e_tel["adresse"] == e_pc["adresse"] == "14 rue des Essais", "fusion : téléphone et PC identiques")
    verif(descs == sorted(["Fissure (corrigé au PC hors ligne)", "Prise à reprendre (vu sur le téléphone hors ligne)", "Nouveau point du téléphone", "Nouveau point du PC"]),
          "fusion : modifs des deux côtés gardées, point supprimé au PC bien supprimé")
    nums = [x["num"] for x in e_tel["points"]]
    verif(len(set(nums)) == len(nums), f"fusion : numéros distincts malgré la création simultanée ({nums})")

    # --- Rédacteur des documents ---
    accueil(pc); pc.click("#btnMenu"); pc.click("#menuBody .menu-item:has-text('Rédacteur')")
    pc.fill("#mNom", "Nico Berger"); pc.fill("#mFonction", "Conducteur de travaux"); pc.click("#mSave"); pc.wait_for_timeout(300)
    synchro(pc); synchro(tel)
    verif(tel.evaluate("()=>idx.settings.nom") == "Nico Berger", "rédacteur : recopié sur le téléphone")

    # --- Redémarrage : la synchro reste active ---
    tel.reload(); tel.wait_for_selector("#syncLine")
    tel.wait_for_function("()=>sync && syncCles && !syncP", timeout=30000)
    verif("Synchronisé" in tel.text_content("#syncLineT"), "redémarrage : synchro toujours active (" + tel.text_content("#syncLineT") + ")")
    tel.screenshot(path=os.path.join(OUT, "tel-4-accueil-synchro.png"))

    # --- Suppression du chantier au PC → disparaît du téléphone ---
    ouvrir(pc, NOM); pc.click("#btnMenu"); pc.click("#menuBody .menu-item:has-text('Supprimer ce chantier')"); pc.wait_for_timeout(500)
    synchro(pc); synchro(tel)
    verif(etat(tel, NOM) is None and etat(pc, NOM) is None, "suppression : le chantier disparaît des deux appareils")

    # --- Nettoyage : arrêt + effacement de l'espace de test ---
    tel.click("#syncLine"); tel.wait_for_selector("#shSync.on"); tel.click("#syStop"); tel.wait_for_timeout(1500)
    r = tel.evaluate("async(k)=>rpc('opr_ouvrir',{p_cle:k,p_creer:false})", cle_test)
    verif(r.get("erreur") == "inconnu", "nettoyage : espace de test effacé du serveur")
    if r.get("erreur") == "inconnu": CLE["v"] = None
    verif(tel.evaluate("()=>sync===null") and "Synchroniser avec" in tel.text_content("#syncLineT"), "arrêt : appareil revenu en mode local")
    nav.close()
srv.shutdown()

print()
print(f"{len(ok)} contrôles OK, {len(ko)} en échec")
for e in erreurs_console: print("   console :", e)
sys.exit(1 if ko else 0)
