<?php
/* Einrichtungs-Assistent (doc/online.md §2): erscheint nur, solange es keine Konfiguration gibt.
 *
 * 1. Turso-Adresse + Schlüssel – wer den Schlüssel hat, darf einrichten (ein Fremder, der die frische Seite zuerst
 *    aufruft, hat ihn nicht). Die Seite prüft die Verbindung und legt ihre Tabellen an.
 * 2. Benutzer + Passwort festlegen.
 * 3. Zweiter Faktor: QR-Code scannen und die erste Zahl bestätigen (ist schon einer eingerichtet, etwa nach einem
 *    Umzug zu einem anderen Hoster: die Zahl aus der vorhandenen App).
 * Danach schreibt die Seite ihre Konfiguration selbst außerhalb des Deploy-Ordners und meldet an.
 */
declare(strict_types=1);

const WZ_DAUER_S = 1800;
const WZ_CODE_VERSUCHE = 5;

$e = fn(string $s) => htmlspecialchars($s, ENT_QUOTES, 'UTF-8');
$wz = $_SESSION['wz'] ?? ['schritt' => 1, 'seit' => time()];
if (time() - $wz['seit'] > WZ_DAUER_S) $wz = ['schritt' => 1, 'seit' => time()];
$hinweis = '';
$gut = '';

