<?php
/* Firmen-Anmeldung (Stufe R2): OpenID Connect, Authorization Code Flow mit PKCE (doc/online.md, Hilfe „firmen-anmeldung“).
 *
 * Einstellungen vom PC (zustand „sso“): an, Aussteller, Client-ID – nichts Geheimes. Das Geheimnis des Anbieters
 * (Client-Secret) oder Zertifikat + Schlüssel stehen nur in der Konfigurationsdatei beim Webhoster außerhalb des
 * Web-Ordners (sso_geheimnis bzw. sso_zertifikat/sso_schluessel), nie im Speicher, nie auf dem PC.
 *
 * Ablauf: sso.php leitet zum Anbieter (state, nonce, PKCE im eigenen Cookie mit SameSite=Lax – das Sitzungs-Cookie ist
 * Strict und kommt bei der Rückkehr vom Anbieter nicht mit). Zurück: Code gegen Token tauschen, ID-Token prüfen
 * (Signatur RS256 mit dem Schlüssel des Anbieters, Aussteller, Empfänger, Ablauf, nonce), Benutzer suchen: über die
 * gebundene Kennung (Aussteller + sub) oder beim ersten Mal über die E-Mail, die ein Admin am PC eingetragen hat.
 * Kein zweiter Faktor in der AMW – den macht der Anbieter. Nur angelegte Benutzer kommen hinein.
 */
declare(strict_types=1);

const SSO_FRIST_S = 600;              // so lange darf der Weg zum Anbieter und zurück dauern
const SSO_UHR_S = 120;                // Toleranz für die Uhrzeiten im Token (Uhr des Webhosters gegen die des Anbieters)
const SSO_ALGOS = ['RS256' => OPENSSL_ALGO_SHA256, 'RS384' => OPENSSL_ALGO_SHA384, 'RS512' => OPENSSL_ALGO_SHA512];

final class SsoFehler extends RuntimeException {}

function b64url(string $roh): string {
    return rtrim(strtr(base64_encode($roh), '+/', '-_'), '=');
}

function b64url_roh(string $s): string {
    $r = base64_decode(strtr($s, '-_', '+/') . str_repeat('=', (4 - strlen($s) % 4) % 4), true);
    if ($r === false) throw new SsoFehler('Token kaputt (Base64)');
    return $r;
}

/** Einstellungen vom PC. Aussteller ohne „/“ am Ende (so steht er auch im Token). */
function sso_einst(): array {
    try { $d = json_decode((string)zustand_lesen('sso'), true) ?: []; } catch (RuntimeException $x) { $d = []; }
    return ['an' => !empty($d['an']), 'aussteller' => rtrim(trim((string)($d['aussteller'] ?? '')), '/'),
            'client_id' => trim((string)($d['client_id'] ?? ''))];
}

/** Wie meldet sich die Seite beim Anbieter: 'geheimnis', 'zertifikat' oder '' (noch nichts eingetragen). */
function sso_zugang_art(?array $k = null): string {
    $k ??= konfig_laden() ?? [];
    if (!empty($k['sso_zertifikat']) && !empty($k['sso_schluessel'])) return 'zertifikat';
    return !empty($k['sso_geheimnis']) ? 'geheimnis' : '';
}

/** Knopf „Mit Firmenkonto anmelden“ zeigen? Nur wenn am PC eingeschaltet UND das Geheimnis beim Webhoster liegt. */
function sso_bereit(): bool {
    $e = sso_einst();
    return $e['an'] && $e['aussteller'] !== '' && $e['client_id'] !== '' && sso_zugang_art() !== '';
}

/** Rückkehr-Adresse beim Anbieter (Redirect-URI): sso.php neben index.php. */
function sso_rueckweg(): string {
    $pfad = rtrim(str_replace(chr(92), '/', dirname((string)($_SERVER['SCRIPT_NAME'] ?? '/sso.php'))), '/');
    return (ist_https() ? 'https' : 'http') . '://' . ($_SERVER['HTTP_HOST'] ?? '') . $pfad . '/sso.php';
}

/** Nur https – http nur für die Probe am PC (Seite und Anbieter auf 127.0.0.1). */
function sso_adresse_ok(string $url): bool {
    $teile = parse_url($url);
    if (!$teile || empty($teile['host'])) return false;
    if (($teile['scheme'] ?? '') === 'https') return true;
    return ($teile['scheme'] ?? '') === 'http' && in_array($teile['host'], ['127.0.0.1', 'localhost'], true) && ist_lokal();
}

