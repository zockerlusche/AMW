<?php
/* AMW online (Stufe 2, doc/12-online.md): gemeinsame Teile für index.php, api.php und die Einrichtung.
 *
 * Konfiguration (Turso-Zugang, Benutzer, Passwort-Hash) schreibt der Einrichtungs-Assistent selbst – außerhalb des
 * Web-/Deploy-Ordners, nie ins Repo. Speicher: Turso über HTTP (/v2/pipeline) oder für Proben am PC eine SQLite-Datei.
 */
declare(strict_types=1);

/* Einstellungen der Online-Seite (Zahnrad „Online-Seite“): Vorgabe, kleinster, größter Wert – dieselben wie
 * amw/abgleich.py WEB_EINSTELLUNGEN. Gespeichert im Online-Speicher, zustand „web_einstellungen“. */
const WEB_EINSTELLUNGEN = ['leerlauf_min' => [30, 5, 240], 'hoechstens_h' => [12, 1, 72], 'fehl_je_ip' => [5, 3, 20],
                           'fehl_gesamt' => [20, 5, 200]];

/** Alle Werte der Online-Seite (geprüft). In der Sitzung 5 min zwischengespeichert, damit nicht jede Anfrage den
 *  Speicher fragt; $frisch = true liest neu (Seite „Einstellungen“). */
function web_einst_alle(bool $frisch = false): array {
    static $d = null;
    if ($d === null || $frisch) {
        if (!$frisch && isset($_SESSION['web_einst']) && time() - $_SESSION['web_einst']['zeit'] < 300) $roh = $_SESSION['web_einst']['werte'];
        else {
            try { $roh = json_decode((string)zustand_lesen('web_einstellungen'), true) ?: []; } catch (RuntimeException $x) { $roh = []; }
            if (session_status() === PHP_SESSION_ACTIVE) $_SESSION['web_einst'] = ['zeit' => time(), 'werte' => $roh];
        }
        $d = [];
        foreach (WEB_EINSTELLUNGEN as $k => [$vorgabe, $lo, $hi]) {
            $v = isset($roh[$k]) ? (int)$roh[$k] : $vorgabe;
            $d[$k] = $v >= $lo && $v <= $hi ? $v : $vorgabe;
        }
    }
    return $d;
}

function web_einst(string $k): int {
    return web_einst_alle()[$k];
}
const SCHREIBEN_JE_STUNDE = 120;     // Briefkasten-Zeilen je Stunde

/* Tabellen im Online-Speicher – dieselben wie amw/abgleich.py SCHEMA (ein Test vergleicht beide). */
const ONLINE_SCHEMA = [
    "CREATE TABLE IF NOT EXISTS ansicht (weg TEXT PRIMARY KEY, inhalt TEXT NOT NULL, pruef TEXT NOT NULL, stand_utc TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS eingang (id INTEGER PRIMARY KEY, zeit_utc TEXT NOT NULL, weg TEXT NOT NULL, daten TEXT NOT NULL, ip TEXT, status TEXT NOT NULL DEFAULT 'neu', ergebnis TEXT, erledigt_utc TEXT)",
    "CREATE INDEX IF NOT EXISTS eingang_neu ON eingang (status, id)",
    "CREATE TABLE IF NOT EXISTS versuch (id INTEGER PRIMARY KEY, zeit_utc TEXT NOT NULL, ip TEXT, ok INTEGER NOT NULL)",
    "CREATE INDEX IF NOT EXISTS versuch_zeit ON versuch (zeit_utc)",
    "CREATE TABLE IF NOT EXISTS zustand (schluessel TEXT PRIMARY KEY, wert TEXT)",
];

