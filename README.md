# 🎮 Minestrator-Restart

[Minestrator](https://minestrator.com) propose un hébergement gratuit de serveur Minecraft, mais coupe le serveur de force **toutes les 4 heures**. Ce projet contourne cette limite en redémarrant le serveur automatiquement, pour le garder en ligne en continu.

Une **plage de maintenance silencieuse de 1h à 6h du matin (heure de Paris)** est respectée : pendant cette plage, le script ne relance pas le serveur (voir plus bas).

## 🔐 Configuration des Secrets

**Settings → Secrets and variables → Actions → New repository secret**, ajouter :

| Nom du secret | Obligatoire | Description | Exemple |
|---|---|---|---|
| `MINESTRATOR_ACCOUNT` | ✅ Oui | 🧾 Email + mot de passe Minestrator, séparés par une virgule | `monemail@example.com,monmotdepasse` |
| `MINESTRATOR_SERVER_ID` | ✅ Oui | 🖥️ ID du serveur | `123456` |
| `MINESTRATOR_AUTH` | ✅ Oui | 🔑 Token d'autorisation API, avec le préfixe Bearer | `Bearer xxxxxxxxxxxxxxxx` |
| `GOST_PROXY` | ✅ Oui | 🌐 Adresse du proxy Gost — les IP de GitHub Actions sont détectées comme VPN et bloquent la connexion, ce secret est donc indispensable | `socks5://user:pass@1.2.3.4:1080` |
| `TG_BOT` | ⬜ Optionnel | 📨 Notification Telegram : Chat ID et Bot Token séparés par une virgule | `987654321,123456:AAFxxx` |
| `DISCORD_WEBHOOK` | ⬜ Optionnel | 📣 URL d'un webhook Discord pour recevoir les notifications de redémarrage dans un salon | `https://discord.com/api/webhooks/xxx/yyy` |

> ✅ Le dépôt étant public, plus aucun identifiant n'est écrit en clair dans `restart_minestrator.py` : tout passe par les secrets GitHub ci-dessus.

## 🕐 Horaires d'exécution

Le workflow tourne **toutes les heures** (`0 * * * *`). À chaque exécution, le script vérifie l'heure actuelle à Paris :

- **Entre 1h et 6h du matin** : le script ne clique pas sur Redémarrer/Démarrer. Le serveur peut donc s'éteindre tout seul au bout de 4h et rester hors ligne — c'est voulu.
- **À partir de 6h** : le script reprend normalement et redémarre/relance le serveur comme d'habitude.

(Le calcul utilise le fuseau `Europe/Paris`, donc l'heure d'été/hiver est gérée automatiquement.)

## 📣 Webhook Discord

Oui, c'est possible : en renseignant le secret `DISCORD_WEBHOOK`, le script envoie automatiquement un message dans le salon Discord relié au webhook à chaque exécution (succès, échec, ou "pas d'action pendant la plage 1h-6h").

En plus du webhook, le script écrit un petit fichier `restart_schedule.json` à la racine du dépôt avec l'heure estimée du prochain arrêt forcé (déduite du compte à rebours affiché par Minestrator) :

```json
{
  "next_restart_utc": "2026-11-19T18:42:00Z",
  "updated_utc": "2026-11-19T14:40:03Z",
  "frozen": false
}
```

Ce fichier est commité automatiquement par le workflow, ce qui le rend accessible publiquement (si le dépôt est public) via son URL "raw" GitHub, par exemple :
`https://raw.githubusercontent.com/<user>/<repo>/main/restart_schedule.json`

## 🧩 Annonces in-game avec Skript

Un plugin Minestrator (Skript) ne peut pas "recevoir" un webhook Discord entrant (les webhooks Discord sont à sens unique : vers Discord uniquement). La solution retenue est donc :

1. Le script Python calcule `next_restart_utc` et le publie dans `restart_schedule.json` (voir ci-dessus).
2. Un script Skript, **avec l'addon [SkBee](https://github.com/ShaneBeeStudios/SkBee)** (qui fournit les effets HTTP GET), interroge cette URL toutes les minutes.
3. Le script Skript compare l'heure récupérée à l'heure actuelle du serveur et déclenche :
   - une annonce à **5 minutes** avant `next_restart_utc`,
   - une annonce finale à l'heure du redémarrage.
4. Comme le workflow GitHub ne tourne pas en continu, l'heure `next_restart_utc` est mémorisée dans une **variable Skript persistante** (`{restart::next}`), ce qui permet au serveur de continuer à annoncer correctement même entre deux exécutions du workflow.

Voir `skript/announce_restart.sk` fourni dans ce dépôt pour un exemple fonctionnel (à adapter au nom exact des options de ton addon HTTP).
