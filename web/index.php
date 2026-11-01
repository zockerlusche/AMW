<?php
/* AMW online: Anmeldung, danach dieselbe Workbench-Seite wie am PC (Daten über api.php). */
declare(strict_types=1);
require __DIR__ . '/inc/lib.php';

sitzung_starten();
kopfzeilen(true);

if (isset($_GET['abmelden'])) {
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_ok($_SERVER['HTTP_X_AMW_TOKEN'] ?? null)) abmelden();
    header('Content-Type: application/json; charset=utf-8');
    exit('{}');
}

$hinweis = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!herkunft_ok()) {
        $hinweis = 'Anfrage abgewiesen (Herkunft) – bitte die Seite direkt über https://' . ($_SERVER['HTTP_HOST'] ?? '') . ' öffnen.';
    } elseif (!csrf_ok($_POST['csrf'] ?? null)) {
        $hinweis = 'Formular abgelaufen – bitte Seite neu laden und erneut versuchen.';
    } else {
        try {
            $code = preg_replace('/\s+/', '', (string)($_POST['code'] ?? ''));
            $hinweis = ($_POST['schritt'] ?? '') === 'einrichten' ? einrichten_abschliessen($code)
                : anmelden((string)($_POST['benutzer'] ?? ''), (string)($_POST['passwort'] ?? ''), $code);
        } catch (RuntimeException $e) {
            $hinweis = 'Speicher nicht erreichbar – bitte später erneut versuchen.';
        }
        if ($hinweis === 'einrichten') $hinweis = '';
        if ($hinweis === '' && angemeldet()) { header('Location: ./', true, 303); exit; }
    }
}

if (angemeldet()) {
    header('Content-Type: text/html; charset=utf-8');
    echo strtr(file_get_contents(__DIR__ . '/inc/seite.html'),
        ['__AMW_TOKEN__' => $_SESSION['csrf'], '__AMW_API__' => 'api.php?weg=']);
    exit;
}

$e = fn(string $s) => htmlspecialchars($s, ENT_QUOTES, 'UTF-8');
$einrichten = $_SESSION['einrichten'] ?? null;
if ($einrichten && time() - $einrichten['seit'] > EINRICHTEN_S) { unset($_SESSION['einrichten']); $einrichten = null; }
header('Content-Type: text/html; charset=utf-8');
?><!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>AMW · Anmeldung</title>
<style>
:root { --grund: #f3f1ec; --flaeche: #fffdf8; --text: #1d1b16; --leise: #6b665c; --linie: #d9d4c8; --bernstein: #b86e00; --rot: #b3261e; }
@media (prefers-color-scheme: dark) { :root { --grund: #12110e; --flaeche: #1b1a16; --text: #ece8dd; --leise: #9a9486; --linie: #34312a; --bernstein: #f0a020; --rot: #ff6b5e; } }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px; background: var(--grund); color: var(--text);
  font: 15px/1.5 Bahnschrift, "Segoe UI", system-ui, sans-serif; }
form { width: 100%; max-width: 360px; background: var(--flaeche); border: 1px solid var(--linie); border-top: 3px solid var(--bernstein);
  border-radius: 4px; padding: 24px; display: grid; gap: 14px; }
h1 { margin: 0; font-size: 20px; letter-spacing: .06em; } h1 b { color: var(--bernstein); }
.leise { color: var(--leise); font-size: 13px; margin: -8px 0 4px; }
label { display: grid; gap: 4px; font-size: 13px; color: var(--leise); text-transform: uppercase; letter-spacing: .06em; }
input { font: inherit; font-size: 16px; padding: 10px 12px; min-height: 46px; border: 1px solid var(--linie); border-radius: 3px;
  background: var(--grund); color: var(--text); text-transform: none; letter-spacing: normal; }
input:focus { outline: 2px solid var(--bernstein); outline-offset: 1px; }
button { font: 600 14px Bahnschrift, system-ui, sans-serif; letter-spacing: .08em; text-transform: uppercase; min-height: 46px;
  border: 0; border-radius: 3px; background: var(--bernstein); color: #1d1b16; cursor: pointer; }
.fehler { color: var(--rot); font-size: 14px; margin: 0; }
.schritte { margin: 0; padding-left: 20px; font-size: 14px; } .schritte li { margin: 4px 0; }
.qr { display: grid; place-items: center; } .qr svg { width: 100%; max-width: 260px; height: auto; border-radius: 3px; }
details { font-size: 13px; color: var(--leise); } details code { display: block; margin-top: 6px; font: 15px Consolas, monospace; color: var(--text); letter-spacing: .05em; }
p { margin: 0; }
</style>
</head>
<body>
<form method="post" action="./" autocomplete="on">
  <h1><b>AMW</b> Workbench</h1>
  <p class="leise">Anmeldung · Sign in</p>
  <?php if ($hinweis !== ''): ?><p class="fehler" role="alert"><?= $e($hinweis) ?></p><?php endif; ?>
  <?php if ($GLOBALS['konfig_warnung'] !== ''): ?><p class="fehler"><?= $e($GLOBALS['konfig_warnung']) ?></p><?php endif; ?>
<?php if ($einrichten):
    require __DIR__ . '/inc/qr.php';
    $link = 'otpauth://totp/AMW:' . rawurlencode($einrichten['benutzer']) . '?secret=' . $einrichten['geheim']
        . '&issuer=AMW&digits=6&period=30'; ?>
  <p><b>Zweiter Faktor einrichten</b> · Set up two-factor</p>
  <ol class="schritte">
    <li>Authenticator-App öffnen (z. B. Google oder Microsoft Authenticator) → <b>+</b> → <b>QR-Code scannen</b>.</li>
    <li>Diesen Code scannen:</li>
  </ol>
  <div class="qr"><?= qr_svg($link) ?></div>
  <details><summary>Scannen geht nicht? Schlüssel zum Abtippen</summary><code><?= $e(implode(' ', str_split($einrichten['geheim'], 4))) ?></code></details>
  <ol class="schritte" start="3"><li>Die 6-stellige Zahl, die die App jetzt unter „AMW“ zeigt, hier eingeben:</li></ol>
  <label>Code aus der App · Authenticator code<input name="code" inputmode="numeric" pattern="\d{6}" maxlength="6" autocomplete="one-time-code" required autofocus></label>
  <input type="hidden" name="schritt" value="einrichten">
  <input type="hidden" name="csrf" value="<?= $e($_SESSION['csrf']) ?>">
  <button type="submit">Bestätigen · Confirm</button>
  <p class="leise">Gilt 10 Minuten. Danach ist die Einrichtung gesperrt – ab dann Passwort + Zahl aus der App.</p>
<?php else: ?>
  <label>Benutzer · User<input name="benutzer" autocomplete="username" required autofocus></label>
  <label>Passwort · Password<input name="passwort" type="password" autocomplete="current-password" required></label>
  <label>Code aus der App · Authenticator code<input name="code" inputmode="numeric" pattern="\d{6}" maxlength="6" autocomplete="one-time-code"></label>
  <p class="leise">Beim allerersten Anmelden leer lassen – dann kommt ein QR-Code für die App.</p>
  <input type="hidden" name="csrf" value="<?= $e($_SESSION['csrf']) ?>">
  <button type="submit">Anmelden · Sign in</button>
<?php endif; ?>
</form>
</body>
</html>
