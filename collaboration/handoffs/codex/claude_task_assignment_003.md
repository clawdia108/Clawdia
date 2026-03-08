# Codex Task: Nasazení Leadfeeder/Dealfront tracking scriptu na Behavera web

## Priority: HIGH
## Assigned: 2026-03-08
## Status: PENDING

## Popis
Po registraci na https://www.dealfront.com/pricing-web-visitors/ (14-day trial) potřebujeme nasadit tracking script na behavera.com.

## Co udělat

### 1. Najdi hlavní `index.html` v Behavera webu
- Repo je pravděpodobně v `/Users/josefhofman/Behavera_web_2025/` nebo `/Users/josefhofman/Behaveranewsite/`
- Hledej `index.html` v rootu nebo ve `public/` složce

### 2. Přidej Leadfeeder tracking script
Script se přidá před `</head>` tag. Formát (UNIQUE_ID se vyplní po registraci):

```html
<script>
(function(ss,ex){
  window.ldfdr=window.ldfdr||function(){(ldfdr._q=ldfdr._q||[]).push([].slice.call(arguments));};
  (function(d,s){
    fs=d.getElementsByTagName(s)[0];
    function ce(src){var cs=d.createElement(s);cs.src=src;cs.async=1;fs.parentNode.insertBefore(cs,fs);};
    ce('https://sc.lfeeder.com/lftracker_v1_UNIQUE_ID.js');
  })(document,'script');
})();
</script>
```

### 3. GDPR compliance
Přidej GDPR consent handling:
```javascript
// Call after user accepts cookies
window.ldfdr && window.ldfdr('acceptCookie');
```

### 4. Verify
- Script musí být na VŠECH stránkách (v React to je automaticky přes index.html)
- Po deployi ověř že `ldfdr` objekt existuje v browser console

## Poznámky
- NECOMMITUJ bez schválení Josefem
- UNIQUE_ID dostaneme po registraci na Dealfront
- Script je async, neovlivní load time
- Tento task čeká na to, až Josef dokončí registraci a získá tracking ID

## Výstup
- Upravený `index.html` s tracking scriptem
- Commit message: "feat: add Leadfeeder/Dealfront tracking script for visitor identification"