/** Zugang aus Schritt 1; für die Probe am PC (nur 127.0.0.1) kann AMW_PROBE_SQLITE eine lokale Datei setzen. */
$zugang_von = function (string $url, string $token): ?array {
    if (ist_lokal() && getenv('AMW_PROBE_SQLITE')) return ['sqlite' => getenv('AMW_PROBE_SQLITE')];
    $u = turso_url($url);
    return $u && $token !== '' ? ['turso_url' => $u, 'turso_token' => $token] : null;
};

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $schritt = (string)($_POST['schritt'] ?? '');
    if (!herkunft_ok()) {
        $hinweis = 'Anfrage abgewiesen (Herkunft) – bitte die Seite direkt über https://' . ($_SERVER['HTTP_HOST'] ?? '') . ' öffnen.';
    } elseif (!csrf_ok($_POST['csrf'] ?? null)) {
        $hinweis = 'Formular abgelaufen – bitte erneut versuchen.';
    } elseif ($schritt === 'zurueck') {
        $wz = ['schritt' => 1, 'seit' => time()];
    } elseif ($schritt === 'wz1') {
        $zugang = $zugang_von((string)($_POST['url'] ?? ''), trim((string)($_POST['token'] ?? '')));
        if ($zugang === null) {
            $hinweis = 'Die Adresse muss eine Turso-Adresse sein (libsql://….turso.io), der Schlüssel darf nicht leer sein.';
        } else {
            try {
                sql(array_map(fn($s) => [$s, []], ONLINE_SCHEMA), $zugang);
                $vorhanden = zustand_lesen('totp_geheim', $zugang) !== null;
                $pc = zustand_lesen('pc_gesehen_utc', $zugang);
                $wz = ['schritt' => 2, 'seit' => $wz['seit'], 'zugang' => $zugang, 'faktor_vorhanden' => $vorhanden, 'pc' => $pc];
                session_regenerate_id(true);
            } catch (RuntimeException $x) {
                $hinweis = match (true) {
                    in_array($x->getCode(), [400, 401, 403], true) => 'Der Turso-Schlüssel wird abgelehnt – bitte einen gültigen Schlüssel mit Lese- und Schreibrecht für diese Datenbank.',
                    $x->getCode() === 404 => 'Diese Turso-Datenbank gibt es nicht – bitte die Adresse prüfen.',
                    default => 'Turso ist nicht erreichbar (' . $x->getMessage() . ') – bitte Adresse prüfen und erneut versuchen.',
                };
            }
        }
    } elseif ($schritt === 'wz2' && ($wz['schritt'] ?? 1) >= 2) {
        $benutzer = trim((string)($_POST['benutzer'] ?? ''));
        $pw = (string)($_POST['passwort'] ?? '');
        if (!preg_match('/^[A-Za-z0-9._@-]{4,40}$/', $benutzer)) $hinweis = 'Benutzer: 4 bis 40 Zeichen (Buchstaben, Ziffern, . _ - @).';
        elseif (mb_strlen($pw) < 14) $hinweis = 'Das Passwort braucht mindestens 14 Zeichen.';
        elseif ($pw !== (string)($_POST['passwort2'] ?? '')) $hinweis = 'Die beiden Passwörter stimmen nicht überein.';
        else {
            $wz['schritt'] = 3;
            $wz['benutzer'] = $benutzer;
            $wz['hash'] = password_hash($pw, PASSWORD_DEFAULT);
            $wz['geheim'] = $wz['faktor_vorhanden'] ? null : neues_geheim();
            $wz['fehlversuche'] = 0;
        }
    } elseif ($schritt === 'wz3' && ($wz['schritt'] ?? 1) === 3) {
        $code = preg_replace('/\s+/', '', (string)($_POST['code'] ?? ''));
        $zugang = $wz['zugang'];
        try {
            $geheim = $wz['geheim'] ?? zustand_lesen('totp_geheim', $zugang);
            $schritt_ok = null;
            if ($geheim !== null && preg_match('/^\d{6}$/', $code)) {
                $jetzt = intdiv(time(), 30);
                foreach ([$jetzt, $jetzt - 1, $jetzt + 1] as $s) if (hash_equals(totp($geheim, $s), $code)) { $schritt_ok = $s; break; }
            }
            if ($schritt_ok === null) {
                $wz['fehlversuche']++;
                $hinweis = 'Die Zahl stimmt nicht – bitte die aktuelle 6-stellige Zahl aus der App unter „AMW“.';
                if ($wz['fehlversuche'] >= WZ_CODE_VERSUCHE) { $wz = ['schritt' => 1, 'seit' => time()]; $hinweis = 'Zu viele falsche Zahlen – bitte von vorn beginnen.'; }
            } else {
                $anw = [["INSERT INTO zustand (schluessel, wert) VALUES ('totp_letzt', ?) ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert", [(string)$schritt_ok]]];
                if ($wz['geheim'] !== null) array_unshift($anw, ["INSERT INTO zustand (schluessel, wert) VALUES ('totp_geheim', ?) ON CONFLICT(schluessel) DO NOTHING", [$wz['geheim']]]);
                sql($anw, $zugang);
                if (zustand_lesen('totp_geheim', $zugang) !== $geheim) {
                    $wz = ['schritt' => 1, 'seit' => time()];
                    $hinweis = 'Inzwischen wurde ein anderer zweiter Faktor eingerichtet – bitte von vorn beginnen.';
                } else {
                    $ort = konfig_schreiben($zugang + ['benutzer' => $wz['benutzer'], 'passwort_hash' => $wz['hash'], 'nur_https' => true]);
                    if ($ort === '') {
                        $hinweis = 'Die Seite darf beim Hoster keine Datei anlegen (weder neben dem Web-Ordner noch in inc). Bitte beim Hoster die Schreibrechte prüfen.';
                    } else {
                        unset($_SESSION['wz']);
                        sitzung_anmelden();
                        if ($ort === 'aussen') { header('Location: ./', true, 303); exit; }
                        $wz = ['schritt' => 4, 'seit' => time()];      // gespeichert, aber im Web-Ordner: deutlich sagen
                    }
                }
            }
        } catch (RuntimeException $x) {
            $hinweis = 'Turso ist gerade nicht erreichbar – bitte gleich noch einmal.';
        }
    }
}
$_SESSION['wz'] = $wz;

$stufe = fn(int $n) => '<div class="stufe">' . str_repeat('<span class="an"></span>', $n) . str_repeat('<span></span>', 3 - $n) . '</div>';
seite_anfang('Einrichtung', 'Einrichtung · Setup');
echo $stufe(min($wz['schritt'], 3));
if ($hinweis !== '') echo '<p class="fehler" role="alert">' . $e($hinweis) . '</p>';
$csrf = '<input type="hidden" name="csrf" value="' . $e($_SESSION['csrf']) . '">';