/** Orte außerhalb des Web-/Deploy-Ordners: dort löscht ein Git-Deploy nichts und niemand kann sie abrufen. */
function konfig_orte(): array {
    $wurzel = rtrim(str_replace(chr(92), '/', (string)($_SERVER['DOCUMENT_ROOT'] ?? dirname(__DIR__))), '/');
    $orte = [];
    if ($e = getenv('AMW_KONFIG')) $orte[] = $e;
    $orte[] = (($p = strpos($wurzel, '/public_html')) !== false ? substr($wurzel, 0, $p) : dirname($wurzel)) . '/amw-konfig.php';
    if (($p = strpos($wurzel, '/domains/')) !== false) $orte[] = substr($wurzel, 0, $p) . '/amw-konfig.php';  // Benutzer-Stamm
    return array_values(array_unique($orte));
}

$GLOBALS['konfig_warnung'] = '';

/** Konfiguration oder null (dann zeigt index.php den Einrichtungs-Assistenten). Eine von Hand nach inc/ hochgeladene
 *  Datei wird beim ersten Aufruf nach außerhalb des Deploy-Ordners verschoben – der nächste Deploy löscht inc/. */
function konfig_laden(): ?array {
    static $k = false;
    if ($k !== false) return $k;
    foreach (konfig_orte() as $ort) if (is_file($ort)) return $k = konfig_gueltig(require $ort);
    $hochgeladen = __DIR__ . '/amw-konfig.php';
    if (!is_file($hochgeladen)) return $k = null;
    $k = konfig_gueltig(require $hochgeladen);
    if ($k !== null && konfig_schreiben_roh(file_get_contents($hochgeladen)) === 'aussen') @unlink($hochgeladen);
    elseif ($k !== null) $GLOBALS['konfig_warnung'] = 'Hinweis: Die Konfiguration liegt im Web-Ordner (inc) – der nächste Deploy löscht sie.';
    return $k;
}

function konfig_gueltig($d): ?array {
    return is_array($d) && !empty($d['benutzer']) && !empty($d['passwort_hash']) ? $d : null;
}

/** Für api.php: ohne Konfiguration gibt es nichts zu liefern. */
function konfig(): array {
    $k = konfig_laden();
    if ($k === null) { header_remove('X-Powered-By'); http_response_code(503); exit('AMW: noch nicht eingerichtet.'); }
    return $k;
}

/** Schreibt die Konfiguration: erst außerhalb des Deploy-Ordners ('aussen'), sonst inc/ ('inc'), sonst ''. */
function konfig_schreiben_roh(string $inhalt): string {
    foreach (konfig_orte() as $ort) {
        if (!is_dir(dirname($ort)) || !is_writable(dirname($ort))) continue;
        $tmp = $ort . '.neu';
        if (@file_put_contents($tmp, $inhalt) === false) continue;
        @chmod($tmp, 0600);
        if (@rename($tmp, $ort) && @file_get_contents($ort) === $inhalt) return 'aussen';
        @unlink($tmp);
    }
    $inc = __DIR__ . '/amw-konfig.php';
    return @file_put_contents($inc, $inhalt) !== false ? 'inc' : '';
}

function konfig_schreiben(array $d): string {
    return konfig_schreiben_roh("<?php\n// AMW online – angelegt " . gmdate('Y-m-d H:i') . " UTC vom Einrichtungs-Assistenten. Nie ins Repo.\nreturn "
        . var_export($d, true) . ";\n");
}

