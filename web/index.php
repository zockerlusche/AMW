<?php
/* AMW online: Einrichtung (solange keine Konfiguration da ist), Anmeldung, danach dieselbe Workbench-Seite wie am PC
 * (Daten über api.php). */
declare(strict_types=1);
require __DIR__ . '/inc/lib.php';

sitzung_starten();
kopfzeilen(true);

if (isset($_GET['abmelden'])) {
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_ok($_SERVER['HTTP_X_AMW_TOKEN'] ?? null)) abmelden();
    header('Content-Type: application/json; charset=utf-8');
    exit('{}');
}

if (konfig_laden() === null || ($_SESSION['wz']['schritt'] ?? 0) === 4) {
    require __DIR__ . '/inc/einrichtung.php';
    exit;
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
        } catch (RuntimeException $x) {
            $hinweis = 'Speicher nicht erreichbar – bitte später erneut versuchen.';
        }
        if ($hinweis === 'einrichten') $hinweis = '';
        if ($hinweis === '' && angemeldet()) { header('Location: ./', true, 303); exit; }
    }
}

if (angemeldet()) {
    unset($_SESSION['wz']);
    header('Content-Type: text/html; charset=utf-8');
    echo strtr(file_get_contents(__DIR__ . '/inc/seite.html'),
        ['__AMW_TOKEN__' => $_SESSION['csrf'], '__AMW_API__' => 'api.php?weg=']);
    exit;
}

$e = fn(string $s) => htmlspecialchars($s, ENT_QUOTES, 'UTF-8');
$einrichten = $_SESSION['einrichten'] ?? null;          // Konfiguration ohne zweiten Faktor (von Hand angelegt)
if ($einrichten && time() - $einrichten['seit'] > EINRICHTEN_S) { unset($_SESSION['einrichten']); $einrichten = null; }
$csrf = '<input type="hidden" name="csrf" value="' . $e($_SESSION['csrf']) . '">';

seite_anfang('Anmeldung', 'Anmeldung · Sign in');
if ($hinweis !== '') echo '<p class="fehler" role="alert">' . $e($hinweis) . '</p>';
if ($GLOBALS['konfig_warnung'] !== '') echo '<p class="fehler">' . $e($GLOBALS['konfig_warnung']) . '</p>';
if ($einrichten):
    require __DIR__ . '/inc/qr.php';
    $link = 'otpauth://totp/AMW:' . rawurlencode($einrichten['benutzer']) . '?secret=' . $einrichten['geheim'] . '&issuer=AMW&digits=6&period=30'; ?>
  <p><b>Zweiter Faktor einrichten</b> · Set up two-factor</p>
  <ol class="schritte">
    <li>Authenticator-App öffnen (Google Authenticator, Microsoft Authenticator …) → <b>+</b> → <b>QR-Code scannen</b>.</li>
    <li>Diesen Code scannen:</li>
  </ol>
  <div class="qr"><?= qr_svg($link) ?></div>
  <details><summary>Scannen geht nicht? Schlüssel zum Eintippen</summary><code><?= $e(implode(' ', str_split($einrichten['geheim'], 4))) ?></code></details>
  <ol class="schritte" start="3"><li>Die 6-stellige Zahl, die die App jetzt unter „AMW“ zeigt, hier eingeben:</li></ol>
  <label>Zahl aus der App · Authenticator code<input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required autofocus></label>
  <input type="hidden" name="schritt" value="einrichten"><?= $csrf ?>
  <button type="submit">Bestätigen · Confirm</button>
<?php else: ?>
  <label>Benutzer · User<input name="benutzer" autocomplete="username" required autofocus></label>
  <label>Passwort · Password<input name="passwort" type="password" autocomplete="current-password" required></label>
  <label>Zahl aus der App · Authenticator code<input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code"></label>
  <?= $csrf ?>
  <button type="submit">Anmelden · Sign in</button>
<?php endif;
seite_ende();