if ($wz['schritt'] === 1): ?>
  <p><b>Schritt 1 von 3 · Online-Speicher verbinden</b></p>
  <p class="leise">Diese Seite ist noch nicht eingerichtet. Du brauchst eine Turso-Datenbank (kostenlos auf turso.tech):
    Adresse der Datenbank und einen Schlüssel („Create Token“) mit Lese- und Schreibrecht. Den Schlüssel kennt nur, wem die
    Datenbank gehört – darum kann niemand sonst diese Seite einrichten.</p>
  <label>Turso-Adresse · Database URL<input name="url" placeholder="libsql://name-konto.….turso.io" autocomplete="off" required autofocus></label>
  <label>Turso-Schlüssel · Token<input name="token" type="password" autocomplete="off" required></label>
  <input type="hidden" name="schritt" value="wz1"><?= $csrf ?>
  <button type="submit">Verbinden · Connect</button>
<?php elseif ($wz['schritt'] === 2): ?>
  <p class="gut">✓ Turso verbunden<?= $wz['pc'] ? ' · PC zuletzt ' . $e(substr((string)$wz['pc'], 0, 16)) . ' UTC' : ' · vom PC noch keine Daten (am PC: amw web einrichten)' ?></p>
  <p><b>Schritt 2 von 3 · Zugang festlegen</b></p>
  <label>Benutzer · User<input name="benutzer" autocomplete="username" minlength="4" maxlength="40" required autofocus></label>
  <label>Passwort · Password (mind. 14 Zeichen)<input name="passwort" type="password" autocomplete="new-password" minlength="14" required></label>
  <label>Passwort wiederholen · Repeat<input name="passwort2" type="password" autocomplete="new-password" minlength="14" required></label>
  <input type="hidden" name="schritt" value="wz2"><?= $csrf ?>
  <button type="submit">Weiter · Next</button>
<?php elseif ($wz['schritt'] === 3):
    if ($wz['geheim'] !== null):
        require __DIR__ . '/qr.php';
        $link = 'otpauth://totp/AMW:' . rawurlencode($wz['benutzer']) . '?secret=' . $wz['geheim'] . '&issuer=AMW&digits=6&period=30'; ?>
  <p><b>Schritt 3 von 3 · Zweiter Faktor</b></p>
  <ol class="schritte">
    <li>Auf dem Handy eine Authenticator-App öffnen (Google Authenticator, Microsoft Authenticator …).</li>
    <li><b>+</b> antippen → <b>QR-Code scannen</b> → diesen Code scannen:</li>
  </ol>
  <div class="qr"><?= qr_svg($link) ?></div>
  <details><summary>Scannen geht nicht? Schlüssel zum Eintippen</summary><code><?= $e(implode(' ', str_split($wz['geheim'], 4))) ?></code></details>
  <ol class="schritte" start="3"><li>Die 6-stellige Zahl, die die App jetzt unter „AMW“ zeigt, hier eingeben:</li></ol>
<?php else: ?>
  <p><b>Schritt 3 von 3 · Zweiter Faktor</b></p>
  <p class="leise">Für diese Datenbank ist schon ein zweiter Faktor eingerichtet (z. B. von einer früheren Installation).
    Bitte die aktuelle Zahl aus deiner Authenticator-App unter „AMW“ eingeben. Neues Handy? Am PC: <code>amw web zweitfaktor-neu</code>, dann von vorn.</p>
<?php endif; ?>
  <label>Zahl aus der App · Authenticator code<input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required autofocus></label>
  <input type="hidden" name="schritt" value="wz3"><?= $csrf ?>
  <button type="submit">Einrichtung abschließen · Finish</button>
<?php else: ?>
  <p class="gut">✓ Eingerichtet – du bist angemeldet.</p>
  <p class="fehler">Achtung: Der Hoster erlaubt der Seite nicht, ihre Konfiguration außerhalb des Web-Ordners zu speichern.
    Sie liegt jetzt in <code>inc/</code> (von außen gesperrt), geht aber beim nächsten Deploy verloren – dann erscheint
    diese Einrichtung wieder (mit vorhandenem zweiten Faktor dauert sie eine Minute).</p>
  <p><a href="./">Weiter zur Workbench</a></p>
<?php endif;
if ($wz['schritt'] === 2 || $wz['schritt'] === 3) {
    echo '<button type="submit" name="schritt" value="zurueck" formnovalidate style="background:none;color:var(--leise);border:1px solid var(--linie)">Von vorn · Start over</button>';
}
seite_ende();