function ist_https(): bool {
    return (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
        || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
}

function ist_lokal(): bool {                              // Probe am PC (php -S 127.0.0.1) – dort ohne HTTPS
    return in_array(parse_url('//' . ($_SERVER['HTTP_HOST'] ?? ''), PHP_URL_HOST), ['127.0.0.1', 'localhost'], true);
}

function kopfzeilen(bool $html): void {
    header_remove('X-Powered-By');
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: DENY');
    header('Referrer-Policy: same-origin');   // no-referrer liesse Formulare mit „Origin: null“ senden (Edge geprüft)
    header('Cache-Control: no-store');
    header('Permissions-Policy: camera=(), microphone=(), geolocation=()');
    if (ist_https()) header('Strict-Transport-Security: max-age=31536000');
    if ($html) {
        header("Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline';"
            . " connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
    }
}

/* --- Speicher --------------------------------------------------------------------------------- */

/** Nur Turso-Adressen – der Assistent ruft keine beliebigen Ziele auf (kein Umweg ins interne Netz). */
function turso_url(string $eingabe): ?string {
    $u = strtolower(trim($eingabe));
    if (!preg_match('#^(?:libsql|https)://([a-z0-9-]+(?:\.[a-z0-9-]+)*\.turso\.io)/?$#', $u, $m)) return null;
    return 'https://' . $m[1];
}

/** Führt Anweisungen aus; Rückgabe je Anweisung die Zeilen als Listen. Wirft RuntimeException (Code = HTTP-Status).
 *  $zugang: ['turso_url', 'turso_token'] oder ['sqlite'] – sonst aus der Konfiguration. */
function sql(array $anweisungen, ?array $zugang = null): array {
    $k = $zugang ?? konfig();
    if (!empty($k['sqlite'])) {                              // Probe am PC
        static $pdo = [];
        $pdo[$k['sqlite']] ??= new PDO('sqlite:' . $k['sqlite'], null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
        $aus = [];
        foreach ($anweisungen as [$s, $args]) {
            $st = $pdo[$k['sqlite']]->prepare($s);
            $st->execute($args);
            $aus[] = $st->columnCount() ? $st->fetchAll(PDO::FETCH_NUM) : [];
        }
        return $aus;
    }
    $url = (turso_url((string)$k['turso_url']) ?? throw new RuntimeException('Turso-Adresse ungültig', 400)) . '/v2/pipeline';
    $req = [];
    foreach ($anweisungen as [$s, $args]) {
        $req[] = ['type' => 'execute', 'stmt' => ['sql' => $s, 'args' => array_map(function ($v) {
            if ($v === null) return ['type' => 'null'];
            if (is_int($v)) return ['type' => 'integer', 'value' => (string)$v];
            return ['type' => 'text', 'value' => (string)$v];
        }, $args)]];
    }
    $req[] = ['type' => 'close'];
    $c = curl_init($url);
    curl_setopt_array($c, [CURLOPT_POST => true, CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 15,
        CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $k['turso_token'], 'Content-Type: application/json'],
        CURLOPT_POSTFIELDS => json_encode(['requests' => $req], JSON_UNESCAPED_UNICODE)]);
    $roh = curl_exec($c);
    $code = (int)curl_getinfo($c, CURLINFO_RESPONSE_CODE);
    curl_close($c);
    if ($roh === false || $code !== 200) throw new RuntimeException("Speicher nicht erreichbar ($code)", $code);
    $antwort = json_decode($roh, true);
    $aus = [];
    foreach (array_slice($antwort['results'] ?? [], 0, count($anweisungen)) as $r) {
        if (($r['type'] ?? '') !== 'ok') throw new RuntimeException('Speicher: ' . ($r['error']['message'] ?? 'Fehler'), 500);
        $aus[] = array_map(fn($z) => array_map(fn($w) => $w['value'] ?? null, $z), $r['response']['result']['rows'] ?? []);
    }
    return $aus;
}

function jetzt_utc(int $verschub = 0): string {
    return gmdate('Y-m-d\TH:i:s\Z', time() + $verschub);
}

function zustand_lesen(string $schluessel, ?array $zugang = null): ?string {
    $z = sql([['SELECT wert FROM zustand WHERE schluessel = ?', [$schluessel]]], $zugang)[0];
    return $z ? $z[0][0] : null;
}

/* --- Sitzung ---------------------------------------------------------------------------------- */

function sitzung_starten(): void {
    $k = konfig_laden();
    if (($k['nur_https'] ?? true) && !ist_https() && !ist_lokal()) {
        header('Location: https://' . ($_SERVER['HTTP_HOST'] ?? '') . ($_SERVER['REQUEST_URI'] ?? '/'), true, 301);
        exit;
    }
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');
    session_name(ist_https() ? '__Host-amw' : 'amw');
    session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'secure' => ist_https(), 'httponly' => true,
        'samesite' => 'Strict']);
    session_start();
    if (empty($_SESSION['csrf'])) $_SESSION['csrf'] = bin2hex(random_bytes(32));
}