/** Ruft den Anbieter (JSON). Keine Weiterleitungen, kurze Frist. */
function sso_holen(string $url, ?array $post = null, array $kopf = []): array {
    if (!sso_adresse_ok($url)) throw new SsoFehler('Adresse des Anbieters nicht erlaubt (nur https): ' . $url);
    $c = curl_init($url);
    $opt = [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 10, CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_PROTOCOLS => CURLPROTO_HTTPS | CURLPROTO_HTTP, CURLOPT_HTTPHEADER => array_merge(['Accept: application/json'], $kopf)];
    if ($post !== null) $opt += [CURLOPT_POST => true, CURLOPT_POSTFIELDS => http_build_query($post)];
    curl_setopt_array($c, $opt);
    $roh = curl_exec($c);
    $code = (int)curl_getinfo($c, CURLINFO_RESPONSE_CODE);
    $fehler = curl_error($c);
    curl_close($c);
    if ($roh === false) throw new SsoFehler("Anbieter nicht erreichbar ($fehler)");
    $d = json_decode((string)$roh, true);
    if ($code !== 200 || !is_array($d)) {
        $grund = is_array($d) ? trim(($d['error'] ?? '') . ' ' . mb_substr((string)($d['error_description'] ?? ''), 0, 200)) : '';
        throw new SsoFehler("Anbieter antwortet $code" . ($grund !== '' ? ": $grund" : ''));
    }
    return $d;
}

/** Beschreibung des Anbieters (.well-known/openid-configuration). Der Aussteller darin muss genau der eingetragene sein. */
function sso_anbieter(string $aussteller): array {
    $d = sso_holen($aussteller . '/.well-known/openid-configuration');
    $iss = (string)($d['issuer'] ?? '');
    if (str_contains($iss, '{tenantid}')) throw new SsoFehler('Aussteller mit „common“/„organizations“ geht nicht – bitte die Mandanten-ID (Tenant ID) eintragen.');
    if (rtrim($iss, '/') !== $aussteller) throw new SsoFehler("Aussteller passt nicht: der Anbieter nennt sich „{$iss}“.");
    foreach (['authorization_endpoint', 'token_endpoint', 'jwks_uri'] as $k) {
        if (!is_string($d[$k] ?? null) || !sso_adresse_ok($d[$k])) throw new SsoFehler("Anbieter ohne gültige Angabe $k");
    }
    return $d + ['issuer_genau' => $iss];
}

/* --- Schlüssel: JWK (n, e) → PEM, ohne Bibliothek ------------------------------------------------------------------ */

function der(int $tag, string $inhalt): string {
    $n = strlen($inhalt);
    $l = $n < 128 ? chr($n) : (fn($s) => chr(0x80 | strlen($s)) . $s)(ltrim(pack('N', $n), "\0"));
    return chr($tag) . $l . $inhalt;
}

function der_zahl(string $b): string {
    $b = ltrim($b, "\0");
    if ($b === '' || ord($b[0]) > 0x7f) $b = "\0" . $b;
    return der(0x02, $b);
}

function jwk_pem(array $k): ?string {
    if (($k['kty'] ?? '') !== 'RSA' || !is_string($k['n'] ?? null) || !is_string($k['e'] ?? null)) return null;
    $rsa = der(0x30, der_zahl(b64url_roh($k['n'])) . der_zahl(b64url_roh($k['e'])));
    $algo = der(0x30, der(0x06, "\x2a\x86\x48\x86\xf7\x0d\x01\x01\x01") . "\x05\x00");     // rsaEncryption, NULL
    return "-----BEGIN PUBLIC KEY-----\n" . chunk_split(base64_encode(der(0x30, $algo . der(0x03, "\0" . $rsa))), 64, "\n")
        . "-----END PUBLIC KEY-----\n";
}

