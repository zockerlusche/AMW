<?php
/* Vorlage für amw-konfig.php – die echte Datei liegt AUSSERHALB des Web-Ordners (bei Hostinger eine Ebene über
 * public_html) und nie im Repo. Erzeugen: php F:\amw\werkzeug\web_zugang.php (fragt das Passwort ab).
 */
return [
    'turso_url'     => 'https://amw-<name>.aws-eu-central-1.turso.io',
    'turso_token'   => '<eigener Datenbank-Schlüssel nur für die Seite>',
    'benutzer'      => '<frei gewählt>',
    'passwort_hash' => '<password_hash(), von web_zugang.php>',
    'totp_geheim'   => '<Base32, von web_zugang.php – in die Authenticator-App>',
    'nur_https'     => true,
    // 'sqlite'     => 'C:/…/probe.db',   // nur für die Probe am PC statt Turso
];
