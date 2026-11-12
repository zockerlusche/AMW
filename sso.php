<?php
/* AMW online: Firmen-Anmeldung (OpenID Connect, Stufe R2) – Bibliothek in inc/sso.php.
 *   sso.php                 → zum Anbieter (Knopf „Mit Firmenkonto anmelden“)
 *   sso.php?code=…&state=…  → zurück vom Anbieter (Redirect-URI, beim Anbieter einzutragen)
 *   sso.php?einrichten      → Geheimnis oder Zertifikat in die Konfiguration (nur System-Admin, angemeldet)
 */
declare(strict_types=1);
require __DIR__ . '/inc/lib.php';
require __DIR__ . '/inc/sso.php';

sitzung_starten();
kopfzeilen(true);
if (konfig_laden() === null) { header('Location: ./', true, 303); exit; }
try { nachruesten(); } catch (Throwable $x) {}

$e = fn(string $s) => htmlspecialchars($s, ENT_QUOTES, 'UTF-8');

/** Meldung auf der Anmeldeseite (eigene kleine Seite, damit sie auch ohne Sitzungs-Cookie erscheint). */
function sso_meldung(string $text): never {
    $e = fn(string $s) => htmlspecialchars($s, ENT_QUOTES, 'UTF-8');
    seite_anfang('Firmen-Anmeldung', 'Firmen-Anmeldung · Company sign-in');
    echo '<p class="fehler" role="alert">' . $e($text) . '</p>'
        . '<p><a href="./">Zurück zur Anmeldung · Back to sign in</a></p>';
    seite_ende();
    exit;
}

/* --- Geheimnis eintragen (System-Admin) ----------------------------------------------------------------------- */
if (isset($_GET['einrichten'])) {
    $ich = isset($_SESSION['benutzer']) ? benutzer_aktuell() : null;
    $admin = angemeldet() && (!empty($_SESSION['zugang']) || ($ich['rolle'] ?? null) === 'system_admin');
    if (!$admin) sso_meldung('Das Geheimnis der Firmen-Anmeldung trägt nur ein System-Admin ein – bitte erst anmelden.');
    $hinweis = '';
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!herkunft_ok() || !csrf_ok($_POST['csrf'] ?? null)) $hinweis = 'Formular abgelaufen – bitte Seite neu laden.';
        else {
            $r = sso_zugang_speichern((string)($_POST['art'] ?? ''), (string)($_POST['geheimnis'] ?? ''),
                                      (string)($_POST['zertifikat'] ?? ''), (string)($_POST['schluessel'] ?? ''));
            if ($r === '' || $r === 'inc') {
                header('Location: sso.php?einrichten=' . ($r === 'inc' ? 'inc' : 'ok'), true, 303);
                exit;
            }
            $hinweis = $r;
        }
    }
    sso_stand_melden();
    $s = sso_einst();
    $art = sso_zugang_art();
    $pruef = '';
    if ($s['aussteller'] !== '') {
        try { sso_anbieter($s['aussteller']); $pruef = 'ok'; } catch (Throwable $x) { $pruef = $x->getMessage(); }
    }
    seite_anfang('Firmen-Anmeldung', 'Firmen-Anmeldung einrichten · Set up company sign-in', 'sso.php?einrichten');
    if ($hinweis !== '') echo '<p class="fehler" role="alert">' . $e($hinweis) . '</p>';
    if (($_GET['einrichten'] ?? '') === 'ok') echo '<p class="gut" role="status">Gespeichert · Saved</p>';
    if (($_GET['einrichten'] ?? '') === 'inc') echo '<p class="fehler">Gespeichert, aber im Web-Ordner (inc) – der nächste Deploy löscht es.</p>'; ?>
  <p class="leise">Aussteller und Client-ID stellst du am PC ein (Einstellungen › Firmen-Anmeldung). Hier kommt nur das Geheimnis
    hin – es landet in der Konfigurationsdatei beim Webhoster außerhalb des Web-Ordners und wird nie wieder angezeigt.</p>
  <p><b>Aussteller</b> · <span class="leise"><?= $e($s['aussteller'] ?: '– am PC eintragen –') ?></span><br>
     <b>Client-ID</b> · <span class="leise"><?= $e($s['client_id'] ?: '– am PC eintragen –') ?></span><br>
     <b>Redirect-URI</b> · <span class="leise"><?= $e(sso_rueckweg()) ?></span><br>
     <b>Anbieter</b> · <?= $pruef === 'ok' ? '<span class="gut">erreichbar, Aussteller stimmt</span>'
        : ($pruef === '' ? '<span class="leise">–</span>' : '<span class="fehler">' . $e($pruef) . '</span>') ?><br>
     <b>Gespeichert</b> · <?= $art === '' ? '<span class="fehler">nichts – der Knopf erscheint erst danach</span>'
        : '<span class="gut">' . ($art === 'zertifikat' ? 'Zertifikat' : 'Geheimnis (Client-Secret)') . '</span>' ?></p>
  <label><span><input type="radio" name="art" value="geheimnis" style="width:auto;min-height:0" <?= $art !== 'zertifikat' ? 'checked' : '' ?>> Geheimnis · Client secret</span>
    <input name="geheimnis" type="password" autocomplete="off" spellcheck="false" placeholder="<?= $art === 'geheimnis' ? 'gespeichert – neu eintragen zum Ersetzen' : 'Wert (Value) aus dem Portal' ?>"></label>
  <label><span><input type="radio" name="art" value="zertifikat" style="width:auto;min-height:0" <?= $art === 'zertifikat' ? 'checked' : '' ?>> Zertifikat · Certificate (PEM)</span>
    <textarea name="zertifikat" rows="3" spellcheck="false" placeholder="-----BEGIN CERTIFICATE-----" style="font:12px Consolas,monospace;width:100%"></textarea>
    <textarea name="schluessel" rows="3" spellcheck="false" placeholder="-----BEGIN PRIVATE KEY-----" style="font:12px Consolas,monospace;width:100%"></textarea></label>
  <input type="hidden" name="csrf" value="<?= $e($_SESSION['csrf']) ?>">
  <button type="submit">Speichern · Save</button>
  <?php if ($art !== ''): ?><button type="submit" name="art" value="entfernen" class="zweit" formnovalidate>Entfernen · Remove</button><?php endif ?>
  <p><a href="./">Zurück zur Workbench · Back</a></p>
