// Modelo de configuracao. Copie para 'segredos.h' e preencha.
// 'segredos.h' esta no .gitignore e nunca deve ir para o repositorio.
//
// A chave que entra aqui e a PUBLISHABLE (sb_publishable_...), nunca a SECRET.
// A secret pertence exclusivamente a API Flask - ver README da api/.
// Mesmo a publishable e extraivel da flash do ESP32: quem a protege sao as
// politicas de RLS (sql/politicas_rls.sql), que a limitam a INSERT.

#ifndef SEGREDOS_H
#define SEGREDOS_H

#define WIFI_SSID_CFG        "Wokwi-GUEST"
#define WIFI_PASSWORD_CFG    ""

#define SUPABASE_URL_CFG     "https://SEU-PROJETO.supabase.co"
#define SUPABASE_CHAVE_CFG   "sb_publishable_COLE_A_SUA_AQUI"

#endif