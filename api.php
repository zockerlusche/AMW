<?php
/* AMW online: Daten für die Seite (aus dem Schaufenster) und der Briefkasten (Antworten, Nachrichten, Halt).
 * Aufruf durch die Seite: api.php?weg=<derselbe Weg wie am PC, z. B. /api/start>
 */
declare(strict_types=1);
require __DIR__ . '/inc/lib.php';

sitzung_starten();
kopfzeilen(false);
header('Content-Type: application/json; charset=utf-8');

/* Projekt der Anfrage (→ doc/plan-projektwahl.md): Kennung aus dem Verzeichnis, ohne Angabe das erste. Ansichten liegen
 * unter „<Kennung>:<Weg>“; solange der PC noch ohne Kennungen hochlädt (vor 1.19.0), gelten die alten Schlüssel. */
$projekt = '';
$verzeichnis = [];
function ansicht_zeile(string $weg): ?array {
    global $projekt;
    $z = sql([['SELECT inhalt, stand_utc FROM ansicht WHERE weg = ?', [$projekt === '' ? $weg : "$projekt:$weg"]]])[0];
    if (!$z && $projekt !== '') $z = sql([['SELECT inhalt, stand_utc FROM ansicht WHERE weg = ?', [$weg]]])[0];
    return $z ? $z[0] : null;
}

function antwort(int $code, $daten): never {
    http_response_code($code);
    echo json_encode($daten, JSON_UNESCAPED_UNICODE);
    exit;
}

/** Datei eines Dokuments, das am PC auf „auch online“ steht. Wie am PC: HTML (Mockup) und SVG abgeschottet (CSP sandbox),
 *  Office nur als Download. Liegt sie noch nicht auf dem Webspace, wird sie jetzt aus dem Speicher geholt. */
function datei_senden(array $q): never {
    $id = (int)($q['id'] ?? 0);
    $z = ansicht_zeile('/intern/dateien');
    $karte = $z ? json_decode($z[0], true) : [];
    [$sha, $endung] = $karte[$id . ':' . (int)($q['v'] ?? 0)] ?? ['', ''];
    if (!preg_match('/^[0-9a-f]{64}$/', $sha) || !isset(DATEI_FORMATE[$endung])) {
        antwort(404, ['fehler' => 'Diese Datei liegt nur am PC.']);
    }
    $ordner = datei_ordner();
    $p = $ordner === null ? null : datei_pfad($ordner, $sha, $endung);
    $roh = null;
    if ($p === null || !is_file($p)) {
        [$r] = sql([['SELECT status, groesse, teile FROM datei WHERE sha = ?', [$sha]]]);
        if ($r && $r[0][0] === 'abgelegt') sql([['DELETE FROM datei WHERE sha = ?', [$sha]]]);   // Kopie verloren: PC lädt neu
        if (!$r || $r[0][0] === 'abgelegt') antwort(404, ['fehler' => 'Die Datei ist auf dem Weg vom PC – bitte gleich noch einmal.']);
        $roh = datei_abholen($sha, $endung, (int)$r[0][1], (int)$r[0][2]);
        if ($roh === null) antwort(404, ['fehler' => 'Die Datei kommt gleich neu vom PC.']);
    }
    [$typ, $vorschau] = DATEI_FORMATE[$endung];
    $laenge = $roh === null ? filesize($p) : strlen($roh);
    $von = 0; $bis = $laenge - 1;                                   // Video: Vor- und Zurückspulen (Range, ein Bereich)
    if (preg_match('/^bytes=(\d*)-(\d*)$/', $_SERVER['HTTP_RANGE'] ?? '', $m) && ($m[1] !== '' || $m[2] !== '')) {
        if ($m[1] === '') { $von = max(0, $laenge - (int)$m[2]); }
        else { $von = (int)$m[1]; if ($m[2] !== '') $bis = min((int)$m[2], $laenge - 1); }
        if ($von >= $laenge || $bis < $von) { http_response_code(416); header('Content-Range: bytes */' . $laenge); exit; }
        http_response_code(206);
        header("Content-Range: bytes $von-$bis/$laenge");
    }
    header('Accept-Ranges: bytes');
    header('Content-Type: ' . $typ);
    header('Content-Length: ' . (string)($bis - $von + 1));
    header('Cache-Control: private, max-age=86400');               // je Version unveränderlich
    header('X-Frame-Options: SAMEORIGIN');
    header('Referrer-Policy: no-referrer');
    if ($vorschau === 'mockup') {
        header("Content-Security-Policy: sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';"
            . " img-src data: blob:; font-src data:; media-src data: blob:; frame-ancestors 'self'");
    } elseif ($vorschau !== 'pdf') {
        header("Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'");
    }
    header('Content-Disposition: ' . ($vorschau === 'download' ? 'attachment' : 'inline') . '; filename="D' . $id . $endung . '"');
    if ($roh === null) {
        $f = fopen($p, 'rb'); fseek($f, $von); $rest = $bis - $von + 1;
        while ($rest > 0 && !feof($f)) {
            $s = fread($f, min(65536, $rest));
            if ($s === false || $s === '') break;                   // Lesefehler auf dem Webspace: abbrechen statt TypeError/Schleife
            echo $s; $rest -= strlen($s);
        }
        fclose($f);
    } else echo substr($roh, $von, $bis - $von + 1);
    exit;
}