<?php
    seite_ende();
    exit;
}

/* --- Zurück vom Anbieter --------------------------------------------------------------------------------------- */
if (isset($_GET['state']) || isset($_GET['error'])) {
    try {
        sso_zurueck($_GET, $_COOKIE[sso_cookie_name()] ?? null);
    } catch (SsoFehler $x) {
        $m = $x->getMessage();                              // Meldungen für den Benutzer sind zweisprachig, technische nur deutsch
        sso_meldung(str_contains($m, ' · ') ? $m : 'Anmeldung mit Firmenkonto fehlgeschlagen · Company sign-in failed: ' . $m);
    } catch (RuntimeException $x) {
        sso_meldung('Speicher nicht erreichbar – bitte später erneut versuchen. · Storage unreachable – please try later.');
    }
    // Das Sitzungs-Cookie ist SameSite=Strict: auf eine Weiterleitung hin, die beim Anbieter begann, schickt der Browser
    // es nicht mit. Ein eigener Schritt von dieser Seite aus (meta refresh) ist eine Navigation von hier – dann schon.
    header('Content-Type: text/html; charset=utf-8');
    echo '<!doctype html><html lang="de"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=./">'
        . '<meta name="robots" content="noindex, nofollow"><title>AMW</title></head><body style="font:15px system-ui;padding:24px">'
        . '<p>Angemeldet · Signed in – <a href="./">weiter · continue</a></p></body></html>';
    exit;
}

/* --- Zum Anbieter ---------------------------------------------------------------------------------------------- */
try {
    header('Location: ' . sso_start(), true, 303);
} catch (SsoFehler $x) {
    sso_meldung($x->getMessage());
} catch (RuntimeException $x) {
    sso_meldung('Speicher nicht erreichbar – bitte später erneut versuchen.');
}
