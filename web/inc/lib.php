<?php
/* AMW online (Stufe 2, doc/12-online.md): gemeinsame Teile für index.php und api.php.
 *
 * Konfiguration liegt AUSSERHALB des Web-Ordners (nie im Repo): Umgebungsvariable AMW_KONFIG oder
 * <Ordner über dem Web-Ordner>/amw-konfig.php. Vorlage: inc/konfig.beispiel.php.
 * Speicher: Turso über HTTP (/v2/pipeline) oder für die Probe am PC eine SQLite-Datei.
 */
declare(strict_types=1);

const SITZUNG_LEERLAUF_S = 1800;     // 30 min ohne Klick → neu anmelden
const SITZUNG_HOECHSTENS_S = 43200;  // spätestens nach 12 h
const FEHL_JE_IP = 5;                // Fehlversuche je Adresse in 15 min
const FEHL_GESAMT = 20;              // Fehlversuche insgesamt in 60 min (verteilte Versuche)
const SCHREIBEN_JE_STUNDE = 120;     // Briefkasten-Zeilen je Stunde

function konfig(): array {
    static $k = null;
    if ($k !== null) return $k;
    // Standard: neben public_html (nie darin, auch wenn die Seite in einem Unterordner/einer Subdomain liegt)
    $wurzel = str_replace('\\', '/', (string)($_SERVER['DOCUMENT_ROOT'] ?? dirname(__DIR__)));
    $basis = ($p = strpos($wurzel, '/public_html')) !== false ? substr($wurzel, 0, $p) : dirname($wurzel);
    $pfad = getenv('AMW_KONFIG') ?: $basis . '/amw-konfig.php';
    if (!is_file($pfad)) { header_remove('X-Powered-By'); http_response_code(503); exit('AMW: Konfiguration fehlt.'); }
    $k = require $pfad;
    foreach (['benutzer', 'passwort_hash', 'totp_geheim'] as $pflicht) {
        if (empty($k[$pflicht])) { http_response_code(503); exit('AMW: Konfiguration unvollständig.'); }
    }
    return $k;
}

function ist_https(): bool {
    return (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
        || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
}

function kopfzeilen(bool $html): void {
    header_remove('X-Powered-By');
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: DENY');
    header('Referrer-Policy: no-referrer');
    header('Cache-Control: no-store');
    header('Permissions-Policy: camera=(), microphone=(), geolocation=()');
    if (ist_https()) header('Strict-Transport-Security: max-age=31536000');
    if ($html) {
        header("Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline';"
            . " connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
    }
}

/* --- Speicher --------------------------------------------------------------------------------- */

/** Führt Anweisungen aus; Rückgabe je Anweisung die Zeilen als Listen. Wirft RuntimeException. */
function sql(array $anweisungen): array {
    $k = konfig();
    if (!empty($k['sqlite'])) {                              // Probe am PC
        static $pdo = null;
        $pdo ??= new PDO('sqlite:' . $k['sqlite'], null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
        $aus = [];
        foreach ($anweisungen as [$s, $args]) {
            $st = $pdo->prepare($s);
            $st->execute($args);
            $aus[] = $st->columnCount() ? $st->fetchAll(PDO::FETCH_NUM) : [];
        }
        return $aus;
    }
    $url = preg_replace('#^libsql://#', 'https://', rtrim($k['turso_url'], '/')) . '/v2/pipeline';
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
    $code = curl_getinfo($c, CURLINFO_RESPONSE_CODE);
    curl_close($c);
    if ($roh === false || $code !== 200) throw new RuntimeException("Speicher nicht erreichbar ($code)");
    $antwort = json_decode($roh, true);
    $aus = [];
    foreach (array_slice($antwort['results'] ?? [], 0, count($anweisungen)) as $r) {
        if (($r['type'] ?? '') !== 'ok') throw new RuntimeException('Speicher: ' . ($r['error']['message'] ?? 'Fehler'));
        $aus[] = array_map(fn($z) => array_map(fn($w) => $w['value'] ?? null, $z), $r['response']['result']['rows'] ?? []);
    }
    return $aus;
}

function jetzt_utc(int $verschub = 0): string {
    return gmdate('Y-m-d\TH:i:s\Z', time() + $verschub);
}

function zustand_lesen(string $schluessel): ?string {
    $z = sql([['SELECT wert FROM zustand WHERE schluessel = ?', [$schluessel]]])[0];
    return $z ? $z[0][0] : null;
}

/* --- Sitzung ---------------------------------------------------------------------------------- */

function sitzung_starten(): void {
    $k = konfig();
    if (($k['nur_https'] ?? true) && !ist_https()) {
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

function angemeldet(): bool {
    if (empty($_SESSION['angemeldet'])) return false;
    $t = time();
    if ($t - ($_SESSION['seit'] ?? 0) > SITZUNG_HOECHSTENS_S || $t - ($_SESSION['zuletzt'] ?? 0) > SITZUNG_LEERLAUF_S) {
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
    return $o === '' || parse_url($o, PHP_URL_HOST) === parse_url('//' . ($_SERVER['HTTP_HOST'] ?? ''), PHP_URL_HOST);
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
    return (int)$je_ip[0][0] >= FEHL_JE_IP || (int)$gesamt[0][0] >= FEHL_GESAMT;
}

/** Prüft Benutzer, Passwort und Code. Rückgabe: '' bei Erfolg, sonst ein Hinweis (absichtlich unspezifisch). */
function anmelden(string $benutzer, string $passwort, string $code): string {
    $k = konfig();
    $ip = $_SERVER['REMOTE_ADDR'] ?? '?';
    if (gesperrt($ip)) return 'Zu viele Fehlversuche – bitte später erneut versuchen.';
    $ok = hash_equals($k['benutzer'], $benutzer) & password_verify($passwort, $k['passwort_hash']);
    $schritt = $ok ? totp_pruefen($k['totp_geheim'], $code) : null;
    $anw = [['INSERT INTO versuch (zeit_utc, ip, ok) VALUES (?, ?, ?)', [jetzt_utc(), $ip, $schritt !== null ? 1 : 0]],
            ['DELETE FROM versuch WHERE zeit_utc < ?', [jetzt_utc(-30 * 86400)]]];
    if ($schritt !== null) {
        $anw[] = ["INSERT INTO zustand (schluessel, wert) VALUES ('totp_letzt', ?) ON CONFLICT(schluessel)"
                  . ' DO UPDATE SET wert = excluded.wert', [(string)$schritt]];
    }
    sql($anw);
    if ($schritt === null) { usleep(400000); return 'Anmeldung fehlgeschlagen.'; }
    session_regenerate_id(true);
    $_SESSION['angemeldet'] = true;
    $_SESSION['seit'] = $_SESSION['zuletzt'] = time();
    $_SESSION['csrf'] = bin2hex(random_bytes(32));
    return '';
}
