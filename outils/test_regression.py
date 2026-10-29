"""Non-régression OPR Chantier 3.1 (vrai Edge, formats iPhone et PC, serveur de synchro simulé) :
fonctions existantes de la V3 + reprise d'anciennes données (V2 et V3) par la synchro."""
import tempfile, base64, functools, http.server, json, os, socketserver, sys, threading, hashlib, re
from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(tempfile.gettempdir(), "opr-chantier-captures"); os.makedirs(OUT, exist_ok=True)
class Silencieux(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Silencieux, directory=REPO)); srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/index.html"

ok, ko, console = [], [], []
def verif(c, m): (ok if c else ko).append(m); print(("OK     " if c else "ÉCHEC  ") + m, flush=True)

# --- serveur de synchro simulé (mêmes règles que serveur/synchro.sql) ---
ESP, SEQ, ENVOIS = {}, [0], []
def appel(fn, a):
    cle = a.get("p_cle", ""); h = hashlib.sha256(cle.encode()).hexdigest()
    if fn == "opr_ouvrir":
        if h in ESP: return {"ok": True}
        if not a.get("p_creer"): return {"ok": False, "erreur": "inconnu"}
        ESP[h] = {"docs": {}, "images": {}, "expirees": set()}; return {"ok": True, "cree": True}
    e = ESP.get(h)
    if e is None: return {"ok": False, "erreur": "inconnu"}
    if fn == "opr_tirer": return {"ok": True, "docs": sorted(({"id": k, **v} for k, v in e["docs"].items() if v["rev"] > (a.get("p_depuis") or 0)), key=lambda x: x["rev"])}
    if fn == "opr_pousser":
        i = a["p_id"]
        if i in e["docs"] and e["docs"][i]["rev"] != (a.get("p_base") or 0): return {"ok": False, "conflit": True, "rev": e["docs"][i]["rev"]}
        SEQ[0] += 1; e["docs"][i] = {"rev": SEQ[0], "data": None if a.get("p_supprime") else a["p_data"], "supprime": bool(a.get("p_supprime"))}; return {"ok": True, "rev": SEQ[0]}
    if fn == "opr_images_manquantes": return {"ok": True, "manquantes": [x for x in a["p_h"] if x not in e["images"] and x not in e["expirees"]]}
    if fn == "opr_image_poser":
        ENVOIS.append(a["p_h"]); e["images"].setdefault(a["p_h"], {"data": a["p_data"], "plan": bool(a.get("p_plan"))}); return {"ok": True}
    if fn == "opr_images_lire": return {"ok": True, "images": {x: e["images"][x]["data"] for x in a["p_h"][:10] if x in e["images"]}}
    if fn == "opr_etat": return {"ok": True, "chantiers": 0, "photos": 0, "plans": 0, "octets": 0, "quota": 1, "base": 1}
    return {"ok": True}
def vieillir_60_jours():
    """Ce que fait opr_tirer au bout de 60 jours : photos effacées (et notées), plans gardés."""
    for e in ESP.values():
        for x in [k for k, v in e["images"].items() if not v["plan"]]: del e["images"][x]; e["expirees"].add(x)
def simu(ctx):
    ctx.route("**/rest/v1/rpc/*", lambda route, req: route.fulfill(status=200, content_type="application/json",
        headers={"access-control-allow-origin": "*"}, body=json.dumps(appel(req.url.rsplit("/", 1)[1], json.loads(req.post_data or "{}")))))

def page(nav, p, nom, mobile):
    ctx = nav.new_context(**(p.devices["iPhone 13"] if mobile else {"viewport": {"width": 1366, "height": 860}}), service_workers="block", accept_downloads=True)
    simu(ctx); ctx.add_init_script("window.print=()=>{ window.__imprime=(window.__imprime||0)+1; };")
    pg = ctx.new_page()
    pg.on("dialog", lambda d: d.accept(d.default_value) if d.type == "prompt" else d.accept())
    pg.on("console", lambda m: m.type == "error" and console.append(f"{nom}: {m.text}"))
    pg.on("pageerror", lambda e: console.append(f"{nom} (exception): {e}"))
    return ctx, pg

