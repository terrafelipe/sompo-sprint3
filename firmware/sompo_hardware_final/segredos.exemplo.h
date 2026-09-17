// Modelo de configuracao. Copie para 'segredos.h' (nesta mesma pasta, ao lado do
// .ino - a Arduino IDE compila todos os arquivos da pasta do sketch) e preencha.
// 'segredos.h' esta no .gitignore e nunca deve ir para o repositorio.
//
// Incluido pelo .ino quando USAR_WIFI = 1 (Wi-Fi + envio ao Supabase). Sem o
// 'segredos.h' a compilacao falha com "segredos.h: No such file".
//
// A chave que entra aqui e a PUBLISHABLE (sb_publishable_...), nunca a SECRET.
// A secret pertence exclusivamente a API Flask - ver README da api/.
// Mesmo a publishable e extraivel da flash do ESP32: quem a protege sao as
// politicas de RLS (sql/preparar_supabase.sql), que a limitam a INSERT.

#ifndef SEGREDOS_H
#define SEGREDOS_H

// Hotspot do celular em 2.4 GHz (o ESP32 nao enxerga 5 GHz).
#define WIFI_SSID_CFG        "NomeDoSeuHotspot"
#define WIFI_PASSWORD_CFG    "suasenha"

#define SUPABASE_URL_CFG     "https://SEU-PROJETO.supabase.co"
#define SUPABASE_CHAVE_CFG   "sb_publishable_COLE_A_SUA_AQUI"

// Gerado uma unica vez no painel, em Equipamentos > Credencial. Cada ESP32
// recebe seu proprio token; ele nunca deve ser reutilizado em outra maquina.
#define DISPOSITIVO_TOKEN_CFG "COLE_O_TOKEN_DESTE_EQUIPAMENTO"

#endif