/* --- Seitenrahmen für Anmeldung und Einrichtung ------------------------------------------------- */

function seite_anfang(string $titel, string $unterzeile): void {
    header('Content-Type: text/html; charset=utf-8');
    $e = fn(string $s) => htmlspecialchars($s, ENT_QUOTES, 'UTF-8');
    echo '<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        . '<meta name="robots" content="noindex, nofollow"><title>AMW · ' . $e($titel) . '</title><style>'
        . ':root{--grund:#f3f1ec;--flaeche:#fffdf8;--text:#1d1b16;--leise:#6b665c;--linie:#d9d4c8;--bernstein:#b86e00;--rot:#b3261e;--gruen:#2e7d32}'
        . '@media (prefers-color-scheme:dark){:root{--grund:#12110e;--flaeche:#1b1a16;--text:#ece8dd;--leise:#9a9486;--linie:#34312a;--bernstein:#f0a020;--rot:#ff6b5e;--gruen:#7bc47f}}'
        . '*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:16px;background:var(--grund);color:var(--text);font:15px/1.5 Bahnschrift,"Segoe UI",system-ui,sans-serif}'
        . 'form{width:100%;max-width:400px;background:var(--flaeche);border:1px solid var(--linie);border-top:3px solid var(--bernstein);border-radius:4px;padding:24px;display:grid;gap:14px}'
        . 'h1{margin:0;font-size:20px;letter-spacing:.06em}h1 b{color:var(--bernstein)}p{margin:0}'
        . '.leise{color:var(--leise);font-size:13px}.unter{color:var(--leise);font-size:13px;margin:-8px 0 4px}'
        . 'label{display:grid;gap:4px;font-size:13px;color:var(--leise);text-transform:uppercase;letter-spacing:.06em}'
        . 'input{font:inherit;font-size:16px;padding:10px 12px;min-height:46px;border:1px solid var(--linie);border-radius:3px;background:var(--grund);color:var(--text);text-transform:none;letter-spacing:normal;width:100%}'
        . 'input:focus{outline:2px solid var(--bernstein);outline-offset:1px}'
        . 'button{font:600 14px Bahnschrift,system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;min-height:46px;border:0;border-radius:3px;background:var(--bernstein);color:#1d1b16;cursor:pointer}'
        . '.fehler{color:var(--rot);font-size:14px}.gut{color:var(--gruen);font-size:14px}'
        . '.schritte{margin:0;padding-left:20px;font-size:14px}.schritte li{margin:4px 0}'
        . '.qr{display:grid;place-items:center}.qr svg{width:100%;max-width:260px;height:auto;border-radius:3px}'
        . 'details{font-size:13px;color:var(--leise)}details code{display:block;margin-top:6px;font:15px Consolas,monospace;color:var(--text);letter-spacing:.05em;word-break:break-all}'
        . '.stufe{display:flex;gap:6px}.stufe span{flex:1;height:4px;border-radius:2px;background:var(--linie)}.stufe span.an{background:var(--bernstein)}'
        . '</style></head><body><form method="post" action="./" autocomplete="on">'
        . '<h1><b>AMW</b> Workbench</h1><p class="unter">' . $e($unterzeile) . '</p>';
}

function seite_ende(): void {
    echo '</form></body></html>';
}

function angemeldet(): bool {
    if (empty($_SESSION['angemeldet'])) return false;
    $t = time();
    if ($t - ($_SESSION['seit'] ?? 0) > web_einst('hoechstens_h') * 3600 || $t - ($_SESSION['zuletzt'] ?? 0) > web_einst('leerlauf_min') * 60) {
        abmelden();
        return false;
    }
    $_SESSION['zuletzt'] = $t;
    return true;
}