if (!angemeldet()) antwort(401, ['fehler' => 'Bitte neu anmelden (Seite neu laden).']);
$ich = isset($_SESSION['benutzer']) ? benutzer_aktuell() : null;            // angelegter Benutzer (sonst: Zugang der Konfiguration)
if (isset($_SESSION['benutzer']) && $ich === null) antwort(401, ['fehler' => 'Bitte neu anmelden (Seite neu laden).']);
if ($ich !== null && !$ich['rolle']) antwort(403, ['fehler' => 'Dein Zugang wird geprüft – ein Admin vergibt Rolle und Projekte.', 'wartet' => true]);

try {
    nachruesten();
    $verzeichnis = sql([['SELECT uid, name, farbe, rechner, gesehen_utc, fragen, agenten, halt FROM projekt ORDER BY name', []]])[0];
} catch (Throwable $e) {                                  // Speicher von vor 1.19.0 ohne Verzeichnis: alte Schlüssel
    $verzeichnis = [];
}
if ($ich !== null && $ich['rolle'] !== 'system_admin') {   // nur zugewiesene Projekte – andere werden nicht ausgeliefert
    $verzeichnis = array_values(array_filter($verzeichnis, fn($z) => in_array($z[0], $ich['projekte'], true)));
    if (!$verzeichnis) antwort(403, ['fehler' => 'Dir ist noch kein Projekt zugewiesen – bitte beim Admin melden.']);
}
$uids = array_column($verzeichnis, 0);
$wunsch = (string)($_GET['projekt'] ?? '');
$projekt = in_array($wunsch, $uids, true) ? $wunsch : (string)($uids[0] ?? '');

$weg = (string)($_GET['weg'] ?? '');
$pfad = (string)parse_url($weg, PHP_URL_PATH);
parse_str((string)parse_url($weg, PHP_URL_QUERY), $q);
if (!str_starts_with($pfad, '/api/')) antwort(404, ['fehler' => 'unbekannt']);

