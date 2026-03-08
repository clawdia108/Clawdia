# Clawdia Remote Access — Ovládej Mac odkudkoli

## Jak to funguje
NordVPN Meshnet vytváří šifrovaný tunel mezi Macem a iPadem. Funguje přes WiFi, mobilní data, z hotelu, odkudkoli na světě. Stačí mít na obou zařízeních zapnutý NordVPN s Meshnet.

---

## Přístupové údaje

| Služba | Adresa | Heslo | K čemu |
|--------|--------|-------|--------|
| **VS Code** | `http://100.101.169.255:8080/` | `clawdia2026` | Editor + terminál v prohlížeči Safari |
| **Dashboard** | `http://100.101.169.255:9090/` | žádné | Clawdia system health, agents, pipeline |
| **SSH** | `ssh josefhofman@100.101.169.255` | systémové heslo | Terminál přes Termius / Blink app |
| **Screen Sharing** | VNC na `100.101.169.255` | systémové heslo | Celý desktop Macu |

---

## Co kde použít

### VS Code v prohlížeči (nejčastější)
- Otevři Safari na iPadu → `http://100.101.169.255:8080/`
- Zadej heslo `clawdia2026`
- Máš plný VS Code s terminálem, otevřený na ~/Clawdia
- Funguje skvěle i na mobilních datech

### Clawdia Dashboard
- Otevři Safari → `http://100.101.169.255:9090/`
- Vidíš: stav agentů, pipeline, scorecard, costs
- Auto-refresh každých 30 sekund
- Žádné heslo nepotřebuješ

### SSH Terminál (rychlé příkazy)
- Stáhni si **Termius** nebo **Blink Shell** z App Store
- Připoj se: `ssh josefhofman@100.101.169.255`
- Užitečné příkazy:
  - `cd ~/Clawdia && python3 scripts/lusha_enricher.py --status`
  - `python3 scripts/agent_dispatcher.py --status`
  - `python3 scripts/health_server.py --check`
  - `launchctl list | grep clawdia`

### Screen Sharing (celý desktop)
- Stáhni si **VNC Viewer** z App Store
- Připoj se na `100.101.169.255`
- Vidíš celý Mac desktop — VS Code, Chrome, všechno
- Pozor: na mobilních datech je pomalejší (přenáší obraz)

---

## Než začneš

### Checklist před připojením
1. Na Macu musí být zapnutý NordVPN s Meshnet
2. Na iPadu musí být zapnutý NordVPN s Meshnet
3. Mac musí být zapnutý (ne v sleep mode)
4. Oba musí být online (WiFi nebo mobilní data)

### Doporučené iPad appky
| App | Zdarma | K čemu |
|-----|--------|--------|
| **Safari** | ano | VS Code + Dashboard |
| **Termius** | ano | SSH terminál |
| **VNC Viewer** | ano | Screen Sharing / celý desktop |

---

## Rychlé Clawdia příkazy (přes SSH nebo VS Code terminál)

```bash
# System status
python3 scripts/health_server.py --check

# Agent dispatcher stav
python3 scripts/agent_dispatcher.py --status

# LUSHA kredity
python3 scripts/lusha_enricher.py --status

# Bus inbox — čekající zprávy
python3 scripts/agent_runner.py --status

# Všechny běžící služby
launchctl list | grep clawdia

# Ruční spuštění agentů
python3 scripts/agent_dispatcher.py          # dispatch úkolů
python3 scripts/agent_runner.py --once       # zpracuj bus zprávy

# Pipeline
python3 scripts/pipedrive_lead_scorer.py     # score deals

# Logy
tail -50 ~/Clawdia/logs/agent-runner-launchd.log
tail -50 ~/Clawdia/logs/orchestrator.log
```

---

## Troubleshooting

| Problém | Řešení |
|---------|--------|
| Nejde se připojit | Zkontroluj že NordVPN Meshnet je zapnutý na obou zařízeních |
| VS Code se nenačítá | `launchctl list | grep code-server` — pokud neběží: `launchctl load ~/Library/LaunchAgents/com.clawdia.code-server.plist` |
| Dashboard nefunguje | `launchctl list | grep health-server` — restart: `launchctl unload && load` plist |
| SSH odmítá spojení | Ověř že Remote Login je zapnutý: System Settings → General → Sharing |
| VNC pomalé | Normální na mobilních datech. Použij raději VS Code v prohlížeči |
| Mac spí | Nastav: System Settings → Energy → Prevent automatic sleeping |

---

*Meshnet IP Macu: 100.101.169.255*
*Lokální IP (stejná WiFi): 192.168.0.105*
*Vytvořeno: 2026-03-08*