function abmelden(): void {
    $_SESSION = [];
    session_regenerate_id(true);
    $_SESSION['csrf'] = bin2hex(random_bytes(32));
}

function csrf_ok(?string $wert): bool {
    return is_string($wert) && hash_equals($_SESSION['csrf'] ?? '', $wert);
}

function herkunft_ok(): bool {                          // Anfragen von fremden Seiten abweisen
    $o = $_SERVER['HTTP_ORIGIN'] ?? '';
    if ($o === '' || $o === 'null') return $o === '';
    // Hinter dem CDN des Hosters kann Host anders aussehen (Port, weitergeleiteter Host) – alle eigenen Namen zulassen
    $eigen = [];
    foreach (['HTTP_HOST', 'HTTP_X_FORWARDED_HOST', 'SERVER_NAME'] as $s) {
        foreach (explode(',', (string)($_SERVER[$s] ?? '')) as $h) {
            $h = strtolower(trim((string)parse_url('//' . trim($h), PHP_URL_HOST)));
            if ($h !== '') $eigen[] = $h;
        }
    }
    return in_array(strtolower((string)parse_url($o, PHP_URL_HOST)), $eigen, true);
}

/* --- Anmeldung: Passwort + Einmalcode (TOTP, RFC 6238) ------------------------------------------ */

function base32_bytes(string $b32): string {
    $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
    $bits = '';
    foreach (str_split(strtoupper(preg_replace('/[^A-Za-z2-7]/', '', $b32))) as $z) {
        $bits .= str_pad(decbin(strpos($alphabet, $z)), 5, '0', STR_PAD_LEFT);
    }
    $aus = '';
    foreach (str_split($bits, 8) as $byte) if (strlen($byte) === 8) $aus .= chr(bindec($byte));
    return $aus;
}

function totp(string $geheim, int $schritt): string {
    $h = hash_hmac('sha1', pack('J', $schritt), base32_bytes($geheim), true);
    $o = ord($h[19]) & 0x0f;
    $n = ((ord($h[$o]) & 0x7f) << 24) | (ord($h[$o + 1]) << 16) | (ord($h[$o + 2]) << 8) | ord($h[$o + 3]);
    return str_pad((string)($n % 1000000), 6, '0', STR_PAD_LEFT);
}

/** Schritt des gültigen Codes (±30 s Toleranz) oder null. Jeder Code gilt nur einmal (zustand.totp_letzt). */
function totp_pruefen(string $geheim, string $code): ?int {
    if (!preg_match('/^\d{6}$/', $code)) return null;
    $jetzt = intdiv(time(), 30);
    $letzt = (int)(zustand_lesen('totp_letzt') ?? 0);
    foreach ([$jetzt, $jetzt - 1, $jetzt + 1] as $s) {
        if ($s > $letzt && hash_equals(totp($geheim, $s), $code)) return $s;
    }
    return null;
}

function gesperrt(string $ip): bool {
    [$je_ip, $gesamt] = sql([
        ['SELECT count(*) FROM versuch WHERE ok = 0 AND ip = ? AND zeit_utc > ?', [$ip, jetzt_utc(-900)]],
        ['SELECT count(*) FROM versuch WHERE ok = 0 AND zeit_utc > ?', [jetzt_utc(-3600)]],
    ]);
    return (int)$je_ip[0][0] >= web_einst('fehl_je_ip') || (int)$gesamt[0][0] >= web_einst('fehl_gesamt');
}

const EINRICHTEN_S = 600;            // so lange gilt der QR-Code beim ersten Anmelden

/** Geheimnis des zweiten Faktors – liegt im Online-Speicher, wird beim ersten Anmelden per QR-Code eingerichtet. */
function totp_geheim(): ?string {
    return zustand_lesen('totp_geheim');
}

function neues_geheim(): string {
    $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
    $g = '';
    foreach (str_split(random_bytes(32)) as $b) $g .= $alphabet[ord($b) % 32];   // 32 Zeichen = 160 Bit
    return $g;
}

