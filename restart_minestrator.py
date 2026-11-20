import os
import time
import json
import uuid
import urllib.request
import urllib.parse
import re
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9, non utilisé ici mais sécurité
    ZoneInfo = None
from seleniumbase import SB

# ============================================================
# Identifiants — lus depuis les secrets GitHub Actions
# (dépôt public : plus aucun identifiant en clair dans le code)
# ============================================================
_account = os.environ.get("MINESTRATOR_ACCOUNT", "")
EMAIL, _, PASSWORD = _account.partition(",")
EMAIL = EMAIL.strip()
PASSWORD = PASSWORD.strip()
SERVER_ID  = os.environ.get("MINESTRATOR_SERVER_ID", "").strip()
AUTH_TOKEN = os.environ.get("MINESTRATOR_AUTH", "").strip()

_proxy = os.environ.get("GOST_PROXY", "").strip()
LOCAL_PROXY = "127.0.0.1:8080" if _proxy else None

_tg = os.environ.get("TG_BOT", "")
TG_CHAT_ID, _, TG_TOKEN = _tg.partition(",")
TG_CHAT_ID = TG_CHAT_ID.strip()
TG_TOKEN = TG_TOKEN.strip()

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()

# User-Agent "navigateur" : Discord (derrière Cloudflare) renvoie parfois une
# erreur 403 Forbidden aux requêtes envoyées avec le User-Agent par défaut de
# urllib ("Python-urllib/3.x"). On imite un navigateur pour éviter ce blocage.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# ============================================================
# Plage de maintenance silencieuse : pas de redémarrage
# entre 1h et 6h, heure de Paris (gère automatiquement l'heure d'été/hiver)
# ============================================================
FREEZE_START_HOUR = 1
FREEZE_END_HOUR   = 6

def is_in_freeze_window() -> bool:
    try:
        if ZoneInfo is None:
            return False
        now_paris = datetime.now(ZoneInfo("Europe/Paris"))
        return FREEZE_START_HOUR <= now_paris.hour < FREEZE_END_HOUR
    except Exception as e:
        # Ne doit jamais faire planter tout le script silencieusement :
        # en cas de doute, on considère qu'on N'EST PAS en pause (comportement normal).
        print(f"⚠️ Erreur lors de la détection de l'heure de Paris (on continue normalement) : {e}")
        return False

LOGIN_URL  = "https://minestrator.com/connexion"
SERVER_URL = f"https://minestrator.com/my/server/{SERVER_ID}"
API_URL    = f"https://mine.sttr.io/server/{SERVER_ID}/poweraction"


# ============================================================
# Notification Telegram (texte + photo avec repli en texte seul)
# ============================================================

def now_str():
    import datetime
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def send_tg(result, detail='', photo_path=None):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("ℹ️ TG_BOT non configuré, notification ignorée")
        return
    msg = (
        f"🎮 Notification Minestrator\n"
        f"🕐 Heure d'exécution : {now_str()}\n"
        f"🖥 ID serveur : {SERVER_ID}\n"
        f"📊 Résultat : {result}\n"
        f"{detail}"
    ).strip()

    if photo_path and os.path.exists(photo_path):
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        boundary = uuid.uuid4().hex
        body = []

        body.append(f"--{boundary}\r\n".encode())
        body.append(b'Content-Disposition: form-data; name="chat_id"\r\n\r\n')
        body.append(f"{TG_CHAT_ID}\r\n".encode())

        body.append(f"--{boundary}\r\n".encode())
        body.append(b'Content-Disposition: form-data; name="caption"\r\n\r\n')
        body.append(f"{msg}\r\n".encode())

        filename = os.path.basename(photo_path)
        body.append(f"--{boundary}\r\n".encode())
        body.append(f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode())
        body.append(b"Content-Type: image/png\r\n\r\n")
        with open(photo_path, "rb") as f:
            body.append(f.read())
        body.append(b"\r\n")
        body.append(f"--{boundary}--\r\n".encode())

        payload = b"".join(body)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(payload))
        }
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30):
                print(f"📨 Notification Telegram (photo) envoyée ({filename})")
            return
        except Exception as e:
            print(f"⚠️ Échec envoi photo Telegram, repli en texte seul : {e}")

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": msg}).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            print("📨 Notification Telegram (texte) envoyée")
    except Exception as e:
        print(f"⚠️ Échec notification Telegram : {e}")


