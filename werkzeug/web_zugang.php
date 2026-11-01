<?php
/* Zugang für die AMW-Seite im Netz erzeugen (doc/12-online.md §4). Nur auf der Kommandozeile, am eigenen PC:
 *
 *   php F:\amw\werkzeug\web_zugang.php            → schreibt F:\amw\daten\amw-konfig.php (daten/ ist nicht im Repo)
 *   php F:\amw\werkzeug\web_zugang.php <datei>    → an einen anderen Ort
 *
 * Fragt Benutzer, Passwort (verdeckt), Turso-Adresse und -Schlüssel (verdeckt) ab und schreibt amw-konfig.php.
 * Den zweiten Faktor richtet die Seite beim ersten Anmelden per QR-Code ein (Geheimnis liegt dann im Online-Speicher).
 * Im eigenen Terminal ausführen (verdeckte Eingabe), nicht über Claude Code (`!`).
 */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }

function frage(string $text, bool $verdeckt = false): string {
    fwrite(STDOUT, $text);
    if ($verdeckt && PHP_OS_FAMILY === 'Windows') {
        $w = trim((string)shell_exec('powershell -NoProfile -Command "$p = Read-Host -AsSecureString; '
            . '[Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($p))"'));
        return $w;
    }
    if ($verdeckt) shell_exec('stty -echo');
    $w = trim((string)fgets(STDIN));
    if ($verdeckt) { shell_exec('stty echo'); fwrite(STDOUT, "\n"); }
    return $w;
}

$ziel = $argv[1] ?? dirname(__DIR__) . DIRECTORY_SEPARATOR . 'daten' . DIRECTORY_SEPARATOR . 'amw-konfig.php';
if (!is_dir(dirname($ziel))) { fwrite(STDERR, 'Ordner gibt es nicht: ' . dirname($ziel) . "\n"); exit(1); }
if (file_exists($ziel)) { fwrite(STDERR, "$ziel gibt es schon – erst umbenennen oder löschen.\n"); exit(1); }

$benutzer = frage('Benutzer (frei wählen, nicht der Vorname): ');
if (strlen($benutzer) < 4) { fwrite(STDERR, "Benutzer: mindestens 4 Zeichen\n"); exit(1); }
$pw = frage('Passwort (mind. 14 Zeichen): ', true);
if (strlen($pw) < 14) { fwrite(STDERR, "zu kurz\n"); exit(1); }
if (frage('Passwort wiederholen: ', true) !== $pw) { fwrite(STDERR, "stimmt nicht überein\n"); exit(1); }
$url = frage('Turso-Adresse (leer = später): ');
$token = $url !== '' ? frage('Turso-Schlüssel nur für die Seite (wird nicht angezeigt): ', true) : '';

$inhalt = "<?php\n// AMW online – erzeugt " . gmdate('Y-m-d H:i') . " UTC von werkzeug/web_zugang.php. Nie ins Repo.\nreturn "
    . var_export(['turso_url' => $url, 'turso_token' => $token, 'benutzer' => $benutzer,
        'passwort_hash' => password_hash($pw, PASSWORD_DEFAULT), 'nur_https' => true], true)
    . ";\n";
if (file_put_contents($ziel, $inhalt) === false || !is_file($ziel)) {
    fwrite(STDERR, "FEHLER: konnte $ziel nicht schreiben – nichts angelegt.\n");
    exit(1);
}
$ziel = realpath($ziel);
fwrite(STDOUT, "
geschrieben: $ziel
Diese Datei in den Ordner inc der Seite hochladen. Beim ersten Anmelden (Feld Code leer lassen)
"
    . "zeigt die Seite einen QR-Code für die Authenticator-App.
");
