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
        if (in_array($pfad, ['/api/einstellungen/pc', '/api/einstellungen/turso', '/api/einstellungen/push', '/api/einstellungen/profil',
                '/api/agent/start', '/api/agent/stop', '/api/push/probe'], true)) {
            antwort(403, ['fehler' => 'Das geht nur am PC.']);
        }
        if (!$frage && !in_array($pfad, ['/api/nachricht', '/api/gelesen', '/api/halt', '/api/weiter',
                '/api/einstellungen/projekt', '/api/einstellungen/agent', '/api/einstellungen/web',
                '/api/plan/spec', '/api/plan/planfrei', '/api/plan/leitbild', '/api/plan/bogen', '/api/plan/risiko',
                '/api/plan/rueckblick', '/api/plan/uebernehmen'], true)) {
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
            str_starts_with($pfad, '/api/einstellungen/'), str_starts_with($pfad, '/api/plan/') => [],
            $pfad === '/api/halt' => ['halt' => 0],
            default => ['aufgehoben' => 0],
        };
        antwort(200, $form + ['unterwegs' => true]);
    }

    if ($pfad === '/api/suche') {                         // im Suchindex vom PC (Nachrichten: die letzten 2000, nur Kurztext)
        $such = mb_strtolower(trim((string)($q['q'] ?? '')));
        if (mb_strlen($such) < 2) antwort(200, []);
        $z = sql([["SELECT inhalt FROM ansicht WHERE weg = '/api/suchindex'", []]])[0];
        if (!$z) antwort(404, ['fehler' => 'Noch kein Suchindex vom PC – bitte in ein paar Minuten noch einmal.']);
        $eintraege = json_decode((string)gzuncompress(base64_decode(json_decode($z[0][0], true)['gepackt'] ?? '')), true) ?: [];
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
        $z = sql([["SELECT inhalt FROM ansicht WHERE weg = '/api/seit'", []]])[0];
        if (!$z) antwort(404, ['fehler' => 'Noch keine Daten vom PC.']);
        $d = json_decode($z[0][0], true);
        $aus = array_fill_keys(['an_dich', 'erledigt', 'laeufe', 'gruen', 'rot', 'fragen_neu', 'beschluesse', 'boegen_fertig'], 0);
        foreach ($d['ereignisse'] as [$zeit, $art]) {
            if (strcmp((string)$zeit, $ab) >= 0 && isset($aus[$art])) $aus[$art]++;
        }
        $aus['fragen_offen'] = (int)$d['fragen_offen'];
        $hl = array_values(array_filter($d['highlights'], fn($h) => strcmp((string)$h['zeit'], $ab) >= 0));
        $aus['highlights'] = array_map(fn($h) => ['id' => $h['id'], 'titel' => $h['titel'], 'agent' => $h['agent']], array_slice($hl, 0, 5));
        antwort(200, $aus);
    }
    if ($pfad === '/api/agent') {                          // Übersicht je Agent: aus dem Schaufenster „/api/agenten“
        $z = sql([["SELECT inhalt FROM ansicht WHERE weg = '/api/agenten'", []]])[0];
        $alle = $z ? json_decode($z[0][0], true) : [];
        $k = (string)($q['kennung'] ?? '');
        if (!isset($alle[$k])) antwort(404, ['fehler' => 'Zu diesem Agenten liegen online noch keine Daten vor.']);
        antwort(200, $alle[$k]);
    }
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
    } elseif ($pfad === '/api/fragen') {
        // Antworten im Briefkasten: beantwortet → ausblenden; Rückfrage → als Blase „unterwegs“ an den Verlauf hängen
        $wartend = [];
        foreach ($offen as [$w, $dat]) if (preg_match('#^/api/frage/(\d+)/antwort$#', $w, $m)) $wartend[(int)$m[1]][] = json_decode($dat, true);
        $aus = [];
        foreach ($d as $f) {
            $liste = $wartend[(int)$f['id']] ?? [];
            if (array_filter($liste, fn($x) => ($x['art'] ?? '') !== 'rueckfrage')) continue;
            foreach ($liste as $x) {
                $f['verlauf'][] = ['zeit_utc' => jetzt_utc(), 'von' => 'Entwickler', 'art' => 'rueckfrage', 'text' => (string)($x['wert'] ?? ''), 'unterwegs' => true];
                $f['wartet_auf_fragesteller'] = true;
            }
            $aus[] = $f;
        }
        $d = $aus;
    } elseif ($pfad === '/api/einstellungen') {          // Online-Seite: aktuelle Werte, nicht der Stand des Schaufensters
        $d['web'] = web_einst_alle(true);
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
