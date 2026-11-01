<?php
/* QR-Code als SVG, ohne fremde Bibliothek (für die Einrichtung des zweiten Faktors, doc/12).
 * Byte-Modus, Fehlerkorrektur M, Version 1–10 (bis 213 Bytes). Ablauf nach ISO/IEC 18004, aufgebaut wie der
 * „QR Code generator“ von Project Nayuki (MIT): Daten → Reed-Solomon → Verschränken → Muster → Maske → SVG.
 */
declare(strict_types=1);

const QR_ECC_M = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26];   // Korrektur-Codewörter je Block, Version 1–10
const QR_BLOECKE_M = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5];        // Anzahl Blöcke

function qr_mul(int $x, int $y): int {
    $z = 0;
    for ($i = 7; $i >= 0; $i--) {
        $z = (($z << 1) ^ (($z >> 7) * 0x11D)) & 0xFF;
        $z ^= (($y >> $i) & 1) * $x;
    }
    return $z;
}

function qr_rs_teiler(int $grad): array {
    $r = array_fill(0, $grad, 0);
    $r[$grad - 1] = 1;
    $wurzel = 1;
    for ($i = 0; $i < $grad; $i++) {
        for ($j = 0; $j < $grad; $j++) {
            $r[$j] = qr_mul($r[$j], $wurzel);
            if ($j + 1 < $grad) $r[$j] ^= $r[$j + 1];
        }
        $wurzel = qr_mul($wurzel, 0x02);
    }
    return $r;
}

function qr_rs_rest(array $daten, array $teiler): array {
    $r = array_fill(0, count($teiler), 0);
    foreach ($daten as $b) {
        $f = $b ^ array_shift($r);
        $r[] = 0;
        foreach ($teiler as $i => $t) $r[$i] ^= qr_mul($t, $f);
    }
    return $r;
}

function qr_roh_module(int $v): int {
    $n = (16 * $v + 128) * $v + 64;
    if ($v >= 2) {
        $a = intdiv($v, 7) + 2;
        $n -= (25 * $a - 10) * $a - 55;
        if ($v >= 7) $n -= 36;
    }
    return $n;
}

function qr_ausrichtung(int $v): array {
    if ($v === 1) return [];
    $anzahl = intdiv($v, 7) + 2;
    $schritt = (int)ceil(($v * 4 + 4) / ($anzahl * 2 - 2)) * 2;
    $r = [6];
    for ($p = $v * 4 + 10; count($r) < $anzahl; $p -= $schritt) array_splice($r, 1, 0, [$p]);
    return $r;
}

