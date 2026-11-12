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
try { nachruesten(); } catch (Throwable $x) {}                // ältere Speicher: Spalten für Benutzer ergänzen (einmal je Sitzung)
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!herkunft_ok()) {
        $hinweis = 'Anfrage abgewiesen (Herkunft) – bitte die Seite direkt über https://' . ($_SERVER['HTTP_HOST'] ?? '') . ' öffnen.';
    } elseif (!csrf_ok($_POST['csrf'] ?? null)) {
        $hinweis = 'Formular abgelaufen – bitte Seite neu laden und erneut versuchen.';
    } else {
        try {
            $code = preg_replace('/\s+/', '', (string)($_POST['code'] ?? ''));
            $hinweis = match ($_POST['schritt'] ?? '') {
                'einrichten' => einrichten_abschliessen($code),
                'freischalten' => freischalten_beginnen((string)($_POST['benutzer'] ?? ''), (string)($_POST['freischaltcode'] ?? '')),
                'passwort' => freischalten_passwort((string)($_POST['passwort'] ?? ''), (string)($_POST['passwort2'] ?? '')),
                'bestaetigen' => freischalten_abschliessen($code),
                default => anmelden((string)($_POST['benutzer'] ?? ''), (string)($_POST['passwort'] ?? ''), $code),
            };
        } catch (RuntimeException $x) {
            $hinweis = 'Speicher nicht erreichbar – bitte später erneut versuchen.';
        }
        if ($hinweis === 'einrichten') $hinweis = '';
        if ($hinweis === '' && angemeldet()) { header('Location: ./', true, 303); exit; }
    }
}

$e = fn(string $s) => htmlspecialchars($s, ENT_QUOTES, 'UTF-8');
if (angemeldet() && isset($_SESSION['benutzer']) && !(benutzer_aktuell()['rolle'] ?? null)) {   // angemeldet, noch ohne Rolle
    seite_anfang('Zugang wird geprüft', 'Zugang wird geprüft · Access under review'); ?>
  <p><b>Dein Zugang wird geprüft.</b> Passwort und zweiter Faktor sind eingerichtet. Ein Admin vergibt jetzt deine Rolle und
     die Projekte – danach siehst du hier die Workbench.</p>
  <p class="leise">Your access is being reviewed. An admin will assign your role and projects.</p>
  <button type="button" onclick="location.href='./'">Neu laden · Reload</button>
  <button type="button" class="zweit" data-abmelden>Abmelden · Sign out</button>
  <script>document.querySelector('[data-abmelden]').onclick = e => { e.preventDefault();
    fetch('?abmelden=1', {method: 'POST', headers: {'X-AMW-Token': <?= json_encode($_SESSION['csrf']) ?>}}).then(() => location.href = './'); };</script>
<?php
    seite_ende();
    exit;
}

if (angemeldet()) {
    unset($_SESSION['wz']);
    header('Content-Type: text/html; charset=utf-8');
    echo strtr(file_get_contents(__DIR__ . '/inc/seite.html'),
        ['__AMW_TOKEN__' => $_SESSION['csrf'], '__AMW_API__' => 'api.php?weg=']);
    exit;
}

$einrichten = $_SESSION['einrichten'] ?? null;          // Konfiguration ohne zweiten Faktor (von Hand angelegt)
if ($einrichten && time() - $einrichten['seit'] > EINRICHTEN_S) { unset($_SESSION['einrichten']); $einrichten = null; }
$csrf = '<input type="hidden" name="csrf" value="' . $e($_SESSION['csrf']) . '">';

$frei = freischalten_offen();                           // erstes Anmelden mit Freischalt-Code läuft
$erstes = isset($_GET['erstes']) || ($_POST['schritt'] ?? '') === 'freischalten';
seite_anfang('Anmeldung', 'Anmeldung · Sign in');
if ($hinweis !== '') echo '<p class="fehler" role="alert">' . $e($hinweis) . '</p>';
if ($GLOBALS['konfig_warnung'] !== '') echo '<p class="fehler">' . $e($GLOBALS['konfig_warnung']) . '</p>';
if ($frei && !empty($frei['geheim'])):                   // Schritt 3: zweiten Faktor einrichten
    require __DIR__ . '/inc/qr.php';
    $link = 'otpauth://totp/AMW:' . rawurlencode($frei['name']) . '?secret=' . $frei['geheim'] . '&issuer=AMW&digits=6&period=30'; ?>
  <p><b>Schritt 3 von 3 · Zweiter Faktor</b> · Step 3 of 3 · Two-factor</p>
  <ol class="schritte">
    <li>Authenticator-App öffnen (Google Authenticator, Microsoft Authenticator …) → <b>+</b> → <b>QR-Code scannen</b>.</li>
    <li>Diesen Code scannen:</li>
  </ol>
  <div class="qr"><?= qr_svg($link) ?></div>
  <details><summary>Scannen geht nicht? Schlüssel zum Eintippen</summary><code><?= $e(implode(' ', str_split($frei['geheim'], 4))) ?></code></details>
  <ol class="schritte" start="3"><li>Die 6-stellige Zahl, die die App jetzt unter „AMW“ zeigt, hier eingeben. Zeigt die App eine
    andere Uhrzeit als dein Gerät, stimmt die Zahl nicht – dann die Uhrzeit automatisch stellen lassen.</li></ol>
  <label>Zahl aus der App · Authenticator code<input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required autofocus></label>
  <input type="hidden" name="schritt" value="bestaetigen"><?= $csrf ?>
  <button type="submit">Fertig · Finish</button>
  <p class="leise">Erst mit diesem Schritt ist dein Zugang eingerichtet. Brichst du vorher ab, gilt dein Freischalt-Code weiter.</p>
<?php elseif ($frei):                                    // Schritt 2: Passwort ?>
  <p><b>Schritt 2 von 3 · Passwort</b> · Step 2 of 3 · Password</p>
  <p class="leise">Hallo <?= $e($frei['name']) ?>. Wähle dein Passwort – mindestens <?= PASSWORT_MIN ?> Zeichen. Niemand außer dir kennt es.</p>
  <input type="hidden" name="benutzer" value="<?= $e($frei['name']) ?>" autocomplete="username">
  <label>Neues Passwort · New password<input name="passwort" type="password" minlength="<?= PASSWORT_MIN ?>" autocomplete="new-password" required autofocus></label>
  <label>Noch einmal · Repeat<input name="passwort2" type="password" minlength="<?= PASSWORT_MIN ?>" autocomplete="new-password" required></label>
  <input type="hidden" name="schritt" value="passwort"><?= $csrf ?>
  <button type="submit">Weiter · Next</button>
<?php elseif ($erstes):                                  // Schritt 1: Name und Freischalt-Code ?>
  <p><b>Erstes Anmelden · Schritt 1 von 3</b> · First sign-in · Step 1 of 3</p>
  <p class="leise">Den Freischalt-Code hat dir ein Admin persönlich gegeben. Er gilt nur einmal und nur kurz.</p>
  <label>Benutzer · User<input name="benutzer" autocomplete="username" required autofocus></label>
  <label>Freischalt-Code · Activation code<input name="freischaltcode" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX-XXXX-XXXX" required></label>
  <input type="hidden" name="schritt" value="freischalten"><?= $csrf ?>
  <button type="submit">Weiter · Next</button>
  <p><a href="./">Zurück zur Anmeldung · Back to sign in</a></p>
<?php elseif ($einrichten):
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
  <p><a href="?erstes=1">Erstes Anmelden mit Freischalt-Code · First sign-in with activation code</a></p>
<?php endif;
seite_ende();