/** Prüft das ID-Token und gibt seine Angaben zurück – sonst SsoFehler. */
function sso_token_pruefen(string $jwt, array $jwks, string $iss, string $client_id, string $nonce, ?int $jetzt = null): array {
    $jetzt ??= time();
    $teile = explode('.', $jwt);
    if (count($teile) !== 3) throw new SsoFehler('Token kaputt');
    $kopf = json_decode(b64url_roh($teile[0]), true);
    $d = json_decode(b64url_roh($teile[1]), true);
    if (!is_array($kopf) || !is_array($d)) throw new SsoFehler('Token kaputt (JSON)');
    $alg = (string)($kopf['alg'] ?? '');
    if (!isset(SSO_ALGOS[$alg])) throw new SsoFehler("Signatur-Verfahren nicht erlaubt: $alg");   // nie „none“, nie HS256
    $passend = array_values(array_filter($jwks['keys'] ?? [], fn($k) => is_array($k) && ($k['kty'] ?? '') === 'RSA'
        && ($k['use'] ?? 'sig') === 'sig' && (!isset($kopf['kid']) || ($k['kid'] ?? null) === $kopf['kid'])));
    if (!$passend || (!isset($kopf['kid']) && count($passend) > 1)) throw new SsoFehler('Schlüssel des Anbieters nicht gefunden');
    $pem = jwk_pem($passend[0]);
    if ($pem === null || openssl_verify($teile[0] . '.' . $teile[1], b64url_roh($teile[2]), $pem, SSO_ALGOS[$alg]) !== 1) {
        throw new SsoFehler('Signatur stimmt nicht');
    }
    if (($d['iss'] ?? null) !== $iss) throw new SsoFehler('Aussteller im Token stimmt nicht');
    $aud = $d['aud'] ?? null;
    $auds = is_array($aud) ? $aud : [$aud];
    if (!in_array($client_id, $auds, true)) throw new SsoFehler('Token ist nicht für diese Seite ausgestellt');
    if (count($auds) > 1 && ($d['azp'] ?? null) !== $client_id) throw new SsoFehler('Token ist nicht für diese Seite ausgestellt (azp)');
    if (!is_numeric($d['exp'] ?? null) || (int)$d['exp'] < $jetzt - SSO_UHR_S) throw new SsoFehler('Token abgelaufen');
    if (is_numeric($d['iat'] ?? null) && (int)$d['iat'] > $jetzt + SSO_UHR_S) throw new SsoFehler('Token aus der Zukunft – stimmt die Uhr?');
    if (is_numeric($d['nbf'] ?? null) && (int)$d['nbf'] > $jetzt + SSO_UHR_S) throw new SsoFehler('Token noch nicht gültig');
    if (!is_string($d['nonce'] ?? null) || !hash_equals($nonce, $d['nonce'])) throw new SsoFehler('Token gehört nicht zu dieser Anmeldung (nonce)');
    if (!is_string($d['sub'] ?? null) || $d['sub'] === '') throw new SsoFehler('Token ohne Kennung (sub)');
    return $d;
}

/** Wie sich die Seite beim Anbieter ausweist: Geheimnis oder signierte Bestätigung mit dem Zertifikat (private_key_jwt). */
function sso_ausweis(array $k, string $client_id, string $token_url): array {
    if (sso_zugang_art($k) === 'zertifikat') {
        $der = '';
        if (preg_match('/-----BEGIN CERTIFICATE-----(.+?)-----END CERTIFICATE-----/s', (string)$k['sso_zertifikat'], $m)) {
            $der = (string)base64_decode(preg_replace('/\s+/', '', $m[1]), true);
        }
        if ($der === '') throw new SsoFehler('Zertifikat in der Konfiguration ist kaputt');
        $t = time();
        $kopf = ['alg' => 'RS256', 'typ' => 'JWT', 'x5t' => b64url(sha1($der, true)), 'x5t#S256' => b64url(hash('sha256', $der, true))];
        $inhalt = ['aud' => $token_url, 'iss' => $client_id, 'sub' => $client_id, 'jti' => bin2hex(random_bytes(16)),
                   'iat' => $t, 'nbf' => $t, 'exp' => $t + 300];
        $roh = b64url(json_encode($kopf, JSON_UNESCAPED_SLASHES)) . '.' . b64url(json_encode($inhalt, JSON_UNESCAPED_SLASHES));
        if (!openssl_sign($roh, $sig, (string)$k['sso_schluessel'], OPENSSL_ALGO_SHA256)) throw new SsoFehler('Schlüssel in der Konfiguration passt nicht');
        return ['client_id' => $client_id, 'client_assertion_type' => 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
                'client_assertion' => $roh . '.' . b64url($sig)];
    }
    return ['client_id' => $client_id, 'client_secret' => (string)($k['sso_geheimnis'] ?? '')];
}

/* --- Ablauf ---------------------------------------------------------------------------------------------------- */

function sso_cookie_name(): string {
    return ist_https() ? '__Host-amw-sso' : 'amw-sso';
}

function sso_cookie(string $wert, int $dauer): void {
    setcookie(sso_cookie_name(), $wert, ['expires' => $dauer > 0 ? time() + $dauer : 1, 'path' => '/', 'secure' => ist_https(),
                                         'httponly' => true, 'samesite' => 'Lax']);
}