/** Liefert die Modul-Matrix [y][x] (true = dunkel). */
function qr_matrix(string $text): array {
    $bytes = array_values(unpack('C*', $text));
    for ($v = 1; $v <= 10; $v++) {
        $kap = intdiv(qr_roh_module($v), 8) - QR_ECC_M[$v] * QR_BLOECKE_M[$v];
        $zaehl = $v <= 9 ? 8 : 16;
        if (4 + $zaehl + 8 * count($bytes) <= $kap * 8) break;
    }
    if ($v > 10) throw new InvalidArgumentException('Text zu lang für den QR-Code');

    // Bitfolge: Modus Byte (0100), Länge, Daten, Ende, auffüllen
    $bits = [];
    $hin = function (int $wert, int $n) use (&$bits) { for ($i = $n - 1; $i >= 0; $i--) $bits[] = ($wert >> $i) & 1; };
    $hin(4, 4);
    $hin(count($bytes), $zaehl);
    foreach ($bytes as $b) $hin($b, 8);
    $hin(0, min(4, $kap * 8 - count($bits)));
    $hin(0, (8 - count($bits) % 8) % 8);
    for ($pad = 0xEC; count($bits) < $kap * 8; $pad ^= 0xEC ^ 0x11) $hin($pad, 8);
    $daten = [];
    foreach (array_chunk($bits, 8) as $c) $daten[] = (int)bindec(implode('', $c));

    // Reed-Solomon je Block, dann verschränken
    $bloecke_n = QR_BLOECKE_M[$v];
    $ecc_n = QR_ECC_M[$v];
    $roh = intdiv(qr_roh_module($v), 8);
    $kurz_n = $bloecke_n - $roh % $bloecke_n;
    $kurz_len = intdiv($roh, $bloecke_n);
    $teiler = qr_rs_teiler($ecc_n);
    $bloecke = [];
    for ($i = 0, $k = 0; $i < $bloecke_n; $i++) {
        $len = $kurz_len - $ecc_n + ($i < $kurz_n ? 0 : 1);
        $d = array_slice($daten, $k, $len);
        $k += $len;
        $e = qr_rs_rest($d, $teiler);
        if ($i < $kurz_n) $d[] = 0;
        $bloecke[] = array_merge($d, $e);
    }
    $folge = [];
    for ($i = 0; $i < count($bloecke[0]); $i++) {
        foreach ($bloecke as $j => $b) {
            if ($i !== $kurz_len - $ecc_n || $j >= $kurz_n) $folge[] = $b[$i];
        }
    }

    // Funktionsmuster
    $g = $v * 4 + 17;
    $m = array_fill(0, $g, array_fill(0, $g, false));
    $fn = array_fill(0, $g, array_fill(0, $g, false));
    $setze = function (int $x, int $y, bool $dunkel) use (&$m, &$fn) { $m[$y][$x] = $dunkel; $fn[$y][$x] = true; };
    for ($i = 0; $i < $g; $i++) { $setze(6, $i, $i % 2 === 0); $setze($i, 6, $i % 2 === 0); }
    foreach ([[3, 3], [$g - 4, 3], [3, $g - 4]] as [$cx, $cy]) {
        for ($dy = -4; $dy <= 4; $dy++) for ($dx = -4; $dx <= 4; $dx++) {
            $x = $cx + $dx; $y = $cy + $dy;
            if ($x >= 0 && $x < $g && $y >= 0 && $y < $g) { $d = max(abs($dx), abs($dy)); $setze($x, $y, $d !== 2 && $d !== 4); }
        }
    }
    $pos = qr_ausrichtung($v);
    $n = count($pos);
    for ($i = 0; $i < $n; $i++) for ($j = 0; $j < $n; $j++) {
        if (($i === 0 && $j === 0) || ($i === 0 && $j === $n - 1) || ($i === $n - 1 && $j === 0)) continue;
        for ($dy = -2; $dy <= 2; $dy++) for ($dx = -2; $dx <= 2; $dx++) $setze($pos[$i] + $dx, $pos[$j] + $dy, max(abs($dx), abs($dy)) !== 1);
    }
    $format = function (int $maske) use ($setze, $g) {
        $d = (0 << 3) | $maske;                         // Fehlerkorrektur M = 00
        $r = $d;
        for ($i = 0; $i < 10; $i++) $r = ($r << 1) ^ (($r >> 9) * 0x537);
        $b = (($d << 10) | $r) ^ 0x5412;
        $bit = fn(int $i) => (($b >> $i) & 1) === 1;
        for ($i = 0; $i <= 5; $i++) $setze(8, $i, $bit($i));
        $setze(8, 7, $bit(6)); $setze(8, 8, $bit(7)); $setze(7, 8, $bit(8));
        for ($i = 9; $i < 15; $i++) $setze(14 - $i, 8, $bit($i));
        for ($i = 0; $i < 8; $i++) $setze($g - 1 - $i, 8, $bit($i));
        for ($i = 8; $i < 15; $i++) $setze(8, $g - 15 + $i, $bit($i));
        $setze(8, $g - 8, true);
    };
    $format(0);
    if ($v >= 7) {
        $r = $v;
        for ($i = 0; $i < 12; $i++) $r = ($r << 1) ^ (($r >> 11) * 0x1F25);
        $b = ($v << 12) | $r;
        for ($i = 0; $i < 18; $i++) {
            $bit = (($b >> $i) & 1) === 1;
            $a = $g - 11 + $i % 3; $c = intdiv($i, 3);
            $setze($a, $c, $bit); $setze($c, $a, $bit);
        }
    }

    // Daten im Zickzack eintragen
    $i = 0;
    $gesamt = count($folge) * 8;
    for ($rechts = $g - 1; $rechts >= 1; $rechts -= 2) {
        if ($rechts === 6) $rechts = 5;
        for ($s = 0; $s < $g; $s++) for ($j = 0; $j < 2; $j++) {
            $x = $rechts - $j;
            $y = (($rechts + 1) & 2) === 0 ? $g - 1 - $s : $s;
            if (!$fn[$y][$x] && $i < $gesamt) { $m[$y][$x] = (($folge[$i >> 3] >> (7 - ($i & 7))) & 1) === 1; $i++; }
        }
    }

    // Maske mit der kleinsten Strafe wählen (Regeln: Läufe, 2×2-Blöcke, Hell/Dunkel-Verhältnis)
    $maskiert = function (int $k) use ($m, $fn, $g): array {
        $r = $m;
        for ($y = 0; $y < $g; $y++) for ($x = 0; $x < $g; $x++) {
            if ($fn[$y][$x]) continue;
            $inv = match ($k) {
                0 => ($x + $y) % 2 === 0, 1 => $y % 2 === 0, 2 => $x % 3 === 0, 3 => ($x + $y) % 3 === 0,
                4 => (intdiv($x, 3) + intdiv($y, 2)) % 2 === 0, 5 => $x * $y % 2 + $x * $y % 3 === 0,
                6 => ($x * $y % 2 + $x * $y % 3) % 2 === 0, default => (($x + $y) % 2 + $x * $y % 3) % 2 === 0,
            };
            if ($inv) $r[$y][$x] = !$r[$y][$x];
        }
        return $r;
    };
    $strafe = function (array $q) use ($g): int {
        $p = 0; $dunkel = 0;
        for ($a = 0; $a < $g; $a++) {
            foreach ([true, false] as $zeile) {
                $lauf = 0; $vorher = null;
                for ($b = 0; $b < $g; $b++) {
                    $c = $zeile ? $q[$a][$b] : $q[$b][$a];
                    if ($c === $vorher) { $lauf++; if ($lauf === 5) $p += 3; elseif ($lauf > 5) $p++; }
                    else { $lauf = 1; $vorher = $c; }
                }
            }
            for ($b = 0; $b < $g; $b++) if ($q[$a][$b]) $dunkel++;
        }
        for ($y = 0; $y < $g - 1; $y++) for ($x = 0; $x < $g - 1; $x++) {
            $c = $q[$y][$x];
            if ($c === $q[$y][$x + 1] && $c === $q[$y + 1][$x] && $c === $q[$y + 1][$x + 1]) $p += 3;
        }
        $p += intdiv(abs($dunkel * 20 - $g * $g * 10), $g * $g) * 10;
        return $p;
    };
    $beste = null; $beste_p = PHP_INT_MAX;
    for ($k = 0; $k < 8; $k++) {
        $format($k);
        $q = $maskiert($k);
        // Formatbits gehören zur Maske: aus $m (mit $format($k) gesetzt) übernehmen
        for ($y = 0; $y < $g; $y++) for ($x = 0; $x < $g; $x++) if ($fn[$y][$x]) $q[$y][$x] = $m[$y][$x];
        $p = $strafe($q);
        if ($p < $beste_p) { $beste_p = $p; $beste = $q; }
    }
    return $beste;
}

function qr_svg(string $text, int $punkt = 6): string {
    $q = qr_matrix($text);
    $g = count($q);
    $rand = 4;
    $w = ($g + 2 * $rand) * $punkt;
    $pfad = '';
    for ($y = 0; $y < $g; $y++) for ($x = 0; $x < $g; $x++) {
        if ($q[$y][$x]) $pfad .= 'M' . (($x + $rand) * $punkt) . ' ' . (($y + $rand) * $punkt) . "h{$punkt}v{$punkt}h-{$punkt}z";
    }
    return "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"$w\" height=\"$w\" viewBox=\"0 0 $w $w\" role=\"img\""
        . " aria-label=\"QR-Code\" shape-rendering=\"crispEdges\"><rect width=\"100%\" height=\"100%\" fill=\"#fff\"/>"
        . "<path d=\"$pfad\" fill=\"#000\"/></svg>";
}