try {
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!herkunft_ok() || !csrf_ok($_SERVER['HTTP_X_AMW_TOKEN'] ?? null)) antwort(403, ['fehler' => 'nicht erlaubt']);
        $grenze = match ($pfad) { '/api/hochladen' => 400000, '/api/dokument/text' => 2000000, default => 32768 };
        $roh = file_get_contents('php://input', false, null, 0, $grenze);
        $daten = json_decode((string)$roh, true);
        if (!is_array($daten)) antwort(400, ['fehler' => 'JSON']);
        unset($daten['_benutzer']);                         // wer handelt, setzt nur der Server (Anmeldung), nie der Aufrufer
        if (str_starts_with($pfad, '/api/benutzer')) antwort(403, ['fehler' => 'Benutzer verwaltest du am PC.']);
        if ($ich !== null && !rolle_reicht($ich['rolle'], eingabe_klasse($pfad))) {
            antwort(403, ['fehler' => 'Nicht erlaubt – dafür reicht deine Rolle nicht.']);
        }
        $wer = $ich['name'] ?? (!empty($_SESSION['zugang']) ? '@zugang' : null);
        if ($wer === null) antwort(401, ['fehler' => 'Bitte neu anmelden (Seite neu laden).']);   // nie ohne Namen weiter
        $daten['_benutzer'] = $wer;
        if ($pfad === '/api/hochladen') {                  // Teile direkt in den Speicher, nicht über den Briefkasten
            try { antwort(200, hochladen($daten)); }
            catch (InvalidArgumentException $x) { antwort(400, ['fehler' => $x->getMessage()]); }
            catch (LengthException $x) { antwort(429, ['fehler' => $x->getMessage()]); }
        }
        $frage = preg_match('#^/api/frage/(\d{1,9})/antwort$#', $pfad, $m);
        $parken = preg_match('#^/api/frage/(\d{1,9})/(parken|aufnehmen)$#', $pfad);
        if (in_array($pfad, ['/api/einstellungen/pc', '/api/einstellungen/turso', '/api/einstellungen/push', '/api/einstellungen/profil',
                '/api/agent/start', '/api/agent/stop', '/api/agent/ende', '/api/agent/start-fehlende', '/api/dienst/neustart', '/api/push/probe'], true)) {
            antwort(403, ['fehler' => 'Das geht nur am PC.']);
        }
        if ($pfad === '/api/schirm' && !empty($daten['frei']) && $ich !== null && $ich['rolle'] !== 'system_admin') {   // frei online: nur System-Admin
            antwort(403, ['fehler' => 'Bildschirm freigeben darf online nur ein System-Admin – belegen geht für alle.']);
        }
        if (!$frage && !$parken && !in_array($pfad, ['/api/nachricht', '/api/gelesen', '/api/halt', '/api/weiter', '/api/schirm',
                '/api/agent/entfernen', '/api/agent/wiederaufnehmen', '/api/agent/loeschen',
                '/api/einstellungen/projekt', '/api/einstellungen/agent', '/api/einstellungen/web',
                '/api/plan/spec', '/api/plan/planfrei', '/api/plan/leitbild', '/api/plan/bogen', '/api/plan/risiko',
                '/api/plan/rueckblick', '/api/plan/uebernehmen', '/api/plan/check',
                '/api/dokument/kommentar', '/api/dokument/setzen', '/api/dokument/status', '/api/dokument/online',
                '/api/dokument/vermerk', '/api/dokument/text', '/api/dokument/neu', '/api/aufgabe/erledigt', '/api/aufgabe/spaeter', '/api/aufgabe/antwort'], true)) {
            antwort(404, ['fehler' => 'unbekannt']);
        }
        // Prüfen, was der PC sowieso prüft, schon hier – damit Fehler sofort sichtbar sind
        if ($frage && (!in_array($daten['art'] ?? '', ['option', 'text', 'rueckfrage'], true) || trim((string)($daten['wert'] ?? '')) === '')) {
            antwort(400, ['fehler' => 'art/wert fehlt']);
        }
        if ($pfad === '/api/nachricht' && (trim((string)($daten['an'] ?? '')) === '' || trim((string)($daten['kurz'] ?? '')) === '')) {
            antwort(400, ['fehler' => 'an/kurz fehlt']);
        }
        if ($pfad === '/api/nachricht' && !in_array($daten['art'] ?? 'auftrag', ['auftrag', 'frage', 'info', 'korrektur', 'freigabe'], true)) {
            antwort(400, ['fehler' => 'Art nicht erlaubt']);
        }
        if (str_starts_with($pfad, '/api/dokument/') && $pfad !== '/api/dokument/neu' && (!is_int($daten['id'] ?? null) || $daten['id'] < 1)) antwort(400, ['fehler' => 'id fehlt']);
        if ($pfad === '/api/dokument/text') {               // berichtigen: Konflikt schon hier erkennen (der PC prüft noch einmal)
            $text = $daten['text'] ?? null;
            if (!is_string($text) || trim($text) === '' || mb_strlen($text) > 400000 || !is_int($daten['basis'] ?? null)) antwort(400, ['fehler' => 'Text oder Version fehlt']);
            $z = ansicht_zeile('/api/dokument?id=' . $daten['id']);
            $neueste = $z ? max(array_column(json_decode($z[0], true)['versionen'] ?? [], 'nr') ?: [0]) : 0;
            if ($neueste && $neueste !== $daten['basis']) antwort(409, ['fehler' => "Inzwischen gibt es v$neueste – nichts gespeichert. Dein Text bleibt im Editor; vergleiche mit der neuen Version und speichere dann erneut.", 'neueste' => $neueste]);
        }
        if ($pfad === '/api/dokument/neu') {
            if (!preg_match('/^[0-9a-f]{32}$/', (string)($daten['hoch'] ?? '')) || mb_strlen((string)($daten['titel'] ?? '')) > 200
                || !in_array($daten['art'] ?? '', ['', 'ergebnis', 'bericht', 'entwurf', 'mockup', 'bild', 'quelle'], true)) antwort(400, ['fehler' => 'Upload, Titel oder Art']);
            try { hoch_abschliessen((string)$daten['hoch']); }
            catch (InvalidArgumentException $x) { antwort(400, ['fehler' => $x->getMessage()]); }
        }
        if ($pfad === '/api/dokument/kommentar' && trim((string)($daten['text'] ?? '')) === '') antwort(400, ['fehler' => 'Text fehlt']);
        if (str_starts_with($pfad, '/api/aufgabe/') && (!is_int($daten['id'] ?? null) || $daten['id'] < 1)) antwort(400, ['fehler' => 'id fehlt']);
        if (in_array($pfad, ['/api/aufgabe/erledigt', '/api/aufgabe/antwort'], true) && trim((string)($daten['text'] ?? '')) === '') antwort(400, ['fehler' => 'Text fehlt']);
        if ($pfad === '/api/dokument/vermerk' && !in_array($daten['art'] ?? '', ['ausgewaehlt', 'verworfen', 'nachbearbeitet'], true)) antwort(400, ['fehler' => 'Art']);
        if ($pfad === '/api/dokument/vermerk' && ($daten['art'] ?? '') === 'nachbearbeitet' && mb_strlen(trim((string)($daten['text'] ?? ''))) < 5) antwort(400, ['fehler' => 'Text fehlt']);
        if ($pfad === '/api/dokument/status' && !in_array($daten['status'] ?? '', ['aktuell', 'archiviert'], true)) antwort(400, ['fehler' => 'Status']);
        if ($pfad === '/api/gelesen' && (!is_array($daten['ids'] ?? null) || !$daten['ids'] || array_filter($daten['ids'], fn($i) => !is_int($i)))) {
            antwort(400, ['fehler' => 'ids fehlen']);
        }
        $n = (int)sql([['SELECT count(*) FROM eingang WHERE zeit_utc > ?', [jetzt_utc(-3600)]]])[0][0][0];
        if ($n >= SCHREIBEN_JE_STUNDE) antwort(429, ['fehler' => 'zu viele Einträge in der letzten Stunde']);
        $eid = (int)(sql([['INSERT INTO eingang (zeit_utc, weg, daten, ip, projekt) VALUES (?, ?, ?, ?, ?) RETURNING id',   // nur der Rechner des Projekts führt es aus
              [jetzt_utc(), $pfad, json_encode($daten, JSON_UNESCAPED_UNICODE), $_SERVER['REMOTE_ADDR'] ?? '?', $projekt === '' ? null : $projekt]]])[0][0][0] ?? 0);
        $_SESSION['eingaenge'] = array_slice([...($_SESSION['eingaenge'] ?? []), $eid], -100);   // nur diese Sitzung fragt ihren Stand ab
        // gleiche Form wie am PC, damit die Seite unverändert bleibt; „unterwegs“ = der PC übernimmt es gleich
        $form = match (true) {
            (bool)$frage => ['status' => ($daten['art'] === 'rueckfrage') ? 'offen' : 'beantwortet'],
            (bool)$parken => ['status' => str_ends_with($pfad, '/parken') ? 'geparkt' : 'offen'],
            $pfad === '/api/nachricht' => ['an' => array_map('trim', explode(',', (string)$daten['an']))],
            $pfad === '/api/gelesen' => ['erledigt' => count($daten['ids'])],
            str_starts_with($pfad, '/api/einstellungen/'), str_starts_with($pfad, '/api/plan/'), str_starts_with($pfad, '/api/dokument/'), str_starts_with($pfad, '/api/aufgabe/') => [],
            $pfad === '/api/halt' => ['halt' => 0],
            $pfad === '/api/schirm' => ['text' => empty($daten['frei']) ? 'Bildschirm wird belegt' : 'Bildschirm wird freigegeben'],
            default => ['aufgehoben' => 0],
        };
        antwort(200, $form + ['unterwegs' => true, 'eingang' => $eid]);
    }

    if ($pfad === '/api/eingang') {                       // Stand eigener Eingaben: neu → erledigt | fehler (mit Grund)
        $ids = array_values(array_intersect(array_map('intval', explode(',', (string)($q['ids'] ?? ''))), $_SESSION['eingaenge'] ?? []));
        if (!$ids) antwort(200, []);
        $z = sql([['SELECT id, status, ergebnis FROM eingang WHERE id IN (' . implode(',', array_fill(0, count($ids), '?')) . ')', $ids]])[0];
        antwort(200, array_map(fn($r) => ['id' => (int)$r[0], 'status' => $r[1], 'fehler' => $r[1] === 'fehler' ? ((json_decode((string)$r[2], true)['fehler'] ?? null) ?: 'Fehler am PC') : null], $z));
    }
    if ($pfad === '/api/projekte' && $verzeichnis) {      // Verzeichnis aller Projekte (auch anderer Rechner)
        $aus = [];
        foreach ($verzeichnis as [$uid, $name, $farbe, $rechner, $gesehen, $fragen, $agenten, $halt]) {
            $aus[] = ['uid' => $uid, 'name' => $name, 'farbe' => $farbe, 'rechner' => $rechner, 'gesehen_utc' => $gesehen,
                      'fragen' => (int)$fragen, 'agenten' => (int)$agenten, 'halt' => (bool)(int)$halt, 'aktiv' => $uid === $projekt,
                      'erreichbar' => strtotime((string)$gesehen) > time() - 7 * 86400];
        }
        antwort(200, ['projekte' => $aus, 'rechner' => null]);
    }
    if ($pfad === '/api/suche') {                         // im Suchindex vom PC (Nachrichten: die letzten 2000, nur Kurztext)
        $such = mb_strtolower(trim((string)($q['q'] ?? '')));
        if (mb_strlen($such) < 2) antwort(200, []);
        $z = ansicht_zeile('/api/suchindex');
        if (!$z) antwort(404, ['fehler' => 'Noch kein Suchindex vom PC – bitte in ein paar Minuten noch einmal.']);
        $eintraege = json_decode((string)gzuncompress(base64_decode(json_decode($z[0], true)['gepackt'] ?? '')), true) ?: [];
        $treffer = [];
        $je_art = [];
        foreach ($eintraege as [$art, $ref, $titel, $text, $zusatz, $zeit]) {
            if (($je_art[$art] ?? 0) >= 25) continue;
            if (mb_stripos((string)$titel . ' ' . (string)$text, $such) === false) continue;
            $je_art[$art] = ($je_art[$art] ?? 0) + 1;
            $treffer[] = ['art' => $art, 'ref' => $ref, 'titel' => $titel, 'zusatz' => $zusatz, 'zeit' => $zeit];
        }
        antwort(200, $treffer);
    }
    if ($pfad === '/api/seit') {                           // „Seit du weg warst“: Zeitpunkte vom PC, gezählt ab dem Besuch dieses Geräts
        $ab = (string)($q['ab'] ?? '');
        if (!preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/', $ab)) antwort(400, ['fehler' => 'ab']);
        $z = ansicht_zeile('/api/seit');
        if (!$z) antwort(404, ['fehler' => 'Noch keine Daten vom PC.']);
        $d = json_decode($z[0], true);
        $aus = array_fill_keys(['an_dich', 'erledigt', 'laeufe', 'gruen', 'rot', 'fragen_neu', 'beschluesse', 'boegen_fertig'], 0);
        foreach ($d['ereignisse'] as [$zeit, $art]) {
            if (strcmp((string)$zeit, $ab) >= 0 && isset($aus[$art])) $aus[$art]++;
        }
        $aus['fragen_offen'] = (int)$d['fragen_offen'];
        $hl = array_values(array_filter($d['highlights'], fn($h) => strcmp((string)$h['zeit'], $ab) >= 0));
        $aus['highlights'] = array_map(fn($h) => ['id' => $h['id'], 'titel' => $h['titel'], 'agent' => $h['agent']], array_slice($hl, 0, 5));
        antwort(200, $aus);
    }
    if ($pfad === '/api/dokument/datei') datei_senden($q);
    if ($pfad === '/api/agent') {                          // Übersicht je Agent: aus dem Schaufenster „/api/agenten“
        $z = ansicht_zeile('/api/agenten');
        $alle = $z ? json_decode($z[0], true) : [];
        $k = (string)($q['kennung'] ?? '');
        if (!isset($alle[$k])) antwort(404, ['fehler' => 'Zu diesem Agenten liegen online noch keine Daten vor.']);
        $a = einstellungen_ueberlagern(['agenten' => [$alle[$k] + ['kennung' => $k]]], briefkasten_wirkt($projekt, $z[1] ?? null))['agenten'][0];
        antwort(200, $a);
    }
    if ($pfad === '/api/gespraech') {                      // Gespräch je Agent: nur auf Wunsch, der PC hält es dann 10 min aktuell
        $k = (string)($q['kennung'] ?? '');
        $z = ansicht_zeile('/api/agenten');
        $alle = $z ? json_decode($z[0], true) : [];
        if (!preg_match('/^[A-Za-z0-9_-]{1,40}$/', $k) || !isset($alle[$k])) antwort(404, ['fehler' => 'Diesen Agenten gibt es online nicht.']);
        $wunsch_schl = 'gespraech:' . ($projekt === '' ? '' : "$projekt:") . $k;    // der Rechner des Projekts hält es aktuell
        [$w] = sql([['SELECT wert FROM zustand WHERE schluessel = ?', [$wunsch_schl]]]);
        $g = ansicht_zeile('/api/gespraech?kennung=' . $k);
        if (!$w || strcmp((string)$w[0][0], jetzt_utc(-60)) < 0) {
            sql([['INSERT INTO zustand (schluessel, wert) VALUES (?, ?) ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert',
                  [$wunsch_schl, jetzt_utc()]]]);
        }
        if (!$g) antwort(200, ['kennung' => $k, 'warten' => true]);
        antwort(200, json_decode($g[0], true) + ['stand_utc' => $g[1]]);
    }
    $schluessel = match (true) {
        $pfad === '/api/aufgaben' => '/api/aufgaben?sicht=' . (string)($q['sicht'] ?? 'offen'),
        $pfad === '/api/fragen' && ($q['alle'] ?? '') === '1' => '/api/fragen?alle=1',
        $pfad === '/api/dokument' => '/api/dokument?id=' . (int)($q['id'] ?? 0),
        $pfad === '/api/thema' => '/api/thema?id=' . (int)($q['id'] ?? 0),
        $pfad === '/api/aufgabe' => '/api/aufgabe?id=' . (int)($q['id'] ?? 0),
        default => $pfad,
    };
    $zeile = ansicht_zeile($schluessel);
    [$pc, $neu] = sql([
        ['SELECT wert FROM zustand WHERE schluessel = ?', [$projekt === '' ? 'pc_gesehen_utc' : "pc_gesehen_utc:$projekt"]],
        ["SELECT sha, endung, groesse, teile FROM datei WHERE status = 'unterwegs' ORDER BY groesse LIMIT 3", []],
    ]);
    $offen = briefkasten_wirkt($projekt, $zeile[1] ?? null);   // was der Mensch getan hat und diese Ansicht noch nicht zeigt
    register_shutdown_function('dateien_nachholen', $neu);
    if (!$zeile && $pfad === '/api/dokument') antwort(404, ['fehler' => 'Dieses Dokument gibt es online (noch) nicht.']);
    if (!$zeile) antwort(404, ['fehler' => 'Noch keine Daten vom PC – läuft der AMW-Dienst mit Abgleich?']);
    $d = json_decode($zeile[0], true);
    $unterwegs = array_column($offen, 0);

    if ($pfad === '/api/aufgaben') {                      // Filter wie am PC, hier auf der fertigen Liste
        $agent = (string)($q['agent'] ?? '');
        $such = mb_strtolower(trim((string)($q['q'] ?? '')));
        $d = array_values(array_filter($d, fn($a) => ($agent === '' || $a['agent'] === $agent)
            && ($such === '' || str_contains(mb_strtolower((string)$a['titel']), $such))));
    } elseif ($pfad === '/api/wissen' && trim((string)($q['q'] ?? '')) !== '') {
        $such = mb_strtolower(trim((string)$q['q']));
        $hat = fn(...$t) => str_contains(mb_strtolower(implode(' ', array_map('strval', $t))), $such);
        $d['beschluesse'] = array_values(array_filter($d['beschluesse'], fn($b) => $hat($b['stichwort'], $b['regel'])));
        $d['wortlaut'] = array_values(array_filter($d['wortlaut'], fn($w) => $hat($w['text'])));
        $d['regeln'] = array_values(array_filter($d['regeln'], fn($r) => $hat($r['text'])));
    } elseif ($pfad === '/api/fragen') {
        // Antworten im Briefkasten: beantwortet → ausblenden; Rückfrage → als Blase „unterwegs“ an den Verlauf hängen
        // Parken im Briefkasten: aus der offenen Liste nehmen bzw. (geparkte zeigen) schon als geparkt/offen kennzeichnen
        $wartend = [];
        $park = [];
        foreach ($offen as [$w, $dat]) {
            if (preg_match('#^/api/frage/(\d+)/antwort$#', $w, $m)) $wartend[(int)$m[1]][] = json_decode($dat, true);
            if (preg_match('#^/api/frage/(\d+)/(parken|aufnehmen)$#', $w, $m)) $park[(int)$m[1]] = $m[2] === 'parken';
        }
        $alle = ($q['alle'] ?? '') === '1';
        $aus = [];
        foreach ($d as $f) {
            $liste = $wartend[(int)$f['id']] ?? [];
            if (array_filter($liste, fn($x) => ($x['art'] ?? '') !== 'rueckfrage')) continue;
            if (isset($park[(int)$f['id']])) {
                if ($park[(int)$f['id']] && !$alle) continue;
                $f['geparkt_utc'] = $park[(int)$f['id']] ? jetzt_utc() : null;
                $f['geparkt_von'] = $park[(int)$f['id']] ? 'Entwickler' : null;
            }
            foreach ($liste as $x) {
                $f['verlauf'][] = ['zeit_utc' => jetzt_utc(), 'von' => 'Entwickler', 'art' => 'rueckfrage', 'text' => (string)($x['wert'] ?? ''), 'unterwegs' => true];
                $f['wartet_auf_fragesteller'] = true;
            }
            $aus[] = $f;
        }
        $d = $aus;
    } elseif ($pfad === '/api/dokumente') {               // Filter wie am PC (amw/dokumente.py liste), hier auf der ganzen Liste
        $status = (string)($q['status'] ?? 'aktuell');
        $such = mb_strtolower(trim((string)($q['q'] ?? '')));
        $gleich = fn($x, string $k) => ($q[$k] ?? '') === '' || (string)$x === (string)$q[$k];
        $d['dokumente'] = array_values(array_filter($d['dokumente'], fn($x) => ($status === 'alle' || $x['status'] === $status)
            && $gleich($x['art'], 'art') && $gleich($x['angelegt_von'], 'von') && $gleich($x['bezug_art'], 'bezug_art')
            && $gleich($x['bezug_id'], 'bezug_id') && ($such === '' || str_contains((string)$x['such'], $such))));
        foreach ($d['dokumente'] as &$x) unset($x['such']);
        unset($x);
    } elseif ($pfad === '/api/dokument') {                 // gewählte Version; Texte liegen für alle Versionen bei
        $nr = (int)($q['v'] ?? 0);
        $nummern = array_column($d['versionen'], 'nr');
        $d['gezeigt'] = in_array($nr, $nummern, true) ? $nr : max($nummern);
        if (isset($d['texte'][(string)$d['gezeigt']])) $d['text'] = $d['texte'][(string)$d['gezeigt']];
        unset($d['texte']);
    } elseif ($pfad === '/api/einstellungen') {          // Online-Seite: aktuelle Werte, nicht der Stand des Schaufensters
        $d['web'] = web_einst_alle(true);
        $d = einstellungen_ueberlagern($d, $offen);       // gespeichert, aber noch nicht angekommen: der neue Wert gilt
    } elseif ($pfad === '/api/start') {
        $gesehen = $pc ? $pc[0][0] : null;
        $d['online'] = ['ich' => $ich !== null ? ['name' => $ich['name'], 'rolle' => $ich['rolle']] : ['name' => null, 'rolle' => 'system_admin'],
                        'web_version' => trim((string)@file_get_contents(__DIR__ . '/inc/VERSION')), 'pc_gesehen_utc' => $gesehen, 'stand_utc' => $zeile[1], 'briefkasten' => count($unterwegs),
                        'pc_frisch' => $gesehen !== null && strtotime($gesehen) > time() - 420];
        $offeneFragen = count(array_filter($unterwegs, fn($w) => str_starts_with($w, '/api/frage/')));
        if (isset($d['zaehler']['fragen'])) $d['zaehler']['fragen'] = max(0, $d['zaehler']['fragen'] - $offeneFragen);
        $gelesen = [];                                    // schon als gelesen markiert, aber noch im Briefkasten
        foreach ($offen as [$w, $dat]) if ($w === '/api/gelesen') $gelesen = array_merge($gelesen, json_decode($dat, true)['ids'] ?? []);
        if (isset($d['an_dich'])) $d['an_dich'] = array_values(array_filter($d['an_dich'], fn($n) => !in_array($n['id'], $gelesen, true)));
    }
    antwort(200, $d);
} catch (RuntimeException $e) {
    antwort(503, ['fehler' => 'Speicher nicht erreichbar – bitte gleich noch einmal.']);
}