/** Schritt 1: zum Anbieter. Rückgabe: die Adresse, zu der weitergeleitet wird. */
function sso_start(): string {
    if (!sso_bereit()) throw new SsoFehler('Die Firmen-Anmeldung ist nicht eingerichtet.');
    $e = sso_einst();
    $a = sso_anbieter($e['aussteller']);
    $vorgang = ['s' => b64url(random_bytes(24)), 'n' => b64url(random_bytes(24)), 'v' => b64url(random_bytes(48)), 't' => time()];
    sso_cookie(b64url(json_encode($vorgang)), SSO_FRIST_S);
    $param = ['response_type' => 'code', 'client_id' => $e['client_id'], 'redirect_uri' => sso_rueckweg(),
              'scope' => 'openid profile email', 'state' => $vorgang['s'], 'nonce' => $vorgang['n'],
              'code_challenge' => b64url(hash('sha256', $vorgang['v'], true)), 'code_challenge_method' => 'S256',
              'response_mode' => 'query'];
    return $a['authorization_endpoint'] . (str_contains($a['authorization_endpoint'], '?') ? '&' : '?') . http_build_query($param);
}

/** Schritt 2: zurück vom Anbieter. Rückgabe: Name des angemeldeten Benutzers; sonst SsoFehler mit einer Meldung für ihn.
 *  $merken: Fehlversuche zählen in dieselbe Sperre wie beim Passwort. */
function sso_zurueck(array $get, ?string $cookie): string {
    $ip = $_SERVER['REMOTE_ADDR'] ?? '?';
    sso_cookie('', 0);                                       // der Vorgang gilt genau einmal
    if (isset($get['error'])) {
        throw new SsoFehler('Der Anbieter hat die Anmeldung abgebrochen · The provider cancelled the sign-in: '
            . mb_substr((string)$get['error'] . ' ' . (string)($get['error_description'] ?? ''), 0, 300));
    }
    $v = $cookie !== null ? json_decode(b64url_roh($cookie), true) : null;
    if (!is_array($v) || !isset($v['s'], $v['n'], $v['v'], $v['t']) || time() - (int)$v['t'] > SSO_FRIST_S) {
        throw new SsoFehler('Die Anmeldung hat zu lange gedauert oder kam aus einem anderen Browser – bitte noch einmal.'
            . ' · Sign-in took too long or came from another browser – please try again.');
    }
    if (!is_string($get['state'] ?? null) || !hash_equals((string)$v['s'], $get['state'])) {
        throw new SsoFehler('Die Antwort des Anbieters gehört nicht zu dieser Anmeldung – bitte noch einmal.'
            . ' · The answer from the provider does not belong to this sign-in – please try again.');
    }
    if (!is_string($get['code'] ?? null) || $get['code'] === '') throw new SsoFehler('Antwort des Anbieters ohne Code');
    if (gesperrt($ip)) throw new SsoFehler('Zu viele Fehlversuche – bitte später erneut versuchen. · Too many failed attempts – please try later.');
    $e = sso_einst();
    if (!sso_bereit()) throw new SsoFehler('Die Firmen-Anmeldung ist nicht (mehr) eingeschaltet.');
    $a = sso_anbieter($e['aussteller']);
    $k = konfig();
    $antwort = sso_holen($a['token_endpoint'], ['grant_type' => 'authorization_code', 'code' => $get['code'],
        'redirect_uri' => sso_rueckweg(), 'code_verifier' => (string)$v['v']] + sso_ausweis($k, $e['client_id'], $a['token_endpoint']));
    if (!is_string($antwort['id_token'] ?? null)) throw new SsoFehler('Anbieter hat kein ID-Token geliefert (Bereich „openid“?)');
    $d = sso_token_pruefen($antwort['id_token'], sso_holen($a['jwks_uri']), $a['issuer_genau'], $e['client_id'], (string)$v['n']);
    return sso_benutzer($d, $a['issuer_genau'], $ip);
}

/** E-Mail aus dem Token: email, sonst (Microsoft Entra ID ohne E-Mail-Angabe) preferred_username bzw. upn. */
function sso_email(array $d): string {
    foreach (['email', 'preferred_username', 'upn'] as $k) {
        $m = strtolower(trim((string)($d[$k] ?? '')));
        if (str_contains($m, '@')) return $m;
    }
    return '';
}