def jpeg(pg, c, t, w=900, h=600):
    b = pg.evaluate("""([c,t,w,h])=>{const v=document.createElement('canvas');v.width=w;v.height=h;const x=v.getContext('2d');x.fillStyle=c;x.fillRect(0,0,w,h);
      x.fillStyle='#fff';x.font='bold 60px sans-serif';x.fillText(t,30,120);return v.toDataURL('image/jpeg',0.9).split(',')[1];}""", [c, t, w, h])
    return {"name": "img.jpg", "mimeType": "image/jpeg", "buffer": base64.b64decode(b)}

with sync_playwright() as p:
    nav = p.chromium.launch(channel="msedge", headless=True)
    for mobile in (True, False):
        F = "iPhone" if mobile else "PC"
        ctx, pg = page(nav, p, F, mobile)
        pg.goto(URL); pg.wait_for_selector("#syncLine")
        # 1) reprise d'une ancienne V2 (clé « state ») + d'un chantier V3 sans les champs de synchro
        img = "data:image/jpeg;base64," + base64.b64encode(jpeg(pg, "#933", "V2")["buffer"]).decode()
        pg.evaluate("""async (img)=>{
          await IDB.set('state',{chantier:{nom:'Ancienne OPR V2',adresse:'1 rue V2'},seq:1,plans:[],reserves:[{id:'r1',num:1,desc:'Réserve V2',photos:[img],gravite:'majeure',statut:'lever'}]});
          await IDB.del('idx');
          await IDB.set('ch:cV3ancien',{id:'cV3ancien',v:3,nom:'Chantier V3 existant',adresse:'3 rue V3',created:'2026-10-20',updated:1761500000000,lastModule:'suivi',plans:[],
            opr:{date:'',presents:'',obs:'',seq:0,reserves:[]},suivi:{seq:1,vseq:1,cur:'v1',visites:[{id:'v1',num:1,date:'2026-10-20'}],points:[{id:'p1',num:1,desc:'Point V3',photos:[img],type:'afaire',prio:'normale',statut:'ouvert',visiteId:'v1'}]}});
        }""", img)
        pg.reload(); pg.wait_for_selector("#syncLine")
        noms = pg.evaluate("()=>idx.chantiers.map(c=>c.nom)")
        verif("Ancienne OPR V2" in noms, f"{F} : reprise des données V2")
        pg.evaluate("async()=>{ const c=await IDB.get('ch:cV3ancien'); idx.chantiers.push(summary(cleanChantier(c))); await saveIdx(); renderHome(); }")

        # 2) saisie courante
        pg.click("#hNew"); pg.fill("#cNom", "Chantier régression"); pg.fill("#cEntreprises", "Plâtrerie — Ent. X\nÉlectricité — Ent. Y"); pg.click("#cSave")
        pg.wait_for_selector("#vCh:not([hidden])")
        pg.click("#fab"); pg.wait_for_selector("#shItem.on"); pg.fill("#iDesc", "Joint à reprendre"); pg.fill("#iLot", "Plâtrerie — Ent. X")
        pg.click("#iType button[data-v='qualite']"); pg.click("#iPrio button[data-v='urgente']")
        pg.set_input_files("#iFileGal", jpeg(pg, "#355", "P1")); pg.wait_for_selector("#iPhotos .photo img"); pg.click("#iSave"); pg.wait_for_timeout(350)
        pg.click("#fab"); pg.fill("#iDesc", "Gaine électrique"); pg.click("#iStatutP button[data-v='fait']"); pg.click("#iSave"); pg.wait_for_timeout(350)
        e = pg.evaluate("()=>({n:ch.suivi.points.length, v:ch.suivi.visites.length, t:ch.suivi.points[0].type, f:ch.suivi.points[1].statut, d:ch.suivi.points[1].dateFait})")
        verif(e["n"] == 2 and e["v"] == 1 and e["t"] == "qualite" and e["f"] == "fait" and e["d"], f"{F} : points, visite auto, statut soldé")
        pg.click("#ctxNew"); pg.wait_for_selector("#shVisite.on"); pg.fill("#vAvancement", "Cloisons terminées"); pg.click("#vSave"); pg.wait_for_timeout(350)
        verif(pg.evaluate("()=>ch.suivi.visites.length") == 2, f"{F} : nouvelle visite")
        # report en réserve
        pid = pg.evaluate("()=>ch.suivi.points[0].id"); pg.click(f"#liste .carte[data-id='{pid}']"); pg.wait_for_selector("#shItem.on")
        pg.click("#iToRes"); pg.wait_for_timeout(500); pg.click("#iSave"); pg.wait_for_timeout(350)
        r = pg.evaluate("()=>({m:ui.module, n:ch.opr.reserves.length, g:ch.opr.reserves[0]&&ch.opr.reserves[0].gravite, ph:ch.opr.reserves[0]&&ch.opr.reserves[0].photos.length})")
        verif(r["m"] == "opr" and r["n"] == 1 and r["g"] == "majeure" and r["ph"] == 1, f"{F} : report d'un point en réserve OPR")
        # plan + pointage
        pg.set_input_files("#planFile", jpeg(pg, "#246", "PLAN", 1400, 1000)); pg.wait_for_selector("#planStage:not([hidden])"); pg.wait_for_timeout(400)
        pg.click("#planPlace"); bb = pg.locator("#planImg").bounding_box()
        pg.mouse.click(bb["x"] + bb["width"] * 0.4, bb["y"] + bb["height"] * 0.5); pg.wait_for_selector("#shItem.on")
        pg.fill("#iDesc", "Réserve pointée"); pg.click("#iSave"); pg.wait_for_timeout(400)
        verif(pg.locator("#planCanvas .pin").count() >= 1, f"{F} : pointage d'une réserve sur le plan")
        pg.screenshot(path=os.path.join(OUT, f"reg-{F}-plan.png"))
        # exports
        pg.click("#tabListe"); pg.click("#btnExport"); pg.wait_for_timeout(1200)
        verif(pg.evaluate("()=>window.__imprime||0") >= 1 and "Procès-verbal" in (pg.evaluate("()=>document.querySelector('#pv').textContent") or ""), f"{F} : PV d'OPR généré")
        with pg.expect_download() as dl:
            pg.click("#btnMenu"); pg.click("#menuBody .menu-item:has-text('Exporter en tableau')")
        verif(dl.value.suggested_filename.endswith(".csv"), f"{F} : export Excel (CSV)")
        if not mobile:
            with pg.expect_download() as dl:
                pg.click("#btnMenu"); pg.click("#menuBody .menu-item:has-text('Envoyer ce chantier')")
            chemin = dl.value.path(); data = json.load(open(chemin, encoding="utf-8"))
            verif(data["type"] == "opr-chantier" and len(data["chantier"]["suivi"]["points"]) == 2, f"{F} : export du chantier en fichier")
            pg.click("#btnBack"); pg.wait_for_timeout(300)
            pg.set_input_files("#importFile", chemin); pg.wait_for_timeout(1200)
            imp = pg.evaluate("()=>idx.chantiers.filter(c=>c.nom==='Chantier régression').map(c=>c.nbPoints+'|'+c.nbRes)")
            verif(imp == ["2|2"], f"{F} : import du fichier (remplacement confirmé, contenu intact : {imp})")
        # 3) synchro des anciennes données vers un 2e appareil
        if pg.evaluate("()=>!!ch"): pg.click("#btnBack"); pg.wait_for_timeout(300)
        pg.click("#syncLine"); pg.wait_for_selector("#shSync.on"); pg.click("#syCreer"); pg.wait_for_selector(".sy-code")
        pg.wait_for_function("()=>sync && sync.dernier>0 && !syncP", timeout=60000)
        code = pg.text_content(".sy-code")
        ctx2, pg2 = page(nav, p, F + "-2", not mobile); pg2.goto(URL); pg2.wait_for_selector("#syncLine")
        pg2.click("#syncLine"); pg2.wait_for_selector("#shSync.on"); pg2.fill("#syCode", code); pg2.click("#syRejoindre")
        pg2.wait_for_function("()=>sync && sync.dernier>0 && !syncP", timeout=60000)
        a = sorted(pg.evaluate("()=>idx.chantiers.map(c=>c.nom+'|'+c.nbPoints+'|'+c.nbRes)"))
        b = sorted(pg2.evaluate("()=>idx.chantiers.map(c=>c.nom+'|'+c.nbPoints+'|'+c.nbRes)"))
        verif(a == b and len(a) >= 3, f"{F} : V2 reprise + V3 existant + nouveaux chantiers recopiés sur l'autre appareil ({len(b)})")
        ph = pg2.evaluate("async()=>{const c=await IDB.get('ch:cV3ancien'); return c && c.suivi.points[0].photos.length}")
        verif(ph == 1, f"{F} : la photo du chantier V3 existant arrive aussi")
        # pas de boucle : chantier ouvert, synchro au repos → au plus 1 appel serveur en 12 s
        pg.click("#syClose"); pg.click("#chList .ccard:has-text('Chantier V3 existant')"); pg.wait_for_selector("#vCh:not([hidden])")
        pg.evaluate("()=>synchroniser()"); appels = []
        pg.on("request", lambda r: "/rpc/" in r.url and appels.append(r.url.rsplit("/", 1)[1]))
        pg.wait_for_timeout(12000)
        verif(len(appels) <= 1, f"{F} : chantier ouvert, pas de synchro en boucle ({len(appels)} appel(s) en 12 s)")
        # une modif au PC/téléphone ouvert part toute seule (≈ 4 s) et arrive sur l'autre appareil
        pg.evaluate("()=>{ ch.suivi.points[0].desc='Modifié chantier ouvert'; persist(); }")
        pg.wait_for_function("()=>!saveT && !syncP && enAttente()===0", timeout=20000)
        pg2.evaluate("()=>synchroniser()")
        d2 = pg2.evaluate("async()=>(await IDB.get('ch:cV3ancien')).suivi.points[0].desc")
        verif(d2 == "Modifié chantier ouvert", f"{F} : modif envoyée seule depuis un chantier ouvert, reçue en face")

        if not mobile:
            # 4) réception pendant une saisie : rien n'est appliqué tant que le formulaire est ouvert
            if pg2.locator("#shSync.on").count(): pg2.click("#syClose"); pg2.wait_for_timeout(300)
            pg2.click("#chList .ccard:has-text('Chantier V3 existant')"); pg2.wait_for_selector("#vCh:not([hidden])")
            pid = pg2.evaluate("()=>ch.suivi.points[0].id")
            pg2.click(f"#liste .carte[data-id='{pid}']"); pg2.wait_for_selector("#shItem.on")
            pg.evaluate("()=>{ ch.suivi.points[0].desc='Changé en face pendant la saisie'; persist(); }")
            pg.wait_for_function("()=>!saveT && !syncP && enAttente()===0", timeout=20000)
            pg2.evaluate("()=>synchroniser()")
            verif(pg2.evaluate("()=>ch.suivi.points[0].desc") == "Modifié chantier ouvert", "saisie en cours : la synchro est reportée")
            pg2.evaluate("async()=>{ await cycle(); }")   # cas Codex : une synchro déjà partie quand le formulaire s'ouvre
            r = pg2.evaluate("()=>({d:ch.suivi.points[0].desc, diff:[...differes]})")
            verif(r["d"] == "Modifié chantier ouvert" and r["diff"], "saisie en cours : une réception déjà partie attend la fermeture du formulaire")
            pg2.click("#iCancel"); pg2.wait_for_timeout(400); pg2.evaluate("()=>synchroniser()")
            verif(pg2.evaluate("()=>ch.suivi.points[0].desc") == "Changé en face pendant la saisie", "formulaire fermé : la réception s'applique")

            # 5) photos effacées du serveur après 60 jours : un nouvel appareil a un repère, rien n'est perdu
            pg.set_input_files("#planFile", jpeg(pg, "#264", "PLAN 60J", 1400, 1000)); pg.wait_for_timeout(800)
            pg.wait_for_function("()=>!saveT && !syncP && enAttente()===0", timeout=20000)
            vieillir_60_jours()
            ctx3, pg3 = page(nav, p, "PC-3", False); pg3.goto(URL); pg3.wait_for_selector("#syncLine")
            pg3.click("#syncLine"); pg3.wait_for_selector("#shSync.on"); pg3.fill("#syCode", code); pg3.click("#syRejoindre")
            pg3.wait_for_function("()=>sync && sync.dernier>0 && !syncP", timeout=60000)
            c3 = pg3.evaluate("async()=>{ const c=cleanChantier(await IDB.get('ch:cV3ancien')); return {ph:c.suivi.points[0].photos, plans:c.plans.map(p=>IMG(p.img))}; }")
            verif(len(c3["ph"]) == 1 and c3["ph"][0].startswith("#") and True in c3["plans"],
                  "après 60 jours : nouvel appareil = repère « sur l'autre appareil » pour la photo, plan bien reçu")
            pg3.click("#syClose"); pg3.click("#chList .ccard:has-text('Chantier V3 existant')"); pg3.wait_for_selector("#vCh:not([hidden])")
            pid = pg3.evaluate("()=>ch.suivi.points[0].id"); pg3.click(f"#liste .carte[data-id='{pid}']"); pg3.wait_for_selector("#shItem.on")
            verif(pg3.locator("#iPhotos .photo.absente").count() == 1, "après 60 jours : vignette « Sur l'autre appareil » dans le formulaire")
            pg3.screenshot(path=os.path.join(OUT, "reg-60-jours-repere.png"))
            pg3.fill("#iDesc", "Modifié sur le 3e appareil"); pg3.click("#iSave"); pg3.wait_for_timeout(400)
            pg3.wait_for_function("()=>!saveT && !syncP && enAttente()===0", timeout=20000)
            n_envois = len(ENVOIS)
            pg.evaluate("()=>synchroniser()")
            r = pg.evaluate("()=>({d:ch.suivi.points[0].desc, ph:ch.suivi.points[0].photos.map(x=>IMG(x))})")
            verif(r["d"] == "Modifié sur le 3e appareil" and r["ph"] == [True], "après 60 jours : l'appareil d'origine garde sa vraie photo")
            pg.evaluate("()=>{ ch.suivi.points[0].desc='Encore modifié'; persist(); }")
            pg.wait_for_function("()=>!saveT && !syncP && enAttente()===0", timeout=20000)
            verif(len(ENVOIS) == n_envois, "après 60 jours : une photo effacée n'est pas renvoyée au serveur")
            pg3.click("#iCancel") if pg3.locator("#shItem.on").count() else None
            pg3.click("#btnMenu"); pg3.click("#menuBody .menu-item:has-text('Compte rendu')"); pg3.wait_for_timeout(1200)
            verif(pg3.evaluate("()=>window.__imprime||0") >= 1, "après 60 jours : compte rendu PDF généré malgré la photo absente")
            ctx3.close()
        ctx2.close(); ctx.close()
    nav.close()
srv.shutdown()
print(f"\n{len(ok)} contrôles OK, {len(ko)} en échec")
for c in console: print("   console :", c)
sys.exit(1 if ko else 0)
