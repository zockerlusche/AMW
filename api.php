<?php
/* AMW online: Daten für die Seite (aus dem Schaufenster) und der Briefkasten (Antworten, Nachrichten, Halt).
 * Aufruf durch die Seite: api.php?weg=<derselbe Weg wie am PC, z. B. /api/start>
 */
declare(strict_types=1);
require __DIR__ . '/inc/lib.php';

sitzung_starten();
kopfzeilen(false);
header('Content-Type: application/json; charset=utf-8');

function antwort(int $code, $daten): never {
    http_response_code($code);
    echo json_encode($daten, JSON_UNESCAPED_UNICODE);
    exit;
}

if (!angemeldet()) antwort(401, ['fehler' => 'Bitte neu anmelden (Seite neu laden).']);

$weg = (string)($_GET['weg'] ?? '');
$pfad = (string)parse_url($weg, PHP_URL_PATH);
parse_str((string)parse_url($weg, PHP_URL_QUERY), $q);

try {
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!herkunft_ok() || !csrf_ok($_SERVER['HTTP_X_AMW_TOKEN'] ?? null)) antwort(403, ['fehler' => 'nicht erlaubt']);
        $roh = file_get_contents('php://input', false, null, 0, 32768);
        $daten = json_decode((string)$roh, true);
        if (!is_array($daten)) antwort(400, ['fehler' => 'JSON']);
        $frage = preg_match('#^/api/frage/(\d{1,9})/antwort$#', $pfad, $m);
        if (!$frage && !in_array($pfad, ['/api/nachricht', '/api/gelesen', '/api/halt', '/api/weiter'], true)) {
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
        if ($pfad === '/api/gelesen' && (!is_array($daten['ids'] ?? null) || !$daten['ids'] || array_filter($daten['ids'], fn($i) => !is_int($i)))) {
            antwort(400, ['fehler' => 'ids fehlen']);
        }
        $n = (int)sql([['SELECT count(*) FROM eingang WHERE zeit_utc > ?', [jetzt_utc(-3600)]]])[0][0][0];
        if ($n >= SCHREIBEN_JE_STUNDE) antwort(429, ['fehler' => 'zu viele Einträge in der letzten Stunde']);
        sql([['INSERT INTO eingang (zeit_utc, weg, daten, ip) VALUES (?, ?, ?, ?)',
              [jetzt_utc(), $pfad, json_encode($daten, JSON_UNESCAPED_UNICODE), $_SERVER['REMOTE_ADDR'] ?? '?']]]);
        // gleiche Form wie am PC, damit die Seite unverändert bleibt; „unterwegs“ = der PC übernimmt es gleich
        $form = match (true) {
            (bool)$frage => ['status' => ($daten['art'] === 'rueckfrage') ? 'offen' : 'beantwortet'],
            $pfad === '/api/nachricht' => ['an' => array_map('trim', explode(',', (string)$daten['an']))],
            $pfad === '/api/gelesen' => ['erledigt' => count($daten['ids'])],
            $pfad === '/api/halt' => ['halt' => 0],
            default => ['aufgehoben' => 0],
        };
        antwort(200, $form + ['unterwegs' => true]);
    }

    if ($pfad === '/api/suche') antwort(404, ['fehler' => 'Die Suche gibt es online noch nicht – bitte am PC suchen.']);
    $schluessel = $pfad === '/api/aufgaben' ? '/api/aufgaben?sicht=' . (string)($q['sicht'] ?? 'offen')
        : ($pfad === '/api/fragen' && ($q['alle'] ?? '') === '1' ? '/api/fragen?alle=1' : $pfad);
    [$zeile, $pc, $offen] = sql([
        ['SELECT inhalt, stand_utc FROM ansicht WHERE weg = ?', [$schluessel]],
        ["SELECT wert FROM zustand WHERE schluessel = 'pc_gesehen_utc'", []],
        ["SELECT weg, daten FROM eingang WHERE status = 'neu'", []],
    ]);
    if (!$zeile) antwort(404, ['fehler' => 'Noch keine Daten vom PC – läuft der AMW-Dienst mit Abgleich?']);
    $d = json_decode($zeile[0][0], true);
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
    } elseif ($pfad === '/api/fragen') {                  // schon beantwortet, aber noch im Briefkasten → ausblenden
        $d = array_values(array_filter($d, fn($f) => !in_array("/api/frage/{$f['id']}/antwort", $unterwegs, true)));
    } elseif ($pfad === '/api/start') {
        $gesehen = $pc ? $pc[0][0] : null;
        $d['online'] = ['web_version' => trim((string)@file_get_contents(__DIR__ . '/inc/VERSION')), 'pc_gesehen_utc' => $gesehen, 'stand_utc' => $zeile[0][1], 'briefkasten' => count($unterwegs),
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