/** Sucht den angelegten Benutzer und meldet ihn an. Erstes Mal: über die E-Mail, danach über die gebundene Kennung. */
function sso_benutzer(array $d, string $iss, string $ip): string {
    $kennung = $iss . '|' . $d['sub'];
    $mail = sso_email($d);
    $t = jetzt_utc();
    $erstes = false;
    $z = sql([['UPDATE benutzer SET angemeldet_utc = ? WHERE sso_kennung = ? AND gesperrt = 0 RETURNING name, sitzung_nr', [$t, $kennung]]])[0];
    if (!$z && $mail !== '') {                                // noch nicht gebunden: genau ein Benutzer mit dieser E-Mail
        $treffer = sql([["SELECT name FROM benutzer WHERE lower(email) = ? AND sso_kennung IS NULL AND gesperrt = 0", [$mail]]])[0];
        if (count($treffer) === 1) {
            $z = sql([['UPDATE benutzer SET sso_kennung = ?, angemeldet_utc = ?, eingerichtet_utc = coalesce(eingerichtet_utc, ?)'
                       . ' WHERE name = ? AND sso_kennung IS NULL AND gesperrt = 0 RETURNING name, sitzung_nr',
                       [$kennung, $t, $t, $treffer[0][0]]]])[0];
            $erstes = (bool)$z;
        }
    }
    if (!$z) {
        versuch_merken($ip, false);
        usleep(400000);
        $wer = $mail !== '' ? " ($mail)" : '';
        throw new SsoFehler("Dein Firmenkonto$wer ist hier nicht freigeschaltet oder gesperrt – bitte beim Admin melden."
            . " · Your company account$wer is not enabled here or is blocked – please contact your admin.");
    }
    versuch_merken($ip, true);
    [$name, $nr] = [(string)$z[0][0], (int)$z[0][1]];
    if ($erstes) {
        try {                                                // der PC meldet es dem Admin (Push): neuer Benutzer, ggf. ohne Rolle
            sql([['INSERT INTO eingang (zeit_utc, weg, daten, ip, projekt) VALUES (?, ?, ?, ?, NULL)',
                  [$t, '/api/benutzer/eingerichtet', json_encode(['_benutzer' => $name, 'weg' => 'firmenkonto']), $ip]]]);
        } catch (Throwable $x) {}                            // die Anmeldung hängt nie daran
    }
    sitzung_benutzer($name, $nr);
    $_SESSION['sso'] = $kennung;
    sso_stand_melden();
    return $name;
}

/** Für den PC (Einstellungen › Firmen-Anmeldung): Art des Zugangs und Rückkehr-Adresse – ohne Geheimnis. Nur aus
 *  angemeldeten Anfragen geschrieben (die Adresse stammt aus dem Host der Anfrage). */
function sso_stand_melden(): void {
    try {
        $wert = json_encode(['zugang' => sso_zugang_art(), 'rueckweg' => sso_rueckweg(), 'zeit_utc' => jetzt_utc()], JSON_UNESCAPED_SLASHES);
        sql([["INSERT INTO zustand (schluessel, wert) VALUES ('sso_stand', ?) ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert", [$wert]]]);
    } catch (Throwable $x) {}
}

/** Geheimnis bzw. Zertifikat in die Konfigurationsdatei (außerhalb des Web-Ordners). $art: geheimnis | zertifikat | entfernen. */
function sso_zugang_speichern(string $art, string $geheimnis, string $zertifikat, string $schluessel): string {
    $k = konfig();
    unset($k['sso_geheimnis'], $k['sso_zertifikat'], $k['sso_schluessel']);
    if ($art === 'geheimnis') {
        $geheimnis = trim($geheimnis);
        if (strlen($geheimnis) < 8 || strlen($geheimnis) > 1000 || preg_match('/\s/', $geheimnis)) return 'Das Geheimnis sieht nicht richtig aus (8–1000 Zeichen, ohne Leerzeichen).';
        $k['sso_geheimnis'] = $geheimnis;
    } elseif ($art === 'zertifikat') {
        $zertifikat = trim($zertifikat); $schluessel = trim($schluessel);
        $x = @openssl_x509_read($zertifikat);
        $p = @openssl_pkey_get_private($schluessel);
        if ($x === false || $p === false) return 'Zertifikat oder Schlüssel ist nicht lesbar (PEM, „-----BEGIN …“).';
        if (!openssl_x509_check_private_key($x, $p)) return 'Schlüssel und Zertifikat gehören nicht zusammen.';
        if ((openssl_pkey_get_details($p)['type'] ?? -1) !== OPENSSL_KEYTYPE_RSA) return 'Nur RSA-Schlüssel.';
        $k['sso_zertifikat'] = $zertifikat;
        $k['sso_schluessel'] = $schluessel;
    } elseif ($art !== 'entfernen') {
        return 'Bitte wählen: Geheimnis oder Zertifikat.';
    }
    $wo = konfig_schreiben($k);
    if ($wo === '') return 'Konfiguration ließ sich nicht schreiben – Rechte des Ordners prüfen.';
    return $wo === 'inc' ? 'inc' : '';
}