function versuch_merken(string $ip, bool $ok, ?int $schritt = null): void {
    $anw = [['INSERT INTO versuch (zeit_utc, ip, ok) VALUES (?, ?, ?)', [jetzt_utc(), $ip, $ok ? 1 : 0]],
            ['DELETE FROM versuch WHERE zeit_utc < ?', [jetzt_utc(-30 * 86400)]]];
    if ($schritt !== null) {
        $anw[] = ["INSERT INTO zustand (schluessel, wert) VALUES ('totp_letzt', ?) ON CONFLICT(schluessel)"
                  . ' DO UPDATE SET wert = excluded.wert', [(string)$schritt]];
    }
    sql($anw);
}

function sitzung_anmelden(): void {
    session_regenerate_id(true);
    unset($_SESSION['einrichten']);
    $_SESSION['angemeldet'] = true;
    $_SESSION['seit'] = $_SESSION['zuletzt'] = time();
    $_SESSION['csrf'] = bin2hex(random_bytes(32));
}

/** Prüft Benutzer, Passwort und Code. Rückgabe: '' angemeldet, 'einrichten' = Passwort stimmt, zweiter Faktor fehlt
 *  noch (QR-Code zeigen), sonst ein Hinweis (absichtlich unspezifisch). */
function anmelden(string $benutzer, string $passwort, string $code): string {
    $k = konfig();
    $ip = $_SERVER['REMOTE_ADDR'] ?? '?';
    if (gesperrt($ip)) return 'Zu viele Fehlversuche – bitte später erneut versuchen.';
    $ok = (bool)(hash_equals($k['benutzer'], $benutzer) & password_verify($passwort, $k['passwort_hash']));
    $geheim = $ok ? totp_geheim() : null;
    if ($ok && $geheim === null) {                       // erstes Anmelden: zweiten Faktor einrichten
        session_regenerate_id(true);
        $_SESSION['einrichten'] = ['geheim' => neues_geheim(), 'seit' => time(), 'benutzer' => $benutzer];
        return 'einrichten';
    }
    $schritt = $ok ? totp_pruefen($geheim, $code) : null;
    versuch_merken($ip, $schritt !== null, $schritt);
    if ($schritt === null) { usleep(400000); return 'Anmeldung fehlgeschlagen.'; }
    sitzung_anmelden();
    return '';
}

/** Zweiter Schritt beim ersten Anmelden: erster Code aus der App bestätigt den gescannten QR-Code. */
function einrichten_abschliessen(string $code): string {
    $e = $_SESSION['einrichten'] ?? null;
    $ip = $_SERVER['REMOTE_ADDR'] ?? '?';
    if (!$e || time() - $e['seit'] > EINRICHTEN_S) { unset($_SESSION['einrichten']); return 'Zeit abgelaufen – bitte neu anmelden.'; }
    if (gesperrt($ip)) return 'Zu viele Fehlversuche – bitte später erneut versuchen.';
    $schritt = null;
    if (preg_match('/^\d{6}$/', $code)) {
        $jetzt = intdiv(time(), 30);
        foreach ([$jetzt, $jetzt - 1, $jetzt + 1] as $s) if (hash_equals(totp($e['geheim'], $s), $code)) { $schritt = $s; break; }
    }
    if ($schritt === null) { versuch_merken($ip, false); usleep(400000); return 'Code stimmt nicht – bitte die aktuelle Zahl aus der App.'; }
    // nur wenn noch keiner eingerichtet ist (nie ein bestehendes Geheimnis überschreiben)
    sql([["INSERT INTO zustand (schluessel, wert) VALUES ('totp_geheim', ?) ON CONFLICT(schluessel) DO NOTHING", [$e['geheim']]]]);
    if (totp_geheim() !== $e['geheim']) { unset($_SESSION['einrichten']); return 'Zweiter Faktor ist schon eingerichtet – bitte normal anmelden.'; }
    versuch_merken($ip, true, $schritt);
    sitzung_anmelden();
    return '';
}