def send_discord(title: str, detail: str = ""):
    """Envoie une notification dans un salon Discord via un webhook."""
    if not DISCORD_WEBHOOK:
        print("ℹ️ DISCORD_WEBHOOK non configuré, notification Discord ignorée")
        return
    content = f"**🎮 Minestrator — {title}**\n🕐 {now_str()}\n🖥 Serveur : {SERVER_ID}\n{detail}".strip()
    payload = json.dumps({"content": content[:1900]}).encode("utf-8")
    try:
        req = urllib.request.Request(
            DISCORD_WEBHOOK,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": BROWSER_USER_AGENT,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15):
            print("📨 Webhook Discord envoyé")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        print(f"⚠️ Échec webhook Discord : HTTP {e.code} {e.reason} — {body}")
    except Exception as e:
        print(f"⚠️ Échec webhook Discord : {e}")


def parse_remaining_to_seconds(remaining: str) -> int:
    """Convertit un texte type '3h 12m 40s' en secondes (0 si non reconnu)."""
    if not remaining:
        return 0
    h = re.search(r'(\d+)\s*h', remaining)
    m = re.search(r'(\d+)\s*m', remaining)
    s = re.search(r'(\d+)\s*s', remaining)
    total = 0
    if h: total += int(h.group(1)) * 3600
    if m: total += int(m.group(1)) * 60
    if s: total += int(s.group(1))
    return total


def write_restart_schedule(remaining: str, frozen: bool):
    """Écrit restart_schedule.json (lu par le script Skript côté serveur)."""
    seconds = parse_remaining_to_seconds(remaining)
    next_restart_iso = None
    next_restart_epoch = None
    if seconds > 0:
        from datetime import timedelta
        dt = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        next_restart_iso = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        next_restart_epoch = int(dt.timestamp())
    data = {
        "next_restart_utc": next_restart_iso,
        "next_restart_epoch": next_restart_epoch,
        "seconds_remaining": seconds,  # simple compteur en secondes, le plus facile à exploiter côté Skript
        "updated_utc": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        "frozen": frozen,
    }
    try:
        with open("restart_schedule.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"📝 restart_schedule.json écrit : {data}")
    except Exception as e:
        print(f"⚠️ Impossible d'écrire restart_schedule.json : {e}")

    # Format texte minimal pour Skript (pas besoin d'addon JSON, juste de "split at")
    try:
        txt_line = f"frozen={'1' if frozen else '0'};seconds_remaining={seconds}"
        with open("restart_schedule.txt", "w", encoding="utf-8") as f:
            f.write(txt_line)
        print(f"📝 restart_schedule.txt écrit : {txt_line}")
    except Exception as e:
        print(f"⚠️ Impossible d'écrire restart_schedule.txt : {e}")


# ============================================================
# Turnstile invisible : injection d'un écouteur + hook pour capturer
# le token et les réponses réseau
# ============================================================

INJECT_TOKEN_LISTENER_JS = """
(function() {
    if (window.__cf_token_listener_injected__) return;
    window.__cf_token_listener_injected__ = true;
    window.__cf_turnstile_token__ = '';
    window.__captured_auth_header__ = '';

    window.addEventListener('message', function(e) {
        if (!e.origin || e.origin.indexOf('cloudflare.com') === -1) return;
        var d = e.data;
        if (!d) return;
        if (d.token && d.token.length > 30) {
            window.__cf_turnstile_token__ = d.token;
        }
    });

    var origFetch = window.fetch;
    window.fetch = function() {
        var args = arguments;
        try {
            if (args[1]) {
                if (args[1].headers) {
                    var auth = args[1].headers['Authorization'] || args[1].headers['authorization'];
                    if (auth) window.__captured_auth_header__ = auth;
                }
                if (args[1].body && typeof args[1].body === 'string') {
                    var parsed = JSON.parse(args[1].body);
                    if (parsed.turnstile_token) {
                        window.__cf_turnstile_token__ = parsed.turnstile_token;
                    }
                }
            }
        } catch(e) {}
        return origFetch.apply(this, args);
    };

    setInterval(function() {
        try {
            var inputs = document.querySelectorAll(
                'input[name="cf-turnstile-response"], input[name="cf_turnstile_response"], input[name*="turnstile"]'
            );
            for (var i = 0; i < inputs.length; i++) {
                if (inputs[i].value && inputs[i].value.length > 30) {
                    window.__cf_turnstile_token__ = inputs[i].value;
                }
            }
            if (window.turnstile && typeof window.turnstile.getResponse === 'function') {
                var resp = window.turnstile.getResponse();
                if (resp && resp.length > 30) {
                    window.__cf_turnstile_token__ = resp;
                }
            }
        } catch(e) {}
    }, 500);
})();
"""

READ_TOKEN_JS = "(function(){ return window.__cf_turnstile_token__ || ''; })()"


def inject_listener(sb):
    try:
        sb.execute_script(INJECT_TOKEN_LISTENER_JS)
        print("📡 Écouteur Turnstile injecté")
    except Exception as e:
        print(f"⚠️ Échec injection de l'écouteur : {e}")


def wait_for_token(sb, timeout=15) -> str:
    print(f"⏳ Attente de génération automatique du token Turnstile (max {timeout}s)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            token = sb.execute_script(READ_TOKEN_JS)
            if token and len(token) > 30:
                print(f"✅ Token capturé (longueur {len(token)})")
                return token
        except Exception:
            pass
        time.sleep(1)

    print("ℹ️ Aucun token Turnstile en clair capturé individuellement")
    return ''


# ============================================================
# Contrôle d'alimentation du serveur : gère à la fois
# "démarrage hors-ligne (Démarrer)" et "redémarrage en ligne (Restart)"
# ============================================================

def check_server_and_click_power(sb) -> dict:
    """
    Détecte si le serveur est actuellement hors ligne (Offline) ou en ligne (Online) :
    - S'il est hors ligne : clique automatiquement sur le bouton vert 'Démarrer le serveur' / 'Démarrer'
    - S'il est en ligne : clique automatiquement sur le bouton jaune de redémarrage (parmi les 3
      boutons alignés en haut à gauche), ce qui réinitialise le compte à rebours de 4h
    """
    js_power = """
    (function() {
        var res = {
            status: 'unknown',
            clicked: false,
            action_type: '',
            detail: '',
            countdown: ''
        };

        var bodyText = document.body.innerText || '';

        var mTimer = bodyText.match(/S'éteint dans\\s+([^\\n]+)/i)
                  || bodyText.match(/Shutting down in\\s+([^\\n]+)/i)
                  || bodyText.match(/\\d+h\\s+\\d+m\\s+\\d+s/);
        if (mTimer) {
            res.countdown = mTimer[0].trim();
        }

        if (/Hors ligne|Serveur hors ligne|Offline|Server offline/i.test(bodyText)) {
            res.status = 'Offline (hors ligne)';
        } else if (/En ligne|Online/i.test(bodyText)) {
            res.status = 'Online (en ligne)';
        }

        var allBtns = Array.from(document.querySelectorAll('button'));

        // 1. Cas A : le serveur est hors ligne -> chercher le bouton vert Démarrer / Start et cliquer dessus
        for (var i = 0; i < allBtns.length; i++) {
            var b = allBtns[i];
            if (b.offsetParent === null || b.disabled) continue;
            var txt = (b.textContent || '').trim();
            if (/Démarrer le serveur|Démarrer|Start server|^Start$/i.test(txt)) {
                b.click();
                res.clicked = true;
                res.action_type = 'start';
                res.detail = 'Bouton vert de démarrage cliqué (' + txt + ')';
                return res;
            }
        }

        // 2. Cas B : le serveur est en ligne -> chercher les 3 boutons alignés en haut à gauche
        //    (bleu, jaune, rouge) et cliquer sur le bouton jaune du milieu (redémarrage)
        for (var j = 0; j < allBtns.length; j++) {
            var parent = allBtns[j].parentElement;
            if (!parent) continue;
            var siblingBtns = parent.querySelectorAll(':scope > button');
            if (siblingBtns.length === 3) {
                var blueBtn   = siblingBtns[0];
                var yellowBtn = siblingBtns[1]; // le bouton jaune du milieu = redémarrage (Restart)
                if (yellowBtn && !yellowBtn.disabled) {
                    yellowBtn.click();
                    res.clicked = true;
                    res.action_type = 'restart';
                    res.detail = 'Bouton jaune de redémarrage cliqué (Restart)';
                    return res;
                } else if (blueBtn && !blueBtn.disabled) {
                    blueBtn.click();
                    res.clicked = true;
                    res.action_type = 'start';
                    res.detail = 'Bouton bleu de démarrage cliqué';
                    return res;
                }
            }
        }

        return res;
    })()
    """
    try:
        data = sb.execute_script(js_power) or {}
        print(f"🔍 État de la page détecté : {data}")
        return data
    except Exception as e:
        print(f"⚠️ Erreur lors du clic sur les boutons d'alimentation : {e}")
        return {}


def get_countdown_text(sb) -> str:
    """Récupère le texte du compte à rebours de 4h après rafraîchissement de la page."""
    try:
        txt = sb.execute_script(r"""
            (function(){
                var bodyText = document.body.innerText || '';
                var m = bodyText.match(/S'éteint dans\s+([^\n]+)/i)
                     || bodyText.match(/Shutting down in\s+([^\n]+)/i)
                     || bodyText.match(/\d+h\s+\d+m\s+\d+s/);
                if (m) return m[0].trim();

                var spans = document.querySelectorAll('[data-slot="base"] span');
                var parts = [];
                for (var i = 0; i < spans.length; i++) {
                    var t = spans[i].textContent.trim();
                    if (/^\d+[hms]$/.test(t)) parts.push(t);
                }
                return parts.length ? parts.join(' ') : '';
            })()
        """)
        return txt or ""
    except Exception:
        return ""


# ============================================================
# API : envoi de l'ordre de redémarrage/démarrage via fetch dans le
# navigateur (n'utilise pas "arguments", compatible CDP)
# ============================================================

def send_power_api(sb, token: str, action: str = "restart") -> bool:
    if not token:
        return False
    token_js = json.dumps(token)
    auth_js = json.dumps(AUTH_TOKEN)
    api_url_js = json.dumps(API_URL)
    action_js = json.dumps(action)

    # Utilise un sondage de variable globale plutôt qu'execute_async_script avec
    # arguments[0], pour éviter totalement l'erreur "ReferenceError: arguments is not defined"
    trigger_js = f"""
    (function() {{
        window.__api_power_done__ = false;
        window.__api_power_result__ = null;
        var authHeader = window.__captured_auth_header__ || {auth_js};
        fetch({api_url_js}, {{
            method: "PUT",
            headers: {{
                "Authorization": authHeader,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            }},
            body: JSON.stringify({{poweraction: {action_js}, turnstile_token: {token_js}}})
        }})
        .then(function(r) {{ return r.json(); }})
        .then(function(data) {{
            window.__api_power_result__ = {{ok: true, data: data}};
            window.__api_power_done__ = true;
        }})
        .catch(function(err) {{
            window.__api_power_result__ = {{ok: false, error: err.toString()}};
            window.__api_power_done__ = true;
        }});
    }})()
    """
    try:
        sb.execute_script(trigger_js)
        for _ in range(15):
            done = sb.execute_script("(function(){ return !!window.__api_power_done__; })()")
            if done:
                result = sb.execute_script("(function(){ return window.__api_power_result__; })()") or {}
                print(f"📡 Réponse API ({action}) : {result}")
                if result.get("ok") and result.get("data", {}).get("api", {}).get("code") == 200:
                    print(f"✅ Commande API ({action}) envoyée avec succès !")
                    return True
                return False
            time.sleep(1)
        return False
    except Exception as e:
        print(f"⚠️ Erreur lors de la requête API : {e}")
        return False


def click_login_btn(sb):
    """Clique sur le bouton de connexion (sans utiliser 'arguments')."""
    try:
        if sb.is_element_visible("button:contains('Se connecter')"):
            sb.click("button:contains('Se connecter')")
            print("✅ Bouton 'Se connecter' cliqué")
            return
        elif sb.is_element_visible("button[type='submit']"):
            sb.click("button[type='submit']")
            print("✅ Bouton submit cliqué")
            return
    except Exception:
        pass

    try:
        sb.execute_script("""
            (function(){
                var btns = Array.from(document.querySelectorAll('button'));
                var target = btns.find(function(b){
                    return b.textContent.indexOf('Se connecter') !== -1 || b.type === 'submit';
                });
                if (target) {
                    target.removeAttribute('disabled');
                    target.click();
                }
            })()
        """)
        print("✅ Clic sur le bouton de connexion déclenché via JS")
    except Exception as e:
        print(f"⚠️ Erreur lors du clic sur le bouton de connexion : {e}")


# ============================================================
# Flux principal
# ============================================================

def run_script():
    if is_in_freeze_window():
        msg = (
            f"⏸️ Plage de maintenance {FREEZE_START_HOUR}h-{FREEZE_END_HOUR}h (Paris) en cours : "
            "aucun redémarrage ne sera déclenché. Reprise automatique à "
            f"{FREEZE_END_HOUR}h."
        )
        print(msg)
        write_restart_schedule(remaining="", frozen=True)
        send_tg("⏸️ Pause nocturne", msg)
        send_discord("Pause nocturne (1h-6h)", msg)
        return

    print("🔧 Démarrage du navigateur...")

    sb_kwargs = dict(uc=True, test=True)
    if LOCAL_PROXY:
        sb_kwargs["proxy"] = LOCAL_PROXY
        print(f"🌐 Utilisation du proxy : {LOCAL_PROXY}")
    else:
        print("ℹ️ Aucun proxy configuré, connexion directe")

    with SB(**sb_kwargs) as sb:
        print("🚀 Navigateur prêt !")

        # ── 1. Vérification de l'IP de sortie ───────────────────────────
        print("🌐 Vérification de l'IP de sortie...")
        try:
            sb.open("https://api.ipify.org/?format=json")
            ip_text = re.sub(r'(\d+\.\d+\.\d+\.)\d+', r'\1xx', sb.get_text('body'))
            print(f"✅ IP de sortie confirmée : {ip_text}")
        except Exception:
            print("⚠️ Vérification de l'IP expirée, on continue")

        # ── 2. Connexion ─────────────────────────────────────────────
        print("🔑 Ouverture de la page de connexion...")
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
        time.sleep(3)

        print("✏️ Saisie des identifiants...")
        try:
            sb.wait_for_element_visible("input[type='password']", timeout=25)

            user_selectors = [
                "input[placeholder*='utilisateur']",
                "input[name='pseudo']",
                "input[name='email']",
                "input[type='text']",
                "input[type='email']",
                "input:not([type='password']):not([type='checkbox']):not([type='hidden'])"
            ]
            typed_user = False
            for sel in user_selectors:
                if sb.is_element_visible(sel):
                    sb.type(sel, EMAIL)
                    print(f"✅ Identifiant saisi via le sélecteur : {sel}")
                    typed_user = True
                    break
            if not typed_user:
                raise RuntimeError("Aucun champ de saisie du compte visible n'a été trouvé")

            sb.type("input[type='password']", PASSWORD)
        except Exception as e:
            print(f"❌ Échec du chargement/remplissage du formulaire de connexion : {e}")
            sb.save_screenshot("login_fail.png")
            send_tg("❌ Échec du formulaire de connexion", f"Raison : {e}", photo_path="login_fail.png")
            return

        print("📤 Envoi de la demande de connexion...")
        time.sleep(1)
        click_login_btn(sb)

        print("⏳ Attente de la redirection après connexion...")
        for sec in range(45):
            try:
                cur_url = sb.get_current_url()
                if "/connexion" not in cur_url:
                    print(f"✅ Connexion réussie ! Page actuelle : {cur_url}")
                    break
                if sec in (12, 25):
                    print(f"🔄 Toujours pas de redirection après {sec}s, nouvelle tentative de clic...")
                    click_login_btn(sb)
            except Exception:
                pass
            time.sleep(1)
        else:
            print("❌ Délai d'attente de connexion dépassé")
            sb.save_screenshot("login_timeout.png")
            send_tg("❌ Délai de connexion dépassé", "La page n'a pas changé après l'envoi des identifiants, voir la capture d'écran", photo_path="login_timeout.png")
            return

        # ── 3. Accès à la page de gestion du serveur et injection de l'écouteur ──
        print(f"🔃 Accès à la page de gestion du serveur : {SERVER_URL}")
        sb.open(SERVER_URL)
        time.sleep(5)
        print(f"📄 Page actuelle : {sb.get_current_url()}")
        inject_listener(sb)
        sb.save_screenshot("server_page.png")

        # ── 4. Clic sur les boutons (hors ligne -> Démarrer / en ligne -> bouton jaune Redémarrer)
        power_res = check_server_and_click_power(sb)
        ui_clicked = power_res.get("clicked", False)
        action_type = power_res.get("action_type") or "restart"
        action_detail = power_res.get("detail") or "Aucun bouton correspondant trouvé"
        before_status = power_res.get("status", "unknown")

        time.sleep(4)
        try:
            sb.uc_gui_click_captcha()
        except Exception:
            pass

        # ── 5. Tentative de récupération du token + appel API en double sécurité ──
        token = wait_for_token(sb, timeout=15)
        api_ok = False
        if token:
            api_ok = send_power_api(sb, token, action=action_type)
            if not api_ok and action_type == "restart":
                api_ok = send_power_api(sb, token, action="start")

        if not ui_clicked and not api_ok:
            sb.save_screenshot("api_fail.png")
            send_tg(
                "❌ Échec du redémarrage/démarrage",
                f"État avant action : {before_status}\nNi le clic sur le bouton ni l'API n'ont fonctionné",
                photo_path="api_fail.png"
            )
            return

        # ── 6. Attente du démarrage/redémarrage puis rafraîchissement pour lire le nouveau compte à rebours de 4h ──
        print("🔄 Attente de 12 secondes pour laisser le serveur finir de démarrer/redémarrer...")
        time.sleep(12)
        sb.open(SERVER_URL)
        time.sleep(6)
        sb.save_screenshot("restart_success.png")

        remaining = get_countdown_text(sb)
        after_check = sb.execute_script("""
            (function(){
                var t = document.body.innerText || '';
                if (/En ligne|Online/i.test(t)) return 'Online (en ligne)';
                if (/Hors ligne|Offline/i.test(t)) return 'Offline (hors ligne/en démarrage)';
                return 'inconnu';
            })()
        """)

        countdown_line = f"⏰ Compte à rebours avant coupure : {remaining}" if remaining else "⏰ Compte à rebours avant coupure : en cours d'initialisation (voir la capture d'écran)"
        summary = (
            f"📌 État avant action : {before_status}\n"
            f"🛠 Action effectuée : {action_detail}\n"
            f"🟢 État actuel : {after_check}\n"
            f"{countdown_line}"
        )
        print(f"⏱️ Exécution terminée :\n{summary}")
        send_tg("✅ Redémarrage/démarrage de maintien en ligne réussi !", summary, photo_path="restart_success.png")
        send_discord("Redémarrage réussi ✅", summary)
        write_restart_schedule(remaining=remaining, frozen=False)


if __name__ == "__main__":
    try:
        run_script()
    except Exception as e:
        # Filet de sécurité : même en cas de plantage imprévu, on prévient
        # (sinon le workflow échoue silencieusement, sans aucune trace visible côté Discord/Telegram).
        import traceback
        err_trace = traceback.format_exc()
        print(f"❌ Erreur fatale non gérée : {e}\n{err_trace}")
        send_tg("❌ Erreur fatale", f"{e}")
        send_discord("Erreur fatale ❌", f"```\n{e}\n```")
        raise
